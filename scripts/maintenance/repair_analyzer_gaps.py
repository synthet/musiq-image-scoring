#!/usr/bin/env python3
"""
Apply DB repairs for issues reported by scripts/analysis/analyze_phase_status.py.

Repairs:
  --keywords        GAP-E: sync images.keywords -> image_keywords / keywords_dim
  --keywords-ips    GAP-B: image_keywords exists but no 'keywords' IPS row -> set done
  --index-meta      GAP-D: scoring=done but indexing/metadata not done -> set both done
  --stuck-running   GAP-K: IPS rows stuck in running/queued -> failed (with message)
  --culling-ips     GAP-C: culling IPS=failed but has stack_id/embedding -> set done
  --folder-agg      GAP-F: recompute folders.phase_agg_json (SLOW — run separately)
  --missing-rows    GAP-J: insert ``not_started`` IPS rows for images that have no
                    row at all for required phases (partial-failure indexing cohort)

--all runs keywords + keywords-ips + index-meta + stuck-running + culling-ips (not folder-agg, not missing-rows). Add --folder-agg or --missing-rows to include those.

Bird species (GAP-I) is NOT fixed here — re-run the Bird Species job from the UI/API.

Usage (WSL + ~/.venvs/tf, same as webapp):
  python scripts/maintenance/repair_analyzer_gaps.py --dry-run --all
  python scripts/maintenance/repair_analyzer_gaps.py --all
  python scripts/maintenance/repair_analyzer_gaps.py --all --folder-agg --folder-agg-limit 200
  python scripts/maintenance/repair_analyzer_gaps.py --keywords --limit 500
  python scripts/maintenance/repair_analyzer_gaps.py --stuck-running --stuck-hours 2
"""

from __future__ import annotations

import argparse
import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from modules import db  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description='Repair DB gaps detected by analyze_phase_status.py')
    parser.add_argument('--dry-run', action='store_true', help='Print counts only; no writes (where supported)')
    parser.add_argument(
        '--all',
        action='store_true',
        help='Run keywords, index-meta, stuck-running (excludes --folder-agg unless also passed)',
    )
    parser.add_argument('--keywords', action='store_true', help='Backfill image_keywords from images.keywords')
    parser.add_argument('--keywords-ips', action='store_true', help='Backfill keywords IPS=done from junction table')
    parser.add_argument('--index-meta', action='store_true', help='Backfill indexing+metadata IPS when scoring done')
    parser.add_argument('--stuck-running', action='store_true', help='Mark old running/queued IPS as failed')
    parser.add_argument('--culling-ips', action='store_true', help='Reset culling IPS=failed to done if data present')
    parser.add_argument('--folder-agg', action='store_true', help='Recompute folder phase aggregate cache')
    parser.add_argument(
        '--missing-rows',
        action='store_true',
        help='Insert not_started IPS rows for images with no row for required phases',
    )
    parser.add_argument(
        '--missing-rows-folder',
        type=str,
        default=None,
        metavar='PATH',
        help='Restrict --missing-rows to images under this folder (and descendants)',
    )
    parser.add_argument('--limit', type=int, default=None, metavar='N', help='Max images for keywords/index-meta')
    parser.add_argument('--stuck-hours', type=int, default=2, metavar='N', help='Age threshold for stuck IPS')
    parser.add_argument('--stuck-phase', type=str, default=None, metavar='CODE', help='Only this phase (e.g. culling)')
    parser.add_argument(
        '--folder-agg-limit',
        type=int,
        default=None,
        metavar='N',
        help='Max folders to recompute (deepest-first); default all',
    )
    args = parser.parse_args()

    run_kw = args.keywords or args.all
    run_kw_ips = args.keywords_ips or args.all
    run_im = args.index_meta or args.all
    run_stuck = args.stuck_running or args.all
    run_cull = args.culling_ips or args.all
    run_fa = args.folder_agg  # not implied by --all (too slow for typical runs)
    run_mr = args.missing_rows  # not implied by --all (operator opts in)

    if not (run_kw or run_kw_ips or run_im or run_stuck or run_cull or run_fa or run_mr):
        parser.error('Specify --all or one of the repair flags')

    print('[repair] running init_db() (schema / pool; may take a moment)…', flush=True)
    db.init_db()
    print('[repair] init_db() done', flush=True)

    if run_kw:
        print('[repair] keywords junction (legacy CSV -> image_keywords)…', flush=True)
        r = db.repair_legacy_keywords_junction(limit=args.limit, dry_run=args.dry_run)
        print(f"[keywords] matched={r['matched']:,}  synced={r.get('synced', 0):,}  nulled={r.get('nulled', 0):,}  dry_run={args.dry_run}", flush=True)

    if run_kw_ips:
        print('[repair] keywords IPS rows…', flush=True)
        r = db.backfill_keywords_ips_done(dry_run=args.dry_run)
        print(f"[keywords-ips] matched={r['matched']:,}  created={r['created']:,}  dry_run={args.dry_run}", flush=True)

    if run_im:
        print('[repair] index/metadata IPS backfill…', flush=True)
        n = db.backfill_index_meta_global(limit=args.limit, dry_run=args.dry_run)
        print(f"[index-meta] images_{'would_update' if args.dry_run else 'updated'}={n:,}", flush=True)

    if run_stuck:
        print('[repair] stuck running/queued IPS…', flush=True)
        r = db.repair_stuck_running_ips(
            hours=args.stuck_hours,
            phase_code=args.stuck_phase,
            dry_run=args.dry_run,
        )
        print(
            f"[stuck-running] matched={r['matched']:,}  updated={r['updated']:,}  "
            f"hours>={args.stuck_hours}  dry_run={args.dry_run}",
            flush=True,
        )

    if run_cull:
        print('[repair] culling IPS (failed but has data)…', flush=True)
        r = db.repair_culling_ips_failed_has_data(dry_run=args.dry_run)
        print(f"[culling-ips] matched={r['matched']:,}  repaired={r['repaired']:,}  dry_run={args.dry_run}", flush=True)

    if run_fa:
        if args.dry_run:
            print(
                "[folder-agg] dry-run: would mark all folders dirty and recompute (use without --dry-run)",
                flush=True,
            )
        else:
            print(
                '[repair] folder phase aggregates (one folder at a time; can take a long time)…',
                flush=True,
            )
            out = db.backfill_folder_phase_aggregates(limit=args.folder_agg_limit)
            print(f"[folder-agg] recomputed={out['recomputed']:,}  selected={out['total']:,}", flush=True)

    if run_mr:
        scope = args.missing_rows_folder or '<all folders>'
        print(f'[repair] missing IPS rows backfill (scope={scope})…', flush=True)
        r = db.backfill_missing_phase_rows(
            folder_path=args.missing_rows_folder,
            limit=args.limit,
            dry_run=args.dry_run,
        )
        action = 'would_insert' if args.dry_run else 'inserted'
        by_phase_str = ', '.join(f"{k}={v:,}" for k, v in (r.get('by_phase') or {}).items())
        print(
            f"[missing-rows] matched={r['matched']:,}  {action}={r['inserted']:,}  "
            f"by_phase=[{by_phase_str}]  dry_run={args.dry_run}",
            flush=True,
        )


if __name__ == '__main__':
    main()

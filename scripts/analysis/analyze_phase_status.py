#!/usr/bin/env python3
"""
analyze_phase_status.py

Cross-checks IMAGE_PHASE_STATUS records against actual data presence in IMAGES
and related tables. Reports discrepancies per image and per folder, and
identifies potential logic gaps in the pipeline.

Architecture reference: docs/technical/WORKFLOW_STAGES_ANALYSIS.md

Discrepancy types detected (GAP codes map to that document):
   1. ips_done_no_data         [GAP-A] IPS=done but phase data is missing in DB
   2. ips_missing_has_data     [GAP-B] No IPS row exists but phase data is present
   3. ips_not_started_has_data [GAP-C] IPS=not_started but phase data already exists
   4. ips_failed_has_data      [GAP-C] IPS=failed but phase data is present (partial success)
   5. phase_order_violation    [GAP-D] Later phase=done but an earlier required phase is not done
   6. folder_cache_stale       [GAP-F] folders.phase_agg_json is dirty or missing
   7. folder_flag_mismatch     [GAP-G] is_fully_scored / is_keywords_processed disagree with IPS
   8. keywords_dual_storage    [GAP-E] images.keywords and image_keywords are out of sync
   9. ips_status_invalid       [GAP-H] IPS status value not in PhaseStatus enum
  10. bird_species_gap         [GAP-I/J] images with 'birds' not species-classified (outside IPS)
  11. stuck_running            [GAP-K] IPS rows frozen in running/queued (job_id propagation loss)

Usage (WSL + ~/.venvs/tf):
  python scripts/analysis/analyze_phase_status.py
  python scripts/analysis/analyze_phase_status.py --folder /mnt/d/Photos/Z8
  python scripts/analysis/analyze_phase_status.py --phase scoring --verbose
  python scripts/analysis/analyze_phase_status.py --limit 5000 --output /tmp/report.json
"""

import argparse
import json
import logging
import os
import sys
from collections import defaultdict
from datetime import datetime
from typing import Dict, List, Optional

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from modules import db  # noqa: E402
from modules.phases import PIPELINE_PHASE_ORDER, PhaseStatus  # noqa: E402

logging.basicConfig(level=logging.WARNING, format='%(levelname)s: %(message)s')

# ── Constants ─────────────────────────────────────────────────────────────────

PHASES = [p.value for p in PIPELINE_PHASE_ORDER]
PHASE_ORDER_IDX = {p: i for i, p in enumerate(PHASES)}

# Derived from the PhaseStatus enum in modules/phases.py
VALID_STATUSES = frozenset(s.value for s in PhaseStatus)
# 'pending' appears in the DB CHECK constraint but is absent from the enum — a known gap
CONSTRAINT_EXTRA = frozenset({'pending'})

# Each phase maps to a key in the enriched image dict that signals data presence
DATA_SIGNAL = {
    'indexing': 'data_indexing',
    'metadata': 'data_metadata',
    'scoring':  'data_scoring',
    'culling':  'data_culling',
    'keywords': 'data_keywords',
}

# Phases where IPS=done with no data output is a VALID state (not a gap).
# keywords: tagger ran but produced zero keywords for the image.
# Scoring/indexing/metadata always produce data if they complete — not included.
OPTIONAL_DATA_PHASES = frozenset({'keywords'})

# Human-readable labels for the report
DISCREPANCY_LABELS = {
    'ips_done_no_data':           'IPS=done but no data present',
    'ips_missing_has_data':       'No IPS row but data is present',
    'ips_not_started_has_data':   'IPS=not_started but data already present',
    'ips_failed_has_data':        'IPS=failed but data is present',
    'phase_order_violation':      'Later phase=done, earlier phase not done',
    'ips_status_invalid':         'IPS status not in PhaseStatus enum',
    'keywords_dual_storage':      'images.keywords / image_keywords out of sync',
    'folder_cache_stale':         'folders.phase_agg_json dirty or missing',
    'folder_flag_mismatch':       'Folder flag contradicts IPS aggregate',
}

SAMPLE_LIMIT = 10
BATCH_SIZE = 500

# Default threshold for flagging IPS rows stuck in 'running'/'queued'
DEFAULT_STUCK_HOURS = 2


# ── Helpers ───────────────────────────────────────────────────────────────────

def _batches(lst, size=BATCH_SIZE):
    for i in range(0, len(lst), size):
        yield lst[i:i + size]


def _wsl_path(folder_path: str) -> str:
    try:
        from modules import utils
        if hasattr(utils, 'convert_path_to_wsl'):
            return utils.convert_path_to_wsl(folder_path) or folder_path
    except Exception:
        pass
    return folder_path


def _folder_filter(folder_path: Optional[str], alias: str = 'f'):
    """Returns (where_fragment starting with 'AND', params) for folder tree filtering."""
    if not folder_path:
        return '', []
    target = _wsl_path(folder_path)
    return (
        f'AND ({alias}.path = ? OR {alias}.path LIKE ? OR {alias}.path LIKE ?)',
        [target, target + '/%', target + '\\%'],
    )


def _trunc(s: Optional[str], n: int = 65) -> str:
    if not s:
        return ''
    return ('...' + s[-(n - 3):]) if len(s) > n else s


def _blob_str(value) -> Optional[str]:
    """Safely convert a Firebird BLOB value to str."""
    if value is None:
        return None
    try:
        if hasattr(value, 'read'):
            return value.read()
        return str(value)
    except Exception:
        return str(value)


# ── Data loading ──────────────────────────────────────────────────────────────

def load_images(conn, folder_path: Optional[str] = None, limit: Optional[int] = None) -> List[dict]:
    """
    Load image rows augmented with per-phase data-presence signals.

    Data signals per phase:
      indexing  — file_path and folder_id are non-null
      metadata  — thumbnail_path or metadata column is non-null, or row in image_exif
      scoring   — score_general > 0 AND score_technical AND at least one legacy model row in image_model_scores (Postgres) or score_spaq non-null (Firebird)
      culling   — image_embedding IS NOT NULL OR stack_id IS NOT NULL
                  (embedding = processed by clustering runner; stack_id = assigned to
                  a cluster; singletons have embedding but no stack_id, stacked images
                  may have stack_id without embedding on older records)
      keywords  — images.keywords is non-null OR row exists in image_keywords
    """
    c = conn.cursor()
    fsql, fparams = _folder_filter(folder_path)
    first = f'FIRST {limit}' if limit else ''

    if db._get_db_engine() == "postgres":
        culling_data_sql = (
            f"CASE WHEN i.stack_id IS NOT NULL OR ({db._postgres_has_default_embedding_sql('i')}) "
            f"THEN 1 ELSE 0 END"
        )
        scoring_data_sql = (
            "CASE WHEN i.score_general IS NOT NULL AND i.score_general > 0 "
            "AND i.score_technical IS NOT NULL "
            "AND EXISTS ("
            "  SELECT 1 FROM image_model_scores ims "
            "  WHERE ims.image_id = i.id AND ims.model_name = 'spaq' "
            "    AND ims.status = 'success' AND ims.is_shadow = FALSE "
            "    AND COALESCE(ims.normalized, ims.raw_score) IS NOT NULL"
            ") THEN 1 ELSE 0 END"
        )
    else:
        culling_data_sql = (
            "CASE WHEN i.image_embedding IS NOT NULL OR i.stack_id IS NOT NULL "
            "THEN 1 ELSE 0 END"
        )
        scoring_data_sql = (
            "CASE WHEN i.score_general IS NOT NULL AND i.score_general > 0 "
            "AND i.score_technical IS NOT NULL AND i.score_spaq IS NOT NULL "
            "THEN 1 ELSE 0 END"
        )

    c.execute(f"""
        SELECT {first}
            i.id,
            i.file_path,
            i.file_name,
            i.folder_id,
            COALESCE(f.path, '') AS folder_path,
            CASE WHEN i.file_path IS NOT NULL AND i.folder_id IS NOT NULL
                 THEN 1 ELSE 0 END AS data_indexing,
            CASE WHEN i.thumbnail_path IS NOT NULL OR i.metadata IS NOT NULL
                 THEN 1 ELSE 0 END AS data_metadata_basic,
            {scoring_data_sql} AS data_scoring,
            {culling_data_sql} AS data_culling,
            CASE WHEN i.keywords IS NOT NULL AND CHAR_LENGTH(i.keywords) > 0
                 THEN 1 ELSE 0 END AS data_keywords_legacy
        FROM images i
        LEFT JOIN folders f ON f.id = i.folder_id
        WHERE 1=1 {fsql}
    """, fparams)

    cols = [d[0].lower() for d in c.description]
    rows = [dict(r) for r in c.fetchall()]
    if not rows:
        return rows

    ids = [r['id'] for r in rows]
    exif_ids: set = set()
    kw_junction_ids: set = set()

    # Batch-query presence in related tables
    for batch in _batches(ids):
        ph = ','.join(['?'] * len(batch))
        try:
            c.execute(f'SELECT DISTINCT image_id FROM image_exif WHERE image_id IN ({ph})', batch)
            exif_ids.update(r[0] for r in c.fetchall())
        except Exception:
            pass  # table may not exist on older DB versions

        try:
            c.execute(f'SELECT DISTINCT image_id FROM image_keywords WHERE image_id IN ({ph})', batch)
            kw_junction_ids.update(r[0] for r in c.fetchall())
        except Exception:
            pass

    for row in rows:
        iid = row['id']
        row['has_exif'] = iid in exif_ids
        row['data_keywords_junction'] = iid in kw_junction_ids
        # Combined signals
        row['data_metadata'] = bool(row['data_metadata_basic'] or iid in exif_ids)
        row['data_keywords'] = bool(row['data_keywords_legacy'] or iid in kw_junction_ids)

    return rows


def load_ips(conn, image_ids: List[int]) -> Dict[int, Dict[str, dict]]:
    """Returns {image_id: {phase_code: {'status': ..., 'updated_at': ...}}}"""
    result: Dict[int, Dict[str, dict]] = defaultdict(dict)
    if not image_ids:
        return result
    c = conn.cursor()
    for batch in _batches(image_ids):
        ph = ','.join(['?'] * len(batch))
        c.execute(f"""
            SELECT ips.image_id, pp.code, ips.status, ips.updated_at
            FROM image_phase_status ips
            JOIN pipeline_phases pp ON pp.id = ips.phase_id
            WHERE ips.image_id IN ({ph})
        """, batch)
        for row in c.fetchall():
            # Do not tuple-unpack RowWrapper: __iter__ yields (key, value) pairs, not columns.
            img_id, code, status, updated_at = row[0], row[1], row[2], row[3]
            # Firebird may return VARCHAR codes uppercase; normalize to match PhaseCode
            code_norm = str(code).strip().lower() if code is not None else ''
            status_norm = str(status).strip().lower() if status is not None else None
            result[img_id][code_norm] = {
                'status': status_norm,
                'updated_at': str(updated_at) if updated_at else None,
            }
    return result


# ── Per-image analysis ────────────────────────────────────────────────────────

def analyze_image(img: dict, ips_map: dict, phases: List[str]) -> List[dict]:
    """Returns a list of discrepancy records for one image."""
    issues = []
    img_id = img['id']
    img_ips = ips_map.get(img_id, {})
    statuses: Dict[str, Optional[str]] = {}

    for phase in phases:
        entry = img_ips.get(phase)
        status = entry['status'] if entry else None
        data_present = bool(img.get(DATA_SIGNAL[phase], False))
        statuses[phase] = status

        ctx = {
            'image_id': img_id,
            'file_path': img.get('file_path', ''),
            'folder_path': img.get('folder_path', ''),
            'phase': phase,
            'ips_status': status,
            'data_present': data_present,
        }

        if status == 'done' and not data_present and phase not in OPTIONAL_DATA_PHASES:
            issues.append({**ctx, 'type': 'ips_done_no_data'})

        elif entry is None and data_present:
            issues.append({**ctx, 'type': 'ips_missing_has_data'})

        elif status == 'not_started' and data_present:
            issues.append({**ctx, 'type': 'ips_not_started_has_data'})

        elif status == 'failed' and data_present:
            issues.append({**ctx, 'type': 'ips_failed_has_data'})

        if status is not None and status not in VALID_STATUSES and status not in CONSTRAINT_EXTRA:
            issues.append({**ctx, 'type': 'ips_status_invalid'})

    # Phase-order violations: a later phase is done while a required predecessor is not.
    # Only direct dependencies are checked to avoid false positives.
    REQUIRED_BEFORE = {
        'metadata': ['indexing'],
        'scoring':  ['metadata'],
        'culling':  ['scoring'],
        'keywords': ['scoring'],
    }
    for phase in phases:
        if statuses.get(phase) != 'done':
            continue
        for earlier in REQUIRED_BEFORE.get(phase, []):
            if earlier not in phases:
                continue
            earlier_status = statuses.get(earlier)
            if earlier_status is None or earlier_status in ('not_started', 'failed'):
                issues.append({
                    'type': 'phase_order_violation',
                    'image_id': img_id,
                    'file_path': img.get('file_path', ''),
                    'folder_path': img.get('folder_path', ''),
                    'phase': phase,
                    'ips_status': statuses.get(phase),
                    'data_present': None,
                    'earlier_phase': earlier,
                    'earlier_status': earlier_status,
                })

    return issues


# ── Folder-level checks ───────────────────────────────────────────────────────

def check_folder_caches(conn, folder_path: Optional[str] = None) -> dict:
    """
    Check folder-level cache consistency.

    Detects:
      - folders.phase_agg_dirty = 1 or phase_agg_json NULL/empty (stale)
      - is_fully_scored / is_keywords_processed flags that contradict live IPS counts
    """
    c = conn.cursor()
    fsql, fparams = _folder_filter(folder_path, alias='f')

    c.execute(f"""
        SELECT f.id, f.path, f.is_fully_scored, f.is_keywords_processed,
               f.phase_agg_dirty, f.phase_agg_json
        FROM folders f
        WHERE 1=1 {fsql}
    """, fparams)

    cols = [d[0].lower() for d in c.description]
    folders = [dict(r) for r in c.fetchall()]

    stale: List[dict] = []
    flag_mismatches: List[dict] = []

    if not folders:
        return {'stale': stale, 'flag_mismatches': flag_mismatches}

    folder_ids = [f['id'] for f in folders]
    # Bulk-query scoring and keywords IPS counts per folder
    counts_by_folder: Dict[int, dict] = {}
    for batch in _batches(folder_ids):
        ph = ','.join(['?'] * len(batch))
        c.execute(f"""
            SELECT
                i.folder_id,
                COUNT(i.id) AS total,
                COALESCE(SUM(CASE WHEN s_ips.status = 'done' THEN 1 ELSE 0 END), 0) AS scoring_done,
                COALESCE(SUM(CASE WHEN k_ips.status IN ('done', 'skipped') THEN 1 ELSE 0 END), 0) AS kw_done
            FROM images i
            LEFT JOIN (
                SELECT ips.image_id, ips.status
                FROM image_phase_status ips
                JOIN pipeline_phases pp ON pp.id = ips.phase_id
                WHERE pp.code = 'scoring'
            ) s_ips ON s_ips.image_id = i.id
            LEFT JOIN (
                SELECT ips.image_id, ips.status
                FROM image_phase_status ips
                JOIN pipeline_phases pp ON pp.id = ips.phase_id
                WHERE pp.code = 'keywords'
            ) k_ips ON k_ips.image_id = i.id
            WHERE i.folder_id IN ({ph})
            GROUP BY i.folder_id
        """, batch)
        for folder_id, total, scoring_done, kw_done in c.fetchall():
            counts_by_folder[folder_id] = {
                'total': total,
                'scoring_done': scoring_done,
                'kw_done': kw_done,
            }

    for folder in folders:
        fid = folder['id']
        fpath = folder.get('path', '')

        # Check 6: stale cache (NULL → treat as dirty; 0 = clean, 1 = dirty)
        dirty_val = folder.get('phase_agg_dirty')
        dirty = 1 if dirty_val is None else int(dirty_val)
        agg_json_raw = _blob_str(folder.get('phase_agg_json'))
        has_json = bool(agg_json_raw and agg_json_raw.strip())
        if dirty or not has_json:
            stale.append({
                'folder_id': fid,
                'folder_path': fpath,
                'dirty': bool(dirty),
                'has_json': has_json,
            })

        # Check 7: legacy flag mismatches
        cnts = counts_by_folder.get(fid, {'total': 0, 'scoring_done': 0, 'kw_done': 0})
        total = cnts['total']
        if total == 0:
            continue

        is_fully = int(folder.get('is_fully_scored') or 0)
        expected_fully = 1 if cnts['scoring_done'] == total else 0
        if is_fully != expected_fully:
            flag_mismatches.append({
                'folder_id': fid,
                'folder_path': fpath,
                'flag': 'is_fully_scored',
                'stored': is_fully,
                'expected': expected_fully,
                'total': total,
                'done': cnts['scoring_done'],
            })

        is_kw = int(folder.get('is_keywords_processed') or 0)
        expected_kw = 1 if cnts['kw_done'] == total else 0
        if is_kw != expected_kw:
            flag_mismatches.append({
                'folder_id': fid,
                'folder_path': fpath,
                'flag': 'is_keywords_processed',
                'stored': is_kw,
                'expected': expected_kw,
                'total': total,
                'done': cnts['kw_done'],
            })

    return {'stale': stale, 'flag_mismatches': flag_mismatches}


def check_keywords_sync(conn, image_ids: List[int]) -> dict:
    """
    Check 8: images where images.keywords and image_keywords are out of sync.

    Returns:
      legacy_only:  images.keywords IS NOT NULL but no rows in image_keywords
      junction_only: image_keywords rows exist but images.keywords IS NULL
    """
    result: Dict[str, List[dict]] = {'legacy_only': [], 'junction_only': []}
    if not image_ids:
        return result

    c = conn.cursor()
    for batch in _batches(image_ids):
        ph = ','.join(['?'] * len(batch))

        try:
            c.execute(f"""
                SELECT i.id, i.file_path, COALESCE(f.path, '') AS folder_path
                FROM images i
                LEFT JOIN folders f ON f.id = i.folder_id
                WHERE i.id IN ({ph})
                  AND i.keywords IS NOT NULL AND i.keywords <> ''
                  AND NOT EXISTS (
                      SELECT 1 FROM image_keywords ik WHERE ik.image_id = i.id
                  )
            """, batch)
            cols = [d[0].lower() for d in c.description]
            result['legacy_only'].extend(dict(r) for r in c.fetchall())

            c.execute(f"""
                SELECT i.id, i.file_path, COALESCE(f.path, '') AS folder_path
                FROM images i
                LEFT JOIN folders f ON f.id = i.folder_id
                WHERE i.id IN ({ph})
                  AND i.keywords IS NULL
                  AND EXISTS (
                      SELECT 1 FROM image_keywords ik WHERE ik.image_id = i.id
                  )
            """, batch)
            result['junction_only'].extend(dict(r) for r in c.fetchall())
        except Exception as exc:
            logging.warning('keywords sync check failed: %s', exc)

    return result


# ── Bird Species ID check ─────────────────────────────────────────────────────

def check_bird_species(conn, image_ids: List[int]) -> dict:
    """
    Check 10: Bird Species ID phase (not tracked by pipeline_phases / IPS).

    Finds images that have the 'birds' keyword (via image_keywords junction) but
    lack any 'species:*' keyword — meaning they were never processed by
    BirdSpeciesRunner, or the runner completed without writing results.

    Also finds images that have 'species:*' keywords but are missing 'birds',
    which may indicate a tagging inconsistency or that 'birds' was removed after
    species classification ran.

    Note: bird_species uses synthetic job_phases (see api._synthetic_bird_species_job_phases)
    and has no IPS row — so discrepancy detection relies entirely on data signals.
    """
    result: Dict[str, List[dict]] = {
        'birds_no_species': [],   # tagged birds, never species-classified
        'species_no_birds': [],   # has species: tag but missing birds tag
    }
    if not image_ids:
        return result

    c = conn.cursor()
    try:
        for batch in _batches(image_ids):
            ph = ','.join(['?'] * len(batch))

            # Images with 'birds' keyword but no 'species:*' keyword
            c.execute(f"""
                SELECT i.id, i.file_path, COALESCE(f.path, '') AS folder_path
                FROM images i
                LEFT JOIN folders f ON f.id = i.folder_id
                WHERE i.id IN ({ph})
                  AND EXISTS (
                      SELECT 1 FROM image_keywords ik
                      JOIN keywords_dim kd ON kd.keyword_id = ik.keyword_id
                      WHERE ik.image_id = i.id AND kd.keyword_norm LIKE '%birds%'
                  )
                  AND NOT EXISTS (
                      SELECT 1 FROM image_keywords ik2
                      JOIN keywords_dim kd2 ON kd2.keyword_id = ik2.keyword_id
                      WHERE ik2.image_id = i.id AND kd2.keyword_norm STARTING WITH 'species:'
                  )
            """, batch)
            cols = [d[0].lower() for d in c.description]
            result['birds_no_species'].extend(dict(r) for r in c.fetchall())

            # Images with 'species:*' keyword but no 'birds' keyword
            c.execute(f"""
                SELECT i.id, i.file_path, COALESCE(f.path, '') AS folder_path
                FROM images i
                LEFT JOIN folders f ON f.id = i.folder_id
                WHERE i.id IN ({ph})
                  AND EXISTS (
                      SELECT 1 FROM image_keywords ik
                      JOIN keywords_dim kd ON kd.keyword_id = ik.keyword_id
                      WHERE ik.image_id = i.id AND kd.keyword_norm STARTING WITH 'species:'
                  )
                  AND NOT EXISTS (
                      SELECT 1 FROM image_keywords ik2
                      JOIN keywords_dim kd2 ON kd2.keyword_id = ik2.keyword_id
                      WHERE ik2.image_id = i.id AND kd2.keyword_norm LIKE '%birds%'
                  )
            """, batch)
            result['species_no_birds'].extend(dict(r) for r in c.fetchall())
    except Exception as exc:
        logging.warning('bird_species check failed (keywords_dim may be absent): %s', exc)

    return result


# ── Stuck-running IPS check ───────────────────────────────────────────────────

def check_stuck_running(conn, stuck_hours: int = DEFAULT_STUCK_HOURS, folder_path: Optional[str] = None) -> List[dict]:
    """
    Check 11: IPS rows frozen in 'running' or 'queued' state longer than stuck_hours.

    These arise from the job_id propagation gap in engine.py (BatchImageProcessor):
    if job_id context is lost inside the worker queue, completion callbacks never
    fire, leaving IPS rows permanently in 'running'.

    Returns a list of stuck rows with image_id, phase, status, and age.
    """
    from datetime import timedelta
    threshold = datetime.utcnow() - timedelta(hours=stuck_hours)

    fsql, fparams = _folder_filter(folder_path)
    c = conn.cursor()

    try:
        c.execute(f"""
            SELECT
                ips.image_id,
                pp.code        AS phase_code,
                ips.status,
                ips.started_at,
                ips.updated_at,
                i.file_path,
                COALESCE(f.path, '') AS folder_path
            FROM image_phase_status ips
            JOIN pipeline_phases pp ON pp.id = ips.phase_id
            JOIN images i ON i.id = ips.image_id
            LEFT JOIN folders f ON f.id = i.folder_id
            WHERE ips.status IN ('running', 'queued')
              AND (
                  (ips.updated_at IS NOT NULL AND ips.updated_at < ?)
                  OR (ips.updated_at IS NULL AND ips.started_at IS NOT NULL AND ips.started_at < ?)
              )
              {fsql}
        """, [threshold, threshold] + fparams)

        cols = [d[0].lower() for d in c.description]
        rows = []
        for r in c.fetchall():
            row = dict(r)
            # Compute age string
            ts = row.get('updated_at') or row.get('started_at')
            if ts:
                try:
                    if isinstance(ts, str):
                        from datetime import datetime as _dt
                        ts = _dt.fromisoformat(ts)
                    age_h = (datetime.utcnow() - ts).total_seconds() / 3600
                    row['age_hours'] = round(age_h, 1)
                except Exception:
                    row['age_hours'] = None
            rows.append(row)
        return rows
    except Exception as exc:
        logging.warning('stuck_running check failed: %s', exc)
        return []


# ── Reporting ─────────────────────────────────────────────────────────────────

def _phase_cell(status: Optional[str], data_present: bool) -> str:
    """Compact cell for the verbose per-image table: 'status(Y/N)'."""
    s = status or '-'
    d = 'Y' if data_present else 'N'
    if status == 'done' and not data_present:
        return f'DONE!{d}'   # discrepancy — done but no data
    if status is None and data_present:
        return f'null!{d}'   # discrepancy — no IPS but data present
    if status in ('not_started', 'failed') and data_present:
        return f'{s}!{d}'    # discrepancy
    return f'{s}|{d}'


def print_report(
    images: List[dict],
    all_issues: List[dict],
    folder_results: dict,
    kw_sync: dict,
    phases: List[str],
    ips_map: dict,
    bird_species: Optional[dict] = None,
    stuck_running: Optional[List[dict]] = None,
    verbose: bool = False,
):
    total_images = len(images)
    total_folders = len({img['folder_path'] for img in images})
    sep = '─' * 72

    print()
    print('=' * 72)
    print('  Phase Status Analysis')
    print('=' * 72)
    print(f'  Images analyzed  : {total_images:,}')
    print(f'  Folders          : {total_folders:,}')
    print(f'  Phases checked   : {", ".join(phases)}')
    print(f'  Total issues     : {len(all_issues):,}')
    print()

    # ── Single-pass aggregation: build all lookup structures together ─────
    per_phase_types = [
        'ips_done_no_data',
        'ips_missing_has_data',
        'ips_not_started_has_data',
        'ips_failed_has_data',
        'ips_status_invalid',
    ]
    per_phase_types_set = set(per_phase_types)
    by_phase: Dict[str, Dict[str, int]] = {p: defaultdict(int) for p in phases}
    by_type: Dict[str, List[dict]] = defaultdict(list)
    pov: List[dict] = []
    for issue in all_issues:
        itype = issue['type']
        by_type[itype].append(issue)
        if itype in per_phase_types_set:
            by_phase[issue['phase']][itype] += 1
        if itype == 'phase_order_violation':
            pov.append(issue)

    short_col = {
        'ips_done_no_data':           'done/no-data',
        'ips_missing_has_data':       'miss/has-data',
        'ips_not_started_has_data':   'ns/has-data',
        'ips_failed_has_data':        'fail/has-data',
        'ips_status_invalid':         'bad-status',
    }

    print(sep)
    print('  Per-Phase Discrepancy Summary')
    print(sep)
    col_w = 14
    header = f"  {'Phase':<12}" + ''.join(f"{short_col[t]:>{col_w}}" for t in per_phase_types)
    print(header)
    for phase in phases:
        row = f"  {phase:<12}" + ''.join(f"{by_phase[phase].get(t, 0):>{col_w},}" for t in per_phase_types)
        print(row)
    print()

    # ── Phase-order violations ─────────────────────────────────────────────
    print(sep)
    print(f'  Phase Order Violations: {len(pov):,}')
    print(sep)
    if pov:
        viol_counts: Dict[str, int] = defaultdict(int)
        for v in pov:
            key = f"{v['phase']}=done  but  {v['earlier_phase']}={v.get('earlier_status') or 'missing'}"
            viol_counts[key] += 1
        for key, cnt in sorted(viol_counts.items(), key=lambda x: -x[1]):
            print(f'  {cnt:>6,}  {key}')
    else:
        print('  None.')
    print()

    # ── Folder cache ───────────────────────────────────────────────────────
    stale = folder_results['stale']
    flag_mm = folder_results['flag_mismatches']
    print(sep)
    print('  Folder Cache Consistency')
    print(sep)
    print(f'  Folders with stale/missing phase_agg_json : {len(stale):,}')
    print(f'  Folder flag mismatches                    : {len(flag_mm):,}')
    if flag_mm:
        flag_counts: Dict[str, int] = defaultdict(int)
        for m in flag_mm:
            flag_counts[m['flag']] += 1
        for flag, cnt in flag_counts.items():
            print(f'    {cnt:>4,}  {flag} stored ≠ expected')
    print()

    # ── Keywords dual storage ──────────────────────────────────────────────
    lo = kw_sync['legacy_only']
    jo = kw_sync['junction_only']
    print(sep)
    print('  Keywords Dual-Storage Sync (Check 8)')
    print(sep)
    print(f'  images.keywords set  but  image_keywords empty : {len(lo):,}')
    print(f'  image_keywords exist but  images.keywords NULL : {len(jo):,}')
    print()

    # ── Bird Species ID ────────────────────────────────────────────────────
    bns = (bird_species or {}).get('birds_no_species', [])
    snb = (bird_species or {}).get('species_no_birds', [])
    print(sep)
    print('  Bird Species ID (Check 10 — outside pipeline_phases)')
    print(sep)
    print(f'  Images with "birds" tag but no species: classification : {len(bns):,}')
    print(f'  Images with species: tag but no "birds" tag            : {len(snb):,}')
    print()

    # ── Stuck running ──────────────────────────────────────────────────────
    stuck = stuck_running or []
    print(sep)
    print('  Stuck Running / Queued IPS Rows (Check 11 — job_id propagation gap)')
    print(sep)
    print(f'  IPS rows frozen in running/queued state : {len(stuck):,}')
    if stuck:
        by_phase_stuck: Dict[str, int] = defaultdict(int)
        by_status_stuck: Dict[str, int] = defaultdict(int)
        for s in stuck:
            by_phase_stuck[s.get('phase_code', '?')] += 1
            by_status_stuck[s.get('status', '?')] += 1
        for phase, cnt in sorted(by_phase_stuck.items(), key=lambda x: -x[1]):
            print(f'    {cnt:>4,}  phase={phase}')
        for status, cnt in sorted(by_status_stuck.items(), key=lambda x: -x[1]):
            print(f'    {cnt:>4,}  status={status}')
    print()

    # ── Root-cause gap summary ─────────────────────────────────────────────
    print(sep)
    print('  Potential Logic Gaps Identified')
    print(sep)

    gap_items: List[str] = []

    # Gap A: done but no data
    done_no_data_total = sum(by_phase[p].get('ips_done_no_data', 0) for p in phases)
    if done_no_data_total:
        gap_items.append(
            f'  [GAP-A] {done_no_data_total:,} images have IPS=done but lack the expected data.\n'
            '          Likely causes: executor wrote IPS=done before writing data, or data was\n'
            '          deleted/nulled after phase completed without resetting IPS.'
        )

    # Gap B: no IPS but data present
    missing_ips_total = sum(by_phase[p].get('ips_missing_has_data', 0) for p in phases)
    if missing_ips_total:
        gap_items.append(
            f'  [GAP-B] {missing_ips_total:,} images have data but no IPS row for that phase.\n'
            '          Likely causes: legacy import path (e.g. direct DB write) that did not\n'
            '          create IMAGE_PHASE_STATUS rows, or rows were deleted from IPS table.'
        )

    # Gap C: not_started / failed but data present
    stale_reset_total = sum(by_phase[p].get('ips_not_started_has_data', 0) for p in phases)
    stale_reset_total += sum(by_phase[p].get('ips_failed_has_data', 0) for p in phases)
    if stale_reset_total:
        gap_items.append(
            f'  [GAP-C] {stale_reset_total:,} images have IPS=not_started/failed but data already\n'
            '          exists. Likely causes: IPS was reset (force-re-run) without clearing the\n'
            '          actual data columns, or a previous partial run stored data then failed.'
        )

    # Gap D: phase order violations
    if pov:
        gap_items.append(
            f'  [GAP-D] {len(pov):,} phase-order violations (later phase=done, earlier not done).\n'
            '          Likely causes: phases were triggered out of order, or earlier-phase IPS\n'
            '          rows were deleted/reset without cascading to later phases.'
        )

    # Gap E: keywords dual storage
    kw_mismatch = len(lo) + len(jo)
    if kw_mismatch:
        gap_items.append(
            f'  [GAP-E] {kw_mismatch:,} keyword sync mismatches between images.keywords and\n'
            '          image_keywords junction table. Likely cause: batch tagging (e.g. via\n'
            '          update_image_fields_batch) ran before the dual-write sync was added,\n'
            '          leaving junction table empty. Run keyword backfill to repair.'
        )

    # Gap F: folder caches
    if stale:
        gap_items.append(
            f'  [GAP-F] {len(stale):,} folders have stale or missing phase_agg_json cache.\n'
            '          Run scripts/maintenance/backfill_folder_phase_aggregates.py to repair.'
        )

    if flag_mm:
        gap_items.append(
            f'  [GAP-G] {len(flag_mm):,} folder legacy-flag mismatches (is_fully_scored /\n'
            '          is_keywords_processed). These are derived from the IPS aggregate;\n'
            '          recomputing phase_agg_json will correct them.'
        )

    # Gap H: invalid status values
    invalid_total = sum(by_phase[p].get('ips_status_invalid', 0) for p in phases)
    if invalid_total:
        gap_items.append(
            f'  [GAP-H] {invalid_total:,} IPS rows have a status value not in the PhaseStatus\n'
            '          enum (e.g. "pending"). The DB CHECK constraint allows "pending" but the\n'
            '          enum does not; this creates ambiguity in status-routing logic.'
        )

    # Gap I: bird species unclassified
    if bns:
        gap_items.append(
            f'  [GAP-I] {len(bns):,} images have the "birds" keyword but no species: classification.\n'
            '          Bird Species ID phase is not tracked in pipeline_phases/IPS; it relies on\n'
            '          synthetic job_phases. Re-run the Bird Species ID job for these images.'
        )

    # Gap J: species without birds
    if snb:
        gap_items.append(
            f'  [GAP-J] {len(snb):,} images have a species: tag but lack the "birds" keyword.\n'
            '          This may indicate the "birds" keyword was removed after species ID ran,\n'
            '          or a tagging source wrote species: directly without the parent keyword.'
        )

    # Gap K: stuck running / queued rows
    if stuck:
        oldest = max((s.get('age_hours') or 0) for s in stuck)
        gap_items.append(
            f'  [GAP-K] {len(stuck):,} IPS rows frozen in running/queued (oldest ≈ {oldest:.1f}h).\n'
            '          Caused by job_id propagation loss in engine.py BatchImageProcessor.\n'
            '          These jobs will never self-resolve; reset them manually or re-run the phase.'
        )

    if gap_items:
        print('\n'.join(gap_items))
    else:
        print('  No gaps found — all checked signals are consistent.')
    print()

    # ── Sample discrepancies ───────────────────────────────────────────────
    print(sep)
    print(f'  Sample Discrepancies (up to {SAMPLE_LIMIT} per type)')
    print(sep)


    for dtype, label in DISCREPANCY_LABELS.items():
        if dtype in ('keywords_dual_storage', 'folder_cache_stale', 'folder_flag_mismatch'):
            continue  # handled separately below
        items = by_type.get(dtype, [])
        if not items:
            continue
        print(f'\n  [{len(items):,}] {label}')
        for item in items[:SAMPLE_LIMIT]:
            if dtype == 'phase_order_violation':
                print(
                    f"    id={item['image_id']:<7}  "
                    f"{item['phase']}=done  ←  {item.get('earlier_phase')}="
                    f"{item.get('earlier_status') or 'missing'}  "
                    f"{_trunc(item['file_path'])}"
                )
            else:
                print(
                    f"    id={item['image_id']:<7}  phase={item.get('phase', ''):<10}  "
                    f"ips={item.get('ips_status') or 'null':<14}  "
                    f"data={item.get('data_present')}  "
                    f"{_trunc(item['file_path'])}"
                )
        if len(items) > SAMPLE_LIMIT:
            print(f'    … and {len(items) - SAMPLE_LIMIT:,} more')

    if lo:
        print(f'\n  [{len(lo):,}] keywords_dual_storage — legacy-only')
        for item in lo[:SAMPLE_LIMIT]:
            print(f"    id={item['id']:<7}  {_trunc(item['file_path'])}")
        if len(lo) > SAMPLE_LIMIT:
            print(f'    … and {len(lo) - SAMPLE_LIMIT:,} more')

    if jo:
        print(f'\n  [{len(jo):,}] keywords_dual_storage — junction-only')
        for item in jo[:SAMPLE_LIMIT]:
            print(f"    id={item['id']:<7}  {_trunc(item['file_path'])}")
        if len(jo) > SAMPLE_LIMIT:
            print(f'    … and {len(jo) - SAMPLE_LIMIT:,} more')

    # ── Bird species samples ────────────────────────────────────────────────
    if bns:
        print(f'\n  [{len(bns):,}] birds_no_species — has "birds", never species-classified')
        for item in bns[:SAMPLE_LIMIT]:
            print(f"    id={item['id']:<7}  {_trunc(item['file_path'])}")
        if len(bns) > SAMPLE_LIMIT:
            print(f'    … and {len(bns) - SAMPLE_LIMIT:,} more')

    if snb:
        print(f'\n  [{len(snb):,}] species_no_birds — has species: tag, missing "birds" keyword')
        for item in snb[:SAMPLE_LIMIT]:
            print(f"    id={item['id']:<7}  {_trunc(item['file_path'])}")
        if len(snb) > SAMPLE_LIMIT:
            print(f'    … and {len(snb) - SAMPLE_LIMIT:,} more')

    # ── Stuck-running samples ──────────────────────────────────────────────
    if stuck:
        print(f'\n  [{len(stuck):,}] stuck_running — IPS rows frozen in running/queued')
        for item in stuck[:SAMPLE_LIMIT]:
            age = f"{item.get('age_hours', '?')}h" if item.get('age_hours') else 'unknown age'
            print(
                f"    id={item['image_id']:<7}  phase={item.get('phase_code', '?'):<12}  "
                f"status={item.get('status', '?'):<10}  age={age}  "
                f"{_trunc(item.get('file_path', ''))}"
            )
        if len(stuck) > SAMPLE_LIMIT:
            print(f'    … and {len(stuck) - SAMPLE_LIMIT:,} more')

    # ── Folder flag mismatches (sample) ────────────────────────────────────
    if flag_mm:
        print(f'\n  [{len(flag_mm):,}] folder_flag_mismatch')
        for item in flag_mm[:SAMPLE_LIMIT]:
            print(
                f"    {item['flag']:<26}  stored={item['stored']}  expected={item['expected']}  "
                f"({item.get('done', 0)}/{item.get('total', 0)})  "
                f"{_trunc(item['folder_path'])}"
            )
        if len(flag_mm) > SAMPLE_LIMIT:
            print(f'    … and {len(flag_mm) - SAMPLE_LIMIT:,} more')

    # ── Verbose per-image table ────────────────────────────────────────────
    if verbose:
        print()
        print(sep)
        print('  Full Per-Image Phase Status')
        print(sep)
        col_w2 = max(10, max(len(p) + 4 for p in phases))
        hdr = f"  {'ID':>8}  {'File':<40}  " + '  '.join(f"{p[:col_w2]:^{col_w2}}" for p in phases)
        print(hdr)
        for img in images:
            img_ips = ips_map.get(img['id'], {})
            cells = []
            for phase in phases:
                entry = img_ips.get(phase)
                status = entry['status'] if entry else None
                data_present = bool(img.get(DATA_SIGNAL[phase], False))
                cells.append(f'{_phase_cell(status, data_present):^{col_w2}}')
            fname = _trunc(img.get('file_name') or img.get('file_path', ''), 40)
            print(f"  {img['id']:>8}  {fname:<40}  " + '  '.join(cells))

    print()
    print('=' * 72)
    print()


# ── Main ──────────────────────────────────────────────────────────────────────

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description='Analyze pipeline phase status vs actual data presence.',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument('--folder', metavar='PATH', help='Scope to one folder tree')
    parser.add_argument(
        '--phase', metavar='PHASE', choices=PHASES,
        help='Scope checks to a single phase',
    )
    parser.add_argument('--limit', type=int, metavar='N', help='Analyze at most N images')
    parser.add_argument('--output', metavar='FILE', help='Export full results as JSON')
    parser.add_argument('--verbose', action='store_true', help='Print per-image detail table')
    parser.add_argument(
        '--stuck-hours', type=int, default=DEFAULT_STUCK_HOURS, metavar='N',
        help=f'Hours threshold for flagging stuck running/queued IPS rows (default: {DEFAULT_STUCK_HOURS})',
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    phases = [args.phase] if args.phase else PHASES

    conn = db.get_db()
    try:
        print(f'Loading images…', end=' ', flush=True)
        images = load_images(conn, folder_path=args.folder, limit=args.limit)
        print(f'{len(images):,} loaded.')

        if not images:
            print('No images found. Check --folder path or DB connection.')
            return

        image_ids = [img['id'] for img in images]

        print('Loading phase statuses…', end=' ', flush=True)
        ips_map = load_ips(conn, image_ids)
        ips_row_count = sum(len(v) for v in ips_map.values())
        print(f'{ips_row_count:,} IPS rows for {len(ips_map):,} images.')

        print('Checking keywords sync…', end=' ', flush=True)
        kw_sync = check_keywords_sync(conn, image_ids)
        print('done.')

        print('Checking folder caches…', end=' ', flush=True)
        folder_results = check_folder_caches(conn, folder_path=args.folder)
        print('done.')

        print('Checking bird species classification…', end=' ', flush=True)
        bird_species = check_bird_species(conn, image_ids)
        print(f"{len(bird_species['birds_no_species']):,} unclassified, "
              f"{len(bird_species['species_no_birds']):,} orphaned species tags.")

        print(f'Checking stuck running/queued (>{args.stuck_hours}h)…', end=' ', flush=True)
        stuck_running = check_stuck_running(conn, stuck_hours=args.stuck_hours, folder_path=args.folder)
        print(f'{len(stuck_running):,} found.')

        print('Analyzing discrepancies…', end=' ', flush=True)
        all_issues: List[dict] = []
        for img in images:
            all_issues.extend(analyze_image(img, ips_map, phases))
        print(f'{len(all_issues):,} found.')

        print_report(
            images, all_issues, folder_results, kw_sync, phases, ips_map,
            bird_species=bird_species,
            stuck_running=stuck_running,
            verbose=args.verbose,
        )

        if args.output:
            export = {
                'generated_at': datetime.utcnow().isoformat() + 'Z',
                'scope': {
                    'folder': args.folder,
                    'phases': phases,
                    'limit': args.limit,
                },
                'summary': {
                    'images_analyzed': len(images),
                    'total_issues': len(all_issues),
                    'keywords_legacy_only': len(kw_sync['legacy_only']),
                    'keywords_junction_only': len(kw_sync['junction_only']),
                    'folder_stale_cache': len(folder_results['stale']),
                    'folder_flag_mismatches': len(folder_results['flag_mismatches']),
                    'bird_species_unclassified': len(bird_species['birds_no_species']),
                    'bird_species_orphaned': len(bird_species['species_no_birds']),
                    'stuck_running_rows': len(stuck_running),
                },
                'issues_by_type': {
                    dtype: [i for i in all_issues if i['type'] == dtype]
                    for dtype in DISCREPANCY_LABELS
                },
                'keywords_sync': kw_sync,
                'folder_results': folder_results,
                'bird_species': bird_species,
                'stuck_running': stuck_running,
            }
            with open(args.output, 'w', encoding='utf-8') as fh:
                json.dump(export, fh, indent=2, default=str)
            print(f'Results exported → {args.output}')
    finally:
        conn.close()


if __name__ == '__main__':
    main()

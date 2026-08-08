"""Read-only DB inventory for student-scorer Phase 0.

Usage (WSL / venv with DB access)::

    python -m scripts.research.student_scorer.audit_dataset --out artifacts/student_scorer/audit.json

Does not write to Postgres. Requires POSTGRES_* env or modules.config.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from scripts.research.student_scorer.common import (
    DEFAULT_TEACHERS,
    PROJECT_ROOT,
    ensure_artifacts_dir,
    freeze_scoring_contract,
    write_json,
)


AUDIT_SQL_VERSIONS = """
SELECT
    model_name,
    model_version,
    is_shadow,
    status,
    COUNT(*) AS image_count,
    AVG(normalized) AS mean_score,
    STDDEV_POP(normalized) AS score_std,
    MIN(scored_at) AS first_scored,
    MAX(scored_at) AS last_scored
FROM image_model_scores
GROUP BY model_name, model_version, is_shadow, status
ORDER BY model_name, model_version;
"""


def _connect():
    from modules import db_postgres

    return db_postgres.get_pg_connection()


def run_audit(
    *,
    teachers: tuple[str, ...] = DEFAULT_TEACHERS,
    dry_run_contract_only: bool = False,
) -> dict[str, Any]:
    contract = freeze_scoring_contract()
    # Prefer live fusion membership when config is available
    try:
        from modules.score_normalization import get_composite_weights, get_percentile_anchors
        from modules.config import get_config_value

        fusion = get_composite_weights()
        anchors = get_percentile_anchors()
        models_cfg = get_config_value("scoring.models", default={}) or {}
        raw = get_config_value("raw_conversion", default={}) or {}
        contract = freeze_scoring_contract(
            fusion=fusion,
            anchors=anchors,
            models_cfg=models_cfg,
            raw_method=str(raw.get("method", "rawpy_half")),
            max_resolution=int(raw.get("max_resolution", 512)),
            jpeg_quality=int(raw.get("jpeg_quality", 85)),
        )
        teachers = tuple(contract["teachers"])
    except Exception:
        pass

    report: dict[str, Any] = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "contract": contract,
        "teachers_selected": list(teachers),
        "provenance_matrix": {
            "teacher_normalized": "primary_distillation",
            "composites": "consistency_and_b0",
            "rating": "human_only_if_source_proven_else_unknown",
            "pick_status": "human_only_if_source_proven_else_unknown",
            "cull_decision": "weak_automatic_unless_source_proven",
            "label": "exclude_unless_semantics_documented",
        },
        "version_inventory": [],
        "canonical_teacher_versions": {},
        "blockers": [],
    }

    if dry_run_contract_only:
        return report

    conn = _connect()
    try:
        with conn.cursor() as cur:
            cur.execute(AUDIT_SQL_VERSIONS)
            cols = [d[0] for d in cur.description]
            rows = [dict(zip(cols, r)) for r in cur.fetchall()]
        report["version_inventory"] = rows

        # Select one canonical version per teacher (most common success, non-shadow)
        by_teacher: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for r in rows:
            if r["model_name"] in teachers and not r["is_shadow"] and r["status"] == "success":
                by_teacher[r["model_name"]].append(r)
        for name, variants in by_teacher.items():
            variants.sort(key=lambda x: int(x["image_count"] or 0), reverse=True)
            top = variants[0]
            report["canonical_teacher_versions"][name] = {
                "model_version": top["model_version"],
                "image_count": int(top["image_count"] or 0),
                "rule": "most_frequent_success_non_shadow",
            }
            if len({v["model_version"] for v in variants}) > 1:
                report["blockers"].append(
                    {
                        "type": "mixed_teacher_versions",
                        "model_name": name,
                        "versions": [
                            {"version": v["model_version"], "count": int(v["image_count"] or 0)}
                            for v in variants
                        ],
                        "action": "export only canonical version; do not merge revisions",
                    }
                )

        for t in teachers:
            if t not in report["canonical_teacher_versions"]:
                report["blockers"].append(
                    {"type": "missing_teacher", "model_name": t, "action": "backfill or drop from fusion freeze"}
                )

        # Image coverage summary
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    COUNT(*) AS n_images,
                    COUNT(*) FILTER (WHERE LOWER(file_path) ~ '\\.(nef|nrw)$') AS n_nef,
                    COUNT(score_general) AS n_with_general,
                    COUNT(burst_uuid) AS n_burst,
                    COUNT(stack_id) AS n_stack,
                    COUNT(sub_stack_id) AS n_sub_stack,
                    COUNT(bird_bbox) AS n_bird_bbox
                FROM images
                """
            )
            cols = [d[0] for d in cur.description]
            report["images_summary"] = dict(zip(cols, cur.fetchone()))

        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT code, dim, COUNT(ie.image_id) AS n
                FROM embedding_spaces es
                LEFT JOIN image_embeddings ie ON false
                GROUP BY code, dim
                """
            )
            # Fallback simpler query if join shape differs
    except Exception as exc:
        report["db_error"] = str(exc)
        report["blockers"].append({"type": "db_unavailable", "error": str(exc)})
    finally:
        try:
            conn.close()
        except Exception:
            pass

    # Embedding space inventory (best-effort, separate query)
    try:
        conn = _connect()
        with conn.cursor() as cur:
            cur.execute("SELECT code, dim, active FROM embedding_spaces ORDER BY code")
            report["embedding_spaces"] = [
                {"code": r[0], "dim": r[1], "active": r[2]} for r in cur.fetchall()
            ]
        conn.close()
    except Exception as exc:
        report["embedding_spaces_error"] = str(exc)

    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Student scorer Phase 0 DB audit")
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Write audit JSON (default: artifacts/student_scorer/audit.json)",
    )
    parser.add_argument(
        "--contract-only",
        action="store_true",
        help="Skip DB queries; emit frozen scoring contract only",
    )
    args = parser.parse_args(argv)
    report = run_audit(dry_run_contract_only=args.contract_only)
    out = args.out or (ensure_artifacts_dir() / "audit.json")
    write_json(out, report)
    print(json.dumps({"wrote": str(out), "blockers": len(report.get("blockers", []))}, indent=2))
    return 0 if not report.get("blockers") or args.contract_only else 0


if __name__ == "__main__":
    raise SystemExit(main())

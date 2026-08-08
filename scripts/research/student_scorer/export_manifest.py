"""Export an immutable offline training manifest (Phase 1).

Writes under ``artifacts/student_scorer/<manifest_id>/``. Never commits path-bearing
absolute files; local root mapping stays in untracked ``local_paths.json``.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from scripts.research.student_scorer.build_splits import (
    assert_no_cross_split_groups,
    assign_splits,
    near_duplicate_leakage,
    splits_to_dict,
)
from scripts.research.student_scorer.common import (
    DEFAULT_GATES,
    DEFAULT_TEACHERS,
    PROJECT_ROOT,
    ensure_artifacts_dir,
    freeze_scoring_contract,
    sha256_file,
    stable_hash,
    write_json,
)
from scripts.research.student_scorer.data import (
    ManifestRow,
    b0_parity_report,
    build_teacher_mask,
    compute_manifest_id,
)


def _rows_from_db(
    teachers: list[str],
    canonical_versions: dict[str, str],
    *,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    from modules import db_postgres

    conn = db_postgres.get_pg_connection()
    try:
        sql = """
            SELECT
                i.id AS image_id,
                i.file_path,
                i.image_hash,
                i.hash_version,
                i.burst_uuid,
                i.stack_id,
                i.sub_stack_id,
                i.folder_id,
                i.rating,
                i.pick_status,
                i.cull_decision,
                i.score_general,
                i.score_technical,
                i.score_aesthetic,
                i.bird_bbox,
                (e.date_time_original::date)::text AS capture_day
            FROM images i
            LEFT JOIN image_exif e ON e.image_id = i.id
            WHERE LOWER(i.file_path) ~ '\\.(nef|nrw)$'
            ORDER BY i.id
        """
        if limit:
            sql += f" LIMIT {int(limit)}"
        with conn.cursor() as cur:
            cur.execute(sql)
            cols = [d[0] for d in cur.description]
            images = [dict(zip(cols, r)) for r in cur.fetchall()]

        # Fetch teacher scores
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT image_id, model_name, model_version, raw_score, normalized, status, is_shadow
                FROM image_model_scores
                WHERE is_shadow = FALSE AND status = 'success'
                  AND model_name = ANY(%s)
                """,
                (teachers,),
            )
            score_rows = cur.fetchall()
    finally:
        conn.close()

    by_image: dict[int, dict[str, Any]] = {}
    for r in score_rows:
        image_id, model_name, model_version, raw_score, normalized, status, is_shadow = r
        want = canonical_versions.get(model_name)
        if want and model_version != want:
            continue
        slot = by_image.setdefault(image_id, {"raw": {}, "norm": {}, "ver": {}})
        slot["raw"][model_name] = float(raw_score) if raw_score is not None else None
        slot["norm"][model_name] = float(normalized) if normalized is not None else None
        slot["ver"][model_name] = model_version

    out: list[dict[str, Any]] = []
    for img in images:
        iid = int(img["image_id"])
        scores = by_image.get(iid, {"raw": {}, "norm": {}, "ver": {}})
        path = img["file_path"] or ""
        # Root-relative token: strip drive / known roots later via local_paths
        path_token = path.replace("\\", "/")
        row = ManifestRow(
            image_id=iid,
            path_token=path_token,
            image_hash=img.get("image_hash"),
            hash_version=str(img.get("hash_version") or ""),
            burst_uuid=img.get("burst_uuid"),
            stack_id=img.get("stack_id"),
            sub_stack_id=img.get("sub_stack_id"),
            folder_id=img.get("folder_id"),
            capture_day=img.get("capture_day"),
            file_exists=Path(path).is_file() if path else False,
            score_general=float(img["score_general"]) if img.get("score_general") is not None else None,
            score_technical=float(img["score_technical"]) if img.get("score_technical") is not None else None,
            score_aesthetic=float(img["score_aesthetic"]) if img.get("score_aesthetic") is not None else None,
            rating=int(img["rating"]) if img.get("rating") is not None else None,
            pick_status=int(img.get("pick_status") or 0),
            cull_decision=img.get("cull_decision"),
            teacher_raw={k: v for k, v in scores["raw"].items() if v is not None},
            teacher_normalized={k: v for k, v in scores["norm"].items() if v is not None},
            teacher_versions=dict(scores["ver"]),
            bird_bbox=img.get("bird_bbox") if isinstance(img.get("bird_bbox"), dict) else None,
        )
        row.teacher_mask = build_teacher_mask(row.teacher_normalized, teachers)
        out.append(row.to_dict())
    return out


def export_from_rows(
    rows: list[dict[str, Any]],
    *,
    contract: dict[str, Any],
    audit: dict[str, Any] | None = None,
    out_root: Path | None = None,
    seed: int = 42,
) -> Path:
    teachers = list(contract.get("teachers") or DEFAULT_TEACHERS)
    protocol_id = "ssp_" + stable_hash({"gates": DEFAULT_GATES, "contract": contract["contract_hash"]})[:12]
    meta = {
        "protocol_id": protocol_id,
        "contract_hash": contract["contract_hash"],
        "teachers": teachers,
        "preprocessing": contract.get("preprocessing"),
        "fusion": contract.get("fusion"),
        "percentile_anchors": contract.get("percentile_anchors"),
        "snapshot_time": datetime.now(timezone.utc).isoformat(),
        "source_commit": _git_commit(),
        "gates": DEFAULT_GATES,
        "n_rows": len(rows),
    }
    manifest_id = compute_manifest_id(meta=meta, rows=rows)
    meta["manifest_id"] = manifest_id

    dest = (out_root or ensure_artifacts_dir()) / manifest_id
    dest.mkdir(parents=True, exist_ok=True)

    # Parquet if pyarrow/pandas available, else JSONL
    parquet_path = dest / "manifest.parquet"
    jsonl_path = dest / "manifest.jsonl"
    try:
        import pandas as pd

        pd.DataFrame(rows).to_parquet(parquet_path, index=False)
        manifest_file = parquet_path
    except Exception:
        with jsonl_path.open("w", encoding="utf-8") as fh:
            for r in rows:
                fh.write(json.dumps(r, default=str) + "\n")
        manifest_file = jsonl_path

    assignments = assign_splits(rows, seed=seed)
    assert_no_cross_split_groups(assignments)
    leaks = near_duplicate_leakage(rows, assignments)
    if leaks:
        raise RuntimeError(
            f"near-duplicate leakage across splits ({len(leaks)} clusters); "
            "merge components and rebuild (AC-3)"
        )

    write_json(dest / "splits.json", {"assignments": splits_to_dict(assignments), "seed": seed})

    b0 = b0_parity_report(
        rows,
        fusion=contract["fusion"],
        anchors=contract["percentile_anchors"],
        teachers=teachers,
    )
    write_json(dest / "b0_parity.json", b0)

    evaluation_protocol = {
        "protocol_id": protocol_id,
        "gates": DEFAULT_GATES,
        "pair_margin": DEFAULT_GATES["pair_margin"],
        "stack_unit": "sub_stack_id_then_stack_id_then_burst",
        "selection_splits_allowed": ["train", "val"],
        "forbidden_selection_splits": ["test", "ood_test"],
        "preference_precedence": [
            "human_pick",
            "human_rating",
            "teacher_consensus",
            "composite_margin",
        ],
    }
    write_json(dest / "evaluation_protocol.json", evaluation_protocol)

    if audit:
        write_json(dest / "audit.json", audit)

    meta["checksum"] = sha256_file(manifest_file)
    write_json(dest / "manifest.meta.json", meta)

    checksums = {
        "manifest": meta["checksum"],
        "meta": stable_hash(meta),
        "protocol_id": protocol_id,
        "manifest_id": manifest_id,
    }
    write_json(dest / "checksums.sha256.json", checksums)

    # Placeholder for operator-filled local path map (gitignored via artifacts/)
    write_json(
        dest / "local_paths.example.json",
        {"path_root_token": "<PATH_ROOT>", "absolute_root": "<FILL_LOCALLY_DO_NOT_COMMIT>"},
    )
    return dest


def _git_commit() -> str:
    try:
        import subprocess

        return (
            subprocess.check_output(
                ["git", "rev-parse", "HEAD"],
                cwd=str(PROJECT_ROOT),
                stderr=subprocess.DEVNULL,
            )
            .decode()
            .strip()
        )
    except Exception:
        return "unknown"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Export student scorer manifest")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--from-jsonl", type=Path, default=None, help="Offline rows (no DB)")
    parser.add_argument("--audit", type=Path, default=None)
    args = parser.parse_args(argv)

    contract = freeze_scoring_contract()
    audit = None
    if args.audit and args.audit.is_file():
        audit = json.loads(args.audit.read_text(encoding="utf-8"))
        if audit.get("contract"):
            contract = audit["contract"]

    teachers = list(contract.get("teachers") or DEFAULT_TEACHERS)
    canonical = {}
    if audit:
        for k, v in (audit.get("canonical_teacher_versions") or {}).items():
            canonical[k] = v.get("model_version")

    if args.from_jsonl:
        rows = []
        with args.from_jsonl.open(encoding="utf-8") as fh:
            for line in fh:
                if line.strip():
                    rows.append(json.loads(line))
    else:
        rows = _rows_from_db(teachers, canonical, limit=args.limit)

    dest = export_from_rows(rows, contract=contract, audit=audit, seed=args.seed)
    print(json.dumps({"manifest_dir": str(dest)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

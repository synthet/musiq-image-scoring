"""Finalize *phantom-scored* images.

A "phantom-scored" image is one whose per-model rows already exist in
``image_model_scores`` (the ML inference ran and succeeded) but whose composite
``images.score_general`` was never written and whose ``scoring`` phase row is not
terminal-complete. This happens when a scoring job is interrupted **between**
``ScoringWorker`` (which persists the per-model rows) and the ``ResultWorker`` finalize
step (``upsert_image`` writing ``score_general`` + ``set_image_phase_status(DONE)``).

The result is a self-perpetuating wedge:
  * ``is_image_scoring_complete()`` returns True (per-model rows exist), so the JIT
    re-planner sees *no scoring work* and skips the phase, and
  * the folder bucketer reads ``image_phase_status = not_started`` and keeps
    re-bucketing the folder as ``awaiting_scoring`` — auto-drive re-enqueues it
    forever while never actually finalizing anything.

This module recomputes the composite (``score_general`` / ``score_technical`` /
``score_aesthetic`` / ``rating`` / ``label``) **from the already-stored model rows**
— no re-inference — and flips the scoring phase to ``done``. It is the missing
companion to :func:`modules.db.reconcile_phantom_complete_image_phases`, which only
flips the phase status and never backfills the composite columns.
"""
from __future__ import annotations

import logging
from typing import Any, Optional, Sequence

from modules import db
from modules import score_normalization as snorm

logger = logging.getLogger(__name__)


def _scope_clause(scope_path: Optional[str]) -> tuple[str, tuple]:
    """Return (sql_fragment, params) restricting to a folder subtree, or ("", ())."""
    if not scope_path or not str(scope_path).strip():
        return "", ()
    from modules import utils

    wsl = utils.convert_path_to_wsl(scope_path) if hasattr(utils, "convert_path_to_wsl") else scope_path
    target = wsl or scope_path
    return " AND (f.path = ? OR f.path LIKE ? OR f.path LIKE ?)", (target, target + "/%", target + "\\%")


def _find_candidates(
    scope_path: Optional[str],
    image_ids: Optional[Sequence[int]],
    limit: int,
) -> list[dict[str, Any]]:
    """Images that are scoring-*complete* (per-model rows present) but not finalized:
    either ``score_general IS NULL`` or the scoring phase row is not ``done``/``skipped``."""
    incomplete_sql = db.get_phase_incomplete_sql("scoring", "i")
    if image_ids:
        ids = [int(i) for i in image_ids if i is not None]
        if not ids:
            return []
        placeholders = ",".join("?" for _ in ids)
        sql = f"""
            SELECT i.id, i.score_general, ips.status AS scoring_status
            FROM images i
            LEFT JOIN pipeline_phases pp ON LOWER(TRIM(pp.code)) = 'scoring'
            LEFT JOIN image_phase_status ips ON ips.image_id = i.id AND ips.phase_id = pp.id
            WHERE i.id IN ({placeholders})
              AND NOT ({incomplete_sql})
        """
        rows = db.get_connector().query(sql, tuple(ids))
        return [dict(r) for r in rows or []]

    scope_frag, scope_params = _scope_clause(scope_path)
    sql = f"""
        SELECT i.id, i.score_general, ips.status AS scoring_status
        FROM images i
        JOIN folders f ON f.id = i.folder_id
        LEFT JOIN pipeline_phases pp ON LOWER(TRIM(pp.code)) = 'scoring'
        LEFT JOIN image_phase_status ips ON ips.image_id = i.id AND ips.phase_id = pp.id
        WHERE NOT ({incomplete_sql})
          AND (
              i.score_general IS NULL
              OR ips.status IS NULL
              OR LOWER(TRIM(ips.status)) NOT IN ('done', 'skipped')
          ){scope_frag}
        FETCH FIRST ? ROWS ONLY
    """
    rows = db.get_connector().query(sql, scope_params + (max(1, int(limit)),))
    return [dict(r) for r in rows or []]


def _model_scores_by_image(image_ids: Sequence[int]) -> dict[int, dict[str, float]]:
    """Production (non-shadow) normalized model scores keyed by image_id then model."""
    ids = [int(i) for i in image_ids if i is not None]
    if not ids:
        return {}
    placeholders = ",".join("?" for _ in ids)
    rows = db.get_connector().query(
        f"""
        SELECT image_id, model_name, normalized, raw_score
        FROM image_model_scores
        WHERE image_id IN ({placeholders})
          AND status = 'success'
          AND is_shadow = FALSE
        """,
        tuple(ids),
    )
    out: dict[int, dict[str, float]] = {}
    for r in rows or []:
        iid = r["image_id"]
        # Fusion anchors operate on the normalized 0-1 value; fall back to raw_score
        # only if normalized is absent (older rows).
        val = r.get("normalized")
        if val is None:
            val = r.get("raw_score")
        if val is None:
            continue
        out.setdefault(iid, {})[str(r["model_name"]).strip().lower()] = float(val)
    return out


def finalize_phantom_scores(
    *,
    scope_path: Optional[str] = None,
    image_ids: Optional[Sequence[int]] = None,
    dry_run: bool = True,
    limit: int = 5000,
) -> dict[str, Any]:
    """Backfill composite scores from stored per-model rows and finalize the scoring phase.

    For each phantom candidate: recompute ``score_general``/``score_technical``/
    ``score_aesthetic``/``rating``/``label`` via :func:`score_normalization.compute_all`
    (only writing composites when ``score_general`` is currently NULL), then flip the
    ``scoring`` phase to ``done``.

    Returns a summary dict: ``candidates``, ``composites_backfilled``, ``phase_finalized``,
    ``no_model_scores``, ``dry_run``, and a small ``samples`` list.
    """
    candidates = _find_candidates(scope_path, image_ids, limit)
    summary: dict[str, Any] = {
        "candidates": len(candidates),
        "composites_backfilled": 0,
        "phase_finalized": 0,
        "no_model_scores": 0,
        "dry_run": bool(dry_run),
        "samples": [],
    }
    if not candidates:
        return summary

    ids = [c["id"] for c in candidates]
    scores_by_image = _model_scores_by_image(ids)
    conn = db.get_connector()

    for cand in candidates:
        iid = cand["id"]
        model_scores = scores_by_image.get(iid)
        if not model_scores:
            # Should not happen (candidates are scoring-complete) but guard anyway.
            summary["no_model_scores"] += 1
            continue

        needs_composite = cand.get("score_general") is None
        computed = None
        if needs_composite:
            computed = snorm.compute_all(model_scores)
            if not dry_run:
                conn.execute(
                    "UPDATE images SET score_general = ?, score_aesthetic = ?, "
                    "score_technical = ?, rating = ?, label = ? WHERE id = ?",
                    (
                        computed["general"],
                        computed["aesthetic"],
                        computed["technical"],
                        computed["rating"],
                        computed["label"],
                        iid,
                    ),
                )
            summary["composites_backfilled"] += 1

        # Flip the scoring phase to done (mirrors reconcile_phantom_complete_image_phases).
        if not dry_run:
            try:
                db.set_image_phase_status(iid, "scoring", "done")
            except Exception:
                logger.debug("finalize_phantom_scores: phase flip failed for image %s", iid, exc_info=True)
        summary["phase_finalized"] += 1

        if len(summary["samples"]) < 10:
            summary["samples"].append({
                "image_id": iid,
                "was_score_general_null": needs_composite,
                "score_general": (computed or {}).get("general") if needs_composite else cand.get("score_general"),
                "prev_phase_status": cand.get("scoring_status"),
            })

    logger.info(
        "finalize_phantom_scores: scope=%s candidates=%d composites=%d phase=%d (dry_run=%s)",
        scope_path or f"ids[{len(ids)}]",
        summary["candidates"],
        summary["composites_backfilled"],
        summary["phase_finalized"],
        dry_run,
    )
    return summary

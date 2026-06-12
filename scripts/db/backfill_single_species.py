"""Reconcile images that carry more than one ``species:`` keyword down to one.

Earlier bird-species runs stored the top-``top_k`` (default 3) species per bird
image. The pipeline now keeps only the single highest-scoring species (BioCLIP
argmax, ``top_k=1``). This script brings *existing* data in line: for every image
with more than one ``species:`` keyword, it keeps the one with the highest
``image_keywords.confidence`` (the stored BioCLIP softmax probability) and removes
the rest.

Both the normalized ``image_keywords`` rows **and** the legacy ``images.keywords``
CSV are updated in the same transaction so the two representations stay in sync
(see ``modules.db_legacy._sync_image_keywords``).

Safety:

- Images whose top two species share the same confidence (or whose confidences
  are all unset / equal) are **skipped and logged** — there is no defensible
  winner, so nothing is deleted. Re-run the bird-species phase with
  ``overwrite=true`` to resolve those from the image instead.
- ``--dry-run`` reports exactly what would change and writes nothing.
- Only ``species:`` keywords are ever touched; general keywords and the
  ``birds:species-exhausted`` marker are left alone.

Postgres only (the canonical gallery/backend engine). Run from the repo root:

    python -m scripts.db.backfill_single_species --dry-run
    python -m scripts.db.backfill_single_species            # apply

The job is idempotent: once an image has a single ``species:`` keyword it no
longer matches the candidate query, so re-running after an interruption is safe.
"""

from __future__ import annotations

import argparse
import logging
import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from modules import db  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

# Confidences within this margin are treated as a tie (no defensible winner).
TIE_EPS = 1e-6
ID_CHUNK = 1000


def _conflicting_image_ids(limit: int | None) -> list[int]:
    """Image ids that have more than one ``species:`` keyword, ordered by id."""
    from modules import db_postgres

    where_limit = ""
    params: tuple = ()
    if limit and limit > 0:
        where_limit = "LIMIT %s"
        params = (int(limit),)

    rows = db_postgres.execute_select(
        f"""
        SELECT ik.image_id AS image_id
        FROM image_keywords ik
        JOIN keywords_dim kd ON kd.keyword_id = ik.keyword_id
        WHERE kd.keyword_norm LIKE 'species:%%'
        GROUP BY ik.image_id
        HAVING COUNT(*) > 1
        ORDER BY ik.image_id
        {where_limit}
        """,
        params,
    )
    return [int(r["image_id"]) for r in rows]


def _species_rows(image_ids: list[int]) -> dict[int, list[dict]]:
    """Map image_id -> list of its species keyword rows (id, norm, display, confidence)."""
    from modules import db_postgres

    out: dict[int, list[dict]] = {}
    for start in range(0, len(image_ids), ID_CHUNK):
        chunk = image_ids[start : start + ID_CHUNK]
        placeholders = ",".join(["%s"] * len(chunk))
        rows = db_postgres.execute_select(
            f"""
            SELECT ik.image_id        AS image_id,
                   ik.keyword_id      AS keyword_id,
                   ik.confidence      AS confidence,
                   kd.keyword_display AS keyword_display,
                   kd.keyword_norm    AS keyword_norm
            FROM image_keywords ik
            JOIN keywords_dim kd ON kd.keyword_id = ik.keyword_id
            WHERE ik.image_id IN ({placeholders})
              AND kd.keyword_norm LIKE 'species:%%'
            """,
            tuple(int(x) for x in chunk),
        )
        for r in rows:
            out.setdefault(int(r["image_id"]), []).append(r)
    return out


def _existing_csv(image_ids: list[int]) -> dict[int, str | None]:
    """Map image_id -> current ``images.keywords`` CSV (or None)."""
    from modules import db_postgres

    out: dict[int, str | None] = {}
    for start in range(0, len(image_ids), ID_CHUNK):
        chunk = image_ids[start : start + ID_CHUNK]
        placeholders = ",".join(["%s"] * len(chunk))
        rows = db_postgres.execute_select(
            f"SELECT id, keywords FROM images WHERE id IN ({placeholders})",
            tuple(int(x) for x in chunk),
        )
        for r in rows:
            out[int(r["id"])] = r["keywords"]
    return out


def _csv_without(csv: str | None, drop_norms: set[str]) -> str | None:
    """Return the CSV with any entry whose lowercased form is in ``drop_norms`` removed."""
    if not csv:
        return csv
    kept = [k for k in (p.strip() for p in csv.split(",")) if k and k.lower() not in drop_norms]
    return ",".join(kept)


def run(dry_run: bool = False, limit: int | None = None) -> None:
    if db._get_db_engine() != "postgres":  # noqa: SLF001 — engine probe
        logger.error("This backfill requires the Postgres engine.")
        return

    image_ids = _conflicting_image_ids(limit)
    logger.info("Images with >1 species: keyword: %d", len(image_ids))
    if not image_ids:
        return

    species_by_image = _species_rows(image_ids)
    csv_by_image = _existing_csv(image_ids)

    # plan: image_id -> (loser_keyword_ids, new_csv, winner_display)
    plan: list[tuple[int, list[int], str | None, str]] = []
    skipped_tie = 0
    removed_total = 0

    for iid in image_ids:
        rows = species_by_image.get(iid, [])
        if len(rows) < 2:
            continue  # changed under us / already reconciled

        def _conf(r: dict) -> float:
            try:
                return float(r["confidence"]) if r["confidence"] is not None else 0.0
            except (TypeError, ValueError):
                return 0.0

        ordered = sorted(rows, key=_conf, reverse=True)
        if _conf(ordered[0]) - _conf(ordered[1]) <= TIE_EPS:
            skipped_tie += 1
            logger.debug(
                "image_id=%s skipped (tie): %s",
                iid,
                ", ".join(f"{r['keyword_display']}={_conf(r):.4f}" for r in ordered),
            )
            continue

        winner = ordered[0]
        losers = ordered[1:]
        loser_ids = [int(r["keyword_id"]) for r in losers]
        loser_norms = {str(r["keyword_norm"]).lower() for r in losers}
        new_csv = _csv_without(csv_by_image.get(iid), loser_norms)
        plan.append((iid, loser_ids, new_csv, str(winner["keyword_display"])))
        removed_total += len(loser_ids)

    logger.info(
        "Plan: %d images to reconcile, %d species rows to remove, %d skipped (tie/unset confidence). dry_run=%s",
        len(plan), removed_total, skipped_tie, dry_run,
    )
    if dry_run or not plan:
        for iid, loser_ids, _csv, winner in plan[:20]:
            logger.info("  image_id=%s keep '%s', drop %d species row(s)", iid, winner, len(loser_ids))
        return

    written = 0
    for start in range(0, len(plan), 200):
        chunk = plan[start : start + 200]

        def _tx(tx, _chunk=chunk):
            for iid, loser_ids, new_csv, _winner in _chunk:
                for kid in loser_ids:
                    tx.execute(
                        "DELETE FROM image_keywords WHERE image_id = ? AND keyword_id = ?",
                        (iid, kid),
                    )
                if csv_by_image.get(iid) is not None:
                    tx.execute("UPDATE images SET keywords = ? WHERE id = ?", (new_csv, iid))

        db.get_connector().run_transaction(_tx)
        written += len(chunk)
        logger.info("Reconciled %d / %d images ...", written, len(plan))

    logger.info("Backfill complete. Reconciled %d images, removed %d species rows.", written, removed_total)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry-run", action="store_true", help="Report changes without writing.")
    ap.add_argument("--limit", type=int, default=None, help="Cap candidate images (testing).")
    args = ap.parse_args()
    run(dry_run=args.dry_run, limit=args.limit)


if __name__ == "__main__":
    main()

"""Load boxed images from production and group them into EXIF-capture bursts.

Burst grouping is the study's one piece of **unbiased** ground truth. Unlike
``images.rating`` / ``label`` / ``pick_status`` / ``cull_decision`` — all of which
are computed by the scoring pipeline itself (``modules/pipeline.py:652``,
``modules/selection_policy.py:89``) and are therefore circular for evaluating a
new signal — capture timestamps come from the camera.

Gap semantics match ``scripts/research/clip_culling/experiments.py:_exif_burst_groups``
(2.0 s default) so results are comparable with the input-size study. Grouping is
applied *per folder*, since a burst never spans a shoot.
"""

from __future__ import annotations

import logging
from typing import Optional, Sequence

from scripts.research.bird_crop import prod

logger = logging.getLogger("bird_crop.bursts")

#: Max seconds between consecutive frames for them to count as one burst.
DEFAULT_GAP_SECONDS = 2.0

#: Selected for every study step. ``bird_bbox`` arrives as a dict (jsonb), and the
#: derived-label columns are carried so the bias probe can measure how the
#: *existing* stack responds to subject geometry — never as accuracy ground truth.
_SQL_BOXED = """
SELECT i.id,
       i.folder_id,
       f.path            AS folder_path,
       i.file_path,
       i.thumbnail_path,
       i.thumbnail_path_win,
       i.bird_bbox,
       i.rating,
       i.label,
       i.pick_status,
       i.cull_decision,
       i.score_general,
       i.score_technical,
       i.score_aesthetic,
       i.stack_id,
       e.date_time_original
FROM images i
JOIN folders f ON f.id = i.folder_id
JOIN image_exif e ON e.image_id = i.id
WHERE jsonb_exists(i.bird_bbox, 'x1')
  AND e.date_time_original IS NOT NULL
"""


def load_boxed_rows(
    *,
    folders: Optional[Sequence[int]] = None,
    limit: int = 0,
    image_ids: Optional[Sequence[int]] = None,
) -> list[dict]:
    """Return production rows that have a real bird box and a capture timestamp.

    ``folders`` restricts to specific ``folder_id`` values (the input-size study
    uses ``62,44,45,676``); omit for the whole library.

    ``image_ids`` pins the population to an explicit list instead, so every track
    measures the same images. It replaces folder/limit selection rather than
    narrowing it — sampling a pinned set would reintroduce exactly the drift the
    pin exists to prevent. See ``scripts/research/bird_crop/pin_study_set.py``.
    """
    if image_ids is not None:
        return _load_pinned_rows(image_ids, folders=folders, limit=limit)

    sql = _SQL_BOXED
    params: list = []
    if folders:
        sql += " AND i.folder_id = ANY(%s)"
        params.append(list(folders))
    sql += " ORDER BY i.folder_id, e.date_time_original, i.id"
    if limit and limit > 0:
        sql += " LIMIT %s"
        params.append(int(limit))

    rows = prod.select(sql, params or None)
    logger.info("Loaded %d boxed image(s) from production.", len(rows))
    return rows


def _load_pinned_rows(
    image_ids: Sequence[int],
    *,
    folders: Optional[Sequence[int]],
    limit: int,
) -> list[dict]:
    """Load exactly *image_ids*, or fail saying which ones the query dropped.

    Silently returning fewer rows than were pinned is the failure mode that made
    the first sweep's four runs incomparable, so a short result is an error here
    rather than a smaller study. Two clauses in ``_SQL_BOXED`` can drop a pinned
    id — the ``bird_bbox`` filter and the ``image_exif`` join — and the message
    names both, because which one fired changes the fix.
    """
    if folders:
        raise SystemExit(
            "--image-ids-file and --folders are mutually exclusive: the pinned list "
            "already names its images, and intersecting it with a folder scope would "
            "measure a different population than the other tracks."
        )
    if limit and limit > 0:
        raise SystemExit(
            "--image-ids-file and --limit are mutually exclusive: the pinned list *is* "
            "the population, and sub-sampling it would reintroduce the drift the pin "
            "exists to prevent."
        )

    wanted = sorted(set(int(i) for i in image_ids))
    sql = (
        _SQL_BOXED
        + " AND i.id = ANY(%s) ORDER BY i.folder_id, e.date_time_original, i.id"
    )
    rows = prod.select(sql, [wanted])

    missing = sorted(set(wanted) - {r["id"] for r in rows})
    if missing:
        raise SystemExit(
            f"{len(missing)} pinned image id(s) did not survive the boxed+EXIF query "
            f"(e.g. {missing[:10]}). Either the bird box is gone or "
            "image_exif.date_time_original is NULL for them; burst grouping needs "
            "both. Re-generate the pinned set with "
            "`python -m scripts.research.bird_crop.pin_study_set --force`."
        )
    logger.info("Loaded %d pinned boxed image(s) from production.", len(rows))
    return rows


def group_bursts(
    rows: Sequence[dict],
    *,
    gap_seconds: float = DEFAULT_GAP_SECONDS,
) -> dict[int, int]:
    """Map ``image_id -> burst_id`` from capture-time gaps, per folder.

    Burst ids are unique across the whole result, so callers can pool folders
    without collisions.
    """
    by_folder: dict[int, list[dict]] = {}
    for r in rows:
        if r.get("date_time_original") is None:
            continue
        by_folder.setdefault(r["folder_id"], []).append(r)

    labels: dict[int, int] = {}
    next_id = 0
    for _folder_id, frames in sorted(by_folder.items()):
        frames = sorted(frames, key=lambda r: (r["date_time_original"], r["id"]))
        labels[frames[0]["id"]] = next_id
        for prev, cur in zip(frames, frames[1:]):
            delta = (cur["date_time_original"] - prev["date_time_original"]).total_seconds()
            if delta > gap_seconds:
                next_id += 1
            labels[cur["id"]] = next_id
        next_id += 1

    return labels


def bursts_by_id(
    rows: Sequence[dict],
    burst_of: dict[int, int],
    *,
    min_size: int = 3,
    max_size: int = 8,
) -> dict[int, list[dict]]:
    """Group rows into ``burst_id -> [rows]``, keeping only bursts within size bounds.

    The size window matters for labelling: fewer than *min_size* frames gives no
    meaningful within-burst ranking, and more than *max_size* makes a single
    side-by-side comparison too large to judge reliably.
    """
    grouped: dict[int, list[dict]] = {}
    for r in rows:
        bid = burst_of.get(r["id"])
        if bid is None:
            continue
        grouped.setdefault(bid, []).append(r)

    kept = {
        bid: sorted(frames, key=lambda r: (r["date_time_original"], r["id"]))
        for bid, frames in grouped.items()
        if min_size <= len(frames) <= max_size
    }
    logger.info(
        "Grouped %d image(s) into %d burst(s); %d within size %d-%d.",
        len(rows), len(grouped), len(kept), min_size, max_size,
    )
    return kept

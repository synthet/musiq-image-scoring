"""
Canonical quality tie-break ordering after the primary score column.

Used by stack ordering SQL, best_image_id recompute, clustering representative
(score strategy), and selection sort keys. Keep ``quality_tiebreak_order_sql``
aligned with the Electron mirror in image-scoring-gallery ``electron/db.ts``.
"""

from __future__ import annotations

from typing import Any, Mapping


def parse_exposure_seconds(value: Any) -> float | None:
    """
    Parse exposure_time from EXIF (often ``\"1/250\"`` or a decimal string) to seconds.

    Returns:
        Seconds as float, or ``None`` if missing / unparsable (sorts last in tie-break).
    """
    if value is None:
        return None
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        try:
            sec = float(value)
        except (TypeError, ValueError):
            return None
        return sec if sec >= 0 else None
    s = str(value).strip()
    if not s:
        return None
    if "/" in s:
        parts = s.split("/", 1)
        if len(parts) != 2:
            return None
        try:
            num = float(parts[0].strip())
            den = float(parts[1].strip())
        except (TypeError, ValueError):
            return None
        if den == 0:
            return None
        out = num / den
        return out if out >= 0 else None
    try:
        sec = float(s)
    except ValueError:
        return None
    return sec if sec >= 0 else None


def quality_tiebreak_order_sql(
    *, exif_alias: str = "e", images_alias: str = "i", dialect: str = "postgres"
) -> str:
    """
    SQL fragment (starts with comma) for ORDER BY after the primary sort expression.

    **postgres** — full order: ISO ASC NULLS LAST, exposure seconds ASC NULLS LAST,
    ``date_time_original`` ASC NULLS LAST, image id ASC.

    **firebird** (legacy ``.fdb``) — ISO + id only; exposure parsing uses Postgres-only
    ``SPLIT_PART`` and is omitted so the same Python callers work on both engines.
    """
    ex = exif_alias
    im = images_alias
    if dialect != "postgres":
        return f", {ex}.iso ASC NULLS LAST, {im}.id ASC"
    return (
        f", {ex}.iso ASC NULLS LAST\n"
        f", CASE\n"
        f"    WHEN {ex}.exposure_time IS NULL THEN NULL\n"
        f"    WHEN POSITION('/' IN {ex}.exposure_time) > 0\n"
        f"      THEN CAST(SPLIT_PART({ex}.exposure_time, '/', 1) AS DOUBLE PRECISION)\n"
        f"         / NULLIF(CAST(SPLIT_PART({ex}.exposure_time, '/', 2) AS DOUBLE PRECISION), 0)\n"
        f"    ELSE CAST({ex}.exposure_time AS DOUBLE PRECISION)\n"
        f"  END ASC NULLS LAST\n"
        f", {ex}.date_time_original ASC NULLS LAST\n"
        f", {im}.id ASC"
    )


def quality_tiebreak_sort_key_best_first(row: Mapping[str, Any]) -> tuple:
    """
    Tuple for sorting images so the *best* tie-break candidate sorts *first*
    (smallest key under ascending ``sorted``).

    Reads ``iso``, ``exposure_time``, ``date_time_original``, ``id`` (or ``image_id``).
    """
    iso = row.get("iso")
    if iso is None:
        t_iso = (1, 0)
    else:
        try:
            t_iso = (0, int(iso))
        except (TypeError, ValueError):
            t_iso = (1, 0)

    exp_sec = parse_exposure_seconds(row.get("exposure_time"))
    if exp_sec is None:
        t_exp = (1, float("inf"))
    else:
        t_exp = (0, float(exp_sec))

    dto = row.get("date_time_original")
    if dto is not None and str(dto).strip():
        t_dto = (0, str(dto).strip())
    else:
        t_dto = (1, "\uffff")

    img_id = row.get("id")
    if img_id is None:
        img_id = row.get("image_id")
    try:
        iid = int(img_id) if img_id is not None else 0
    except (TypeError, ValueError):
        iid = 0
    return (t_iso, t_exp, t_dto, (0, iid))

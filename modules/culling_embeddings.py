"""Just-in-time culling-tower embeddings for two-level culling.

When ``culling.two_level.enabled`` is true, ``SelectionService`` calls
``ensure_embeddings_for_space`` for stacked images missing the configured
level-2 space before sub-stack assignment. Bulk library backfill remains
available via ``scripts/backfill_culling_embeddings.py``.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Callable, Iterable, List, Mapping, Sequence, Tuple

logger = logging.getLogger(__name__)

# Below this fraction of requested IDs with vectors after ensure, log a warning.
LOW_COVERAGE_WARN = 0.90

ProgressCb = Callable[[str], None]


@dataclass(frozen=True)
class EnsureResult:
    """Outcome of ``ensure_embeddings_for_space``."""

    space_code: str
    requested: int
    missing_before: int
    persisted: int
    covered_after: int

    @property
    def coverage_ratio(self) -> float:
        if self.requested <= 0:
            return 1.0
        return self.covered_after / self.requested


def collect_stacked_image_ids(by_stack: Mapping[object, Sequence[Mapping]]) -> List[int]:
    """Image IDs in multi-image stacks (level-2 sub-clustering scope)."""
    ids: List[int] = []
    for stack_id, group in by_stack.items():
        if stack_id is None or len(group) < 2:
            continue
        for img in group:
            try:
                ids.append(int(img["id"]))
            except (KeyError, TypeError, ValueError):
                continue
    return ids


def resolve_embedding_paths(
    rows: Sequence[Mapping | tuple],
    *,
    use_thumbnails: bool = True,
) -> Tuple[List[Tuple[int, str]], int]:
    """Return ``(image_id, local_path)`` pairs; prefer on-disk thumbnails when set."""
    from modules import utils

    resolved: List[Tuple[int, str]] = []
    n_thumb = 0
    for row in rows:
        if isinstance(row, dict):
            image_id = int(row["id"])
            file_path = str(row.get("file_path") or "")
            thumb = str(row.get("thumbnail_path") or "")
            thumb_win = row.get("thumbnail_path_win")
        else:
            image_id = int(row[0])
            file_path = str(row[1])
            thumb = str(row[2]) if len(row) > 2 else ""
            thumb_win = row[3] if len(row) > 3 else None

        path = file_path
        if use_thumbnails:
            for candidate in (thumb, thumb_win):
                if not candidate:
                    continue
                local_thumb = utils.convert_path_to_local(str(candidate))
                if os.path.exists(local_thumb):
                    path = str(candidate)
                    n_thumb += 1
                    break
        resolved.append((image_id, utils.convert_path_to_local(path)))
    return resolved, n_thumb


def ensure_embeddings_for_space(
    space_code: str,
    image_ids: Iterable[int],
    *,
    batch_size: int = 32,
    use_thumbnails: bool = True,
    device: str | None = None,
    fp16: bool = True,
    progress_cb: ProgressCb | None = None,
) -> EnsureResult:
    """Embed missing vectors for ``image_ids`` and persist when Postgres is active."""
    from modules import db
    from modules.embedding_extractors import (
        CullingEmbedder,
        generate_and_persist,
        is_supported,
    )

    ids = sorted({int(i) for i in image_ids})
    if not ids:
        return EnsureResult(space_code, 0, 0, 0, 0)

    if not is_supported(space_code):
        logger.warning(
            "[culling] level2 space %r is not a culling tower; skipping JIT embed",
            space_code,
        )
        return EnsureResult(space_code, len(ids), len(ids), 0, 0)

    if db._get_db_engine() != "postgres":
        logger.debug(
            "[culling] JIT embed for %r skipped (engine=%s)",
            space_code,
            db._get_db_engine(),
        )
        return EnsureResult(space_code, len(ids), len(ids), 0, 0)

    missing_rows = db.get_images_missing_embedding_for_space(
        space_code,
        image_ids=ids,
    )
    missing_before = len(missing_rows)
    if missing_before == 0:
        return EnsureResult(space_code, len(ids), 0, 0, len(ids))

    if progress_cb:
        progress_cb(
            f"Generating {space_code} embeddings for {missing_before} stacked image(s)..."
        )
    logger.info(
        "[culling] level2 ensure space=%s missing=%d of %d stacked ids",
        space_code,
        missing_before,
        len(ids),
    )

    local_rows, n_thumb = resolve_embedding_paths(missing_rows, use_thumbnails=use_thumbnails)
    logger.info(
        "[culling] level2 load paths: %d via thumbnail, %d via original",
        n_thumb,
        len(local_rows) - n_thumb,
    )

    embedder = CullingEmbedder(space_code, device=device, fp16=fp16)
    persisted = 0
    try:
        persisted = generate_and_persist(
            space_code,
            local_rows,
            batch_size=batch_size,
            embedder=embedder,
        )
    finally:
        embedder.unload()

    covered = db.get_image_embeddings_batch_for_space(space_code, ids)
    covered_after = len(covered)
    ratio = covered_after / len(ids) if ids else 1.0
    logger.info(
        "[culling] level2 ensure space=%s persisted=%d coverage=%d/%d (%.1f%%)",
        space_code,
        persisted,
        covered_after,
        len(ids),
        100.0 * ratio,
    )
    if ratio < LOW_COVERAGE_WARN:
        logger.warning(
            "[culling] level2 %s coverage %.1f%% below %.0f%% after ensure "
            "(%d/%d stacked images have vectors)",
            space_code,
            100.0 * ratio,
            100.0 * LOW_COVERAGE_WARN,
            covered_after,
            len(ids),
        )

    return EnsureResult(
        space_code=space_code,
        requested=len(ids),
        missing_before=missing_before,
        persisted=persisted,
        covered_after=covered_after,
    )

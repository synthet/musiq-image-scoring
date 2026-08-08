"""Load and validate the within-burst label set.

Human verdicts are the study's only *non-circular* quality ground truth. The
multi-agent labelling harness can also fill this file; in that case a UUID-stamped
``label_set_judges-*.json`` sidecar marks the verdicts as ``agent-derived`` and
reports must not call them human. Everything the DB offers — ``rating``, ``label``,
``pick_status``, ``cull_decision`` — is computed by the scoring pipeline from the
very models under test.

Labelling is deliberately **within-burst and comparative**: for each burst the
labeller marks which frame(s) they would keep, rather than scoring frames on an
absolute scale. Comparative judgement inside a burst is both far more reliable
and exactly what culling needs.

CSV contract (``reports/bird-crop/labels/label_set.csv``)
--------------------------------------------------------
=====================  ==================================================
``image_id``           production ``images.id`` — the only join key
``burst_id``           study-local burst grouping id
``area_frac_tercile``  1 (smallest subjects) .. 3 (largest)
``frame_index``        position within the burst, 1-based
``verdict``            ``best`` | ``good`` | ``reject`` — **you fill this in**
=====================  ==================================================

No file paths are stored in the committed CSV; resolve them from ``image_id``.
"""

from __future__ import annotations

import csv
import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

from scripts.research.bird_crop import prod

logger = logging.getLogger("bird_crop.labels")

LABEL_CSV = prod.LABELS_DIR / "label_set.csv"
PROVENANCE_GLOB = "label_set_judges-*.json"

#: ``best`` = would keep this one; ``good`` = acceptable but not the pick;
#: ``reject`` = would delete. Ordered worst -> best for ranking metrics.
VERDICTS = ("reject", "good", "best")
VERDICT_RANK = {v: i for i, v in enumerate(VERDICTS)}

FIELDNAMES = ("image_id", "burst_id", "area_frac_tercile", "frame_index", "verdict")


def ground_truth_provenance(path: Path = LABEL_CSV) -> dict[str, Any]:
    """Describe who supplied the current verdicts.

    A UUID-stamped judge sidecar is authoritative when present. Without one the
    historical/manual workflow remains human-labelled. Corrupt sidecars are
    skipped with a warning rather than making the label CSV unloadable.
    """
    candidates = sorted(
        path.parent.glob(PROVENANCE_GLOB),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    for sidecar in candidates:
        try:
            with open(sidecar, encoding="utf-8-sig") as f:
                payload = json.load(f)
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("Could not read label provenance %s: %s", sidecar, exc)
            continue
        if payload.get("ground_truth_kind") == "agent-derived":
            return {
                "kind": "agent-derived",
                "description": (
                    "agent-derived within-burst verdicts "
                    "(vision-LLM consensus; not human)"
                ),
                "sidecar": sidecar.name,
            }
    return {
        "kind": "human",
        "description": "human within-burst verdicts (non-circular)",
        "sidecar": None,
    }


@dataclass(frozen=True)
class LabelRow:
    image_id: int
    burst_id: int
    area_frac_tercile: int
    frame_index: int
    verdict: str

    @property
    def rank(self) -> int:
        """Ordinal quality, higher is better — for rank-correlation metrics."""
        return VERDICT_RANK[self.verdict]


class LabelSetError(RuntimeError):
    """Raised when the label CSV is missing, malformed, or incompletely filled."""


def write_template(rows: list[dict], path: Path = LABEL_CSV) -> Path:
    """Write an unlabelled template CSV. Refuses to clobber existing verdicts."""
    if path.exists():
        try:
            existing = load(path, require_complete=False)
        except LabelSetError:
            existing = []
        if any(r.verdict for r in existing):
            raise LabelSetError(
                f"{path} already contains verdicts; refusing to overwrite. "
                "Move or delete it first if you really mean to resample."
            )
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()
        for r in rows:
            writer.writerow({k: r.get(k, "") for k in FIELDNAMES})
    logger.info("Wrote %s (%d rows to label)", path, len(rows))
    return path


def load(path: Path = LABEL_CSV, *, require_complete: bool = True) -> list[LabelRow]:
    """Read the label CSV.

    With ``require_complete`` (the default) every row must carry a valid verdict
    and every burst must have at least one ``best`` — so a half-filled sheet fails
    loudly instead of silently shrinking the evaluation set.
    """
    if not path.exists():
        raise LabelSetError(
            f"No label set at {path}. Run "
            "`python -m scripts.research.bird_crop.build_label_set` first."
        )

    out: list[LabelRow] = []
    with open(path, encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        missing_cols = set(FIELDNAMES) - set(reader.fieldnames or ())
        if missing_cols:
            raise LabelSetError(f"{path} is missing column(s): {sorted(missing_cols)}")
        for lineno, raw in enumerate(reader, start=2):
            verdict = (raw.get("verdict") or "").strip().lower()
            if verdict and verdict not in VERDICT_RANK:
                raise LabelSetError(
                    f"{path}:{lineno}: verdict {verdict!r} not one of {list(VERDICTS)}"
                )
            try:
                out.append(
                    LabelRow(
                        image_id=int(raw["image_id"]),
                        burst_id=int(raw["burst_id"]),
                        area_frac_tercile=int(raw["area_frac_tercile"]),
                        frame_index=int(raw["frame_index"]),
                        verdict=verdict,
                    )
                )
            except (TypeError, ValueError) as exc:
                raise LabelSetError(f"{path}:{lineno}: bad numeric field ({exc})") from exc

    if require_complete:
        _assert_complete(out, path)
    labelled = sum(1 for r in out if r.verdict)
    logger.info("Loaded %d label row(s) from %s (%d labelled).", len(out), path, labelled)
    return out


def _assert_complete(rows: list[LabelRow], path: Path) -> None:
    blank = [r.image_id for r in rows if not r.verdict]
    if blank:
        raise LabelSetError(
            f"{path}: {len(blank)} row(s) still unlabelled "
            f"(e.g. image_id {blank[:5]}). Fill in the 'verdict' column."
        )
    by_burst: dict[int, list[LabelRow]] = {}
    for r in rows:
        by_burst.setdefault(r.burst_id, []).append(r)
    no_best = [bid for bid, frames in by_burst.items() if not any(f.verdict == "best" for f in frames)]
    if no_best:
        raise LabelSetError(
            f"{path}: {len(no_best)} burst(s) have no 'best' frame (e.g. {no_best[:5]}). "
            "Every burst needs at least one keeper so top-1 accuracy is defined."
        )
    ties = [bid for bid, frames in by_burst.items() if sum(f.verdict == "best" for f in frames) > 1]
    if ties:
        logger.info(
            "%d burst(s) have multiple 'best' frames; top-1 metrics will count a hit "
            "if the model picks any of them.", len(ties),
        )


def by_burst(rows: list[LabelRow]) -> dict[int, list[LabelRow]]:
    """Group label rows into ``burst_id -> [rows]``, ordered by frame index."""
    grouped: dict[int, list[LabelRow]] = {}
    for r in rows:
        grouped.setdefault(r.burst_id, []).append(r)
    return {bid: sorted(v, key=lambda r: r.frame_index) for bid, v in grouped.items()}


def best_ids(rows: list[LabelRow]) -> dict[int, set[int]]:
    """``burst_id -> {image_id}`` of frames marked ``best``."""
    out: dict[int, set[int]] = {}
    for r in rows:
        if r.verdict == "best":
            out.setdefault(r.burst_id, set()).add(r.image_id)
    return out


def try_load(path: Path = LABEL_CSV) -> Optional[list[LabelRow]]:
    """Load a complete label set, or return ``None`` if it is absent/incomplete.

    Lets the geometry study run its label-free bias probe before any labelling
    has happened, then pick the labels up automatically once they exist.
    """
    try:
        return load(path, require_complete=True)
    except LabelSetError as exc:
        logger.warning("Within-burst label set unavailable: %s", exc)
        return None

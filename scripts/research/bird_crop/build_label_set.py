"""Step 0 — sample bursts and emit a human labelling sheet.

Builds the study's only non-circular ground truth. Samples whole EXIF bursts (not
loose images), stratified by subject size, and renders one contact sheet per burst
so labelling is a side-by-side comparison.

The contact sheet cells are **bbox crops, not full frames**, and that is
deliberate: a 200 px thumbnail of an 8256 px frame shows a ~50 px bird, which
would leave the labeller as unable to judge subject sharpness as the full-frame
model under test. Within a 2-second burst the composition barely changes, so
sharpness and pose are what actually vary — exactly what the crop shows.

Reads production **read-only**; writes only into ``reports/bird-crop/labels/``.

Run in WSL with the app venv::

    source ~/.venvs/tf/bin/activate

    # See what would be sampled, decode nothing
    python -m scripts.research.bird_crop.build_label_set --dry-run

    # Default sample: 48 bursts (16 per subject-size tercile)
    python -m scripts.research.bird_crop.build_label_set

    # Restrict to the input-size study's folders, for comparability
    python -m scripts.research.bird_crop.build_label_set --folders 62,44,45,676

Then open ``reports/bird-crop/labels/sheets/`` alongside
``reports/bird-crop/labels/label_set.csv`` and fill in the ``verdict`` column
(``best`` / ``good`` / ``reject``) for every row.
"""

from __future__ import annotations

import argparse
import logging
import random
import statistics
import uuid
from pathlib import Path
from typing import Optional, Sequence

from scripts.research.bird_crop import bursts, labels, prod
from scripts.research.bird_crop.bbox import parse_bbox

logger = logging.getLogger("bird_crop.build_label_set")

#: Bursts sampled per subject-size tercile. Candidate bursts average ~4.7 frames,
#: so 3 x 18 lands around 250 images — enough for within-burst statistics without
#: making the labelling session unreasonable.
DEFAULT_PER_TERCILE = 18

#: Contact-sheet cell size. Large enough to judge eye/feather sharpness on a crop.
CELL_PX = 420
SHEET_COLS = 4


def _tercile_bounds(values: Sequence[float]) -> tuple[float, float]:
    """Return the two cut points splitting *values* into terciles."""
    ordered = sorted(values)
    if len(ordered) < 3:
        return (0.0, 0.0)
    q = statistics.quantiles(ordered, n=3, method="inclusive")
    return (q[0], q[1])


def _tercile_of(value: float, bounds: tuple[float, float]) -> int:
    low, high = bounds
    if value <= low:
        return 1
    if value <= high:
        return 2
    return 3


def select_bursts(
    *,
    folders: Optional[Sequence[int]] = None,
    per_tercile: int = DEFAULT_PER_TERCILE,
    min_size: int = 3,
    max_size: int = 8,
    seed: int = 20260729,
) -> tuple[dict[int, list[dict]], dict[int, int]]:
    """Pick bursts stratified by median subject size.

    Terciles are computed over the **whole boxed population**, not over the
    candidate bursts, so tercile 1 really means "small subject by library
    standards" and the sample stays comparable to library-wide statistics.

    Returns ``({burst_id: [rows]}, {burst_id: tercile})``.
    """
    rows = bursts.load_boxed_rows(folders=folders)
    if not rows:
        raise RuntimeError("No boxed images found in production; nothing to sample.")

    all_area_fracs = []
    for r in rows:
        box = parse_bbox(r.get("bird_bbox"))
        if box is not None:
            all_area_fracs.append(box.area_frac)
    bounds = _tercile_bounds(all_area_fracs)
    logger.info(
        "Library area_frac terciles: <=%.4f | <=%.4f | rest (n=%d)",
        bounds[0], bounds[1], len(all_area_fracs),
    )

    burst_of = bursts.group_bursts(rows)
    candidates = bursts.bursts_by_id(rows, burst_of, min_size=min_size, max_size=max_size)

    by_tercile: dict[int, list[int]] = {1: [], 2: [], 3: []}
    tercile_of_burst: dict[int, int] = {}
    for bid, frames in candidates.items():
        fracs = [
            box.area_frac
            for box in (parse_bbox(f.get("bird_bbox")) for f in frames)
            if box is not None
        ]
        if len(fracs) != len(frames):
            continue  # require every frame boxed, so all variants cover all frames
        t = _tercile_of(statistics.median(fracs), bounds)
        tercile_of_burst[bid] = t
        by_tercile[t].append(bid)

    rng = random.Random(seed)
    chosen: dict[int, list[dict]] = {}
    for t in (1, 2, 3):
        pool = sorted(by_tercile[t])
        rng.shuffle(pool)
        take = pool[:per_tercile]
        if len(take) < per_tercile:
            logger.warning(
                "Tercile %d has only %d eligible burst(s) (wanted %d).",
                t, len(take), per_tercile,
            )
        for bid in take:
            chosen[bid] = candidates[bid]

    logger.info(
        "Selected %d burst(s) / %d image(s): %s",
        len(chosen),
        sum(len(v) for v in chosen.values()),
        {t: sum(1 for b in chosen if tercile_of_burst[b] == t) for t in (1, 2, 3)},
    )
    return chosen, tercile_of_burst


def build_rows(
    chosen: dict[int, list[dict]],
    tercile_of_burst: dict[int, int],
) -> list[dict]:
    """Flatten selected bursts into label CSV rows (verdict left blank)."""
    out: list[dict] = []
    for bid in sorted(chosen):
        for idx, frame in enumerate(chosen[bid], start=1):
            out.append(
                {
                    "image_id": frame["id"],
                    "burst_id": bid,
                    "area_frac_tercile": tercile_of_burst[bid],
                    "frame_index": idx,
                    "verdict": "",
                }
            )
    return out


def render_sheets(
    chosen: dict[int, list[dict]],
    tercile_of_burst: dict[int, int],
    *,
    out_dir: Path,
    cell_px: int = CELL_PX,
) -> list[Path]:
    """Render one crop contact sheet per burst. Returns the paths written."""
    from scripts.research.clip_culling.live_stack_montage import montage

    out_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []

    for bid in sorted(chosen):
        frames = chosen[bid]
        cells = []
        tiles: list[Path] = []
        for idx, frame in enumerate(frames, start=1):
            crop_path = _write_crop_tile(frame, out_dir, bid, idx, cell_px)
            tiles.append(crop_path)
            box = parse_bbox(frame.get("bird_bbox"))
            area = f"{box.area_frac * 100:.1f}%" if box else "?"
            conf = f"{box.conf:.2f}" if box else "?"
            cells.append((str(crop_path), f"#{idx} id={frame['id']} area={area} conf={conf}"))

        sheet = out_dir / f"burst{bid:05d}_t{tercile_of_burst[bid]}_{uuid.uuid4()}.jpg"
        result = montage(cells, cols=SHEET_COLS, box=cell_px, out=str(sheet))
        if result:
            written.append(Path(result))
        for tile in tiles:
            tile.unlink(missing_ok=True)

    logger.info("Rendered %d contact sheet(s) into %s", len(written), out_dir)
    return written


def _write_crop_tile(frame: dict, out_dir: Path, bid: int, idx: int, cell_px: int) -> Path:
    """Decode one frame, crop to the padded box, and write a temp tile for montage.

    ``montage`` takes file paths, so crops land in short-lived tiles that are
    deleted once the sheet is assembled.
    """
    from PIL import Image

    from scripts.research.bird_crop import crops

    tile = out_dir / f".tile_{bid:05d}_{idx:02d}_{uuid.uuid4()}.jpg"
    read_path = _resolve_original(frame)
    try:
        if not read_path:
            raise FileNotFoundError(frame.get("file_path"))
        # pad 25% for labelling: a little context helps judge pose and clipping
        # without shrinking the bird the way a full frame does.
        result = crops.load_variant(read_path, frame.get("bird_bbox"), "croppad25")
        if result is None:
            raise ValueError("no usable box")
        img = result.image
        img.thumbnail((cell_px, cell_px), Image.LANCZOS)
        img.save(tile, "JPEG", quality=92)
    except Exception as exc:  # noqa: BLE001 — one bad frame must not kill the sheet
        logger.warning("Crop tile failed for image_id=%s: %s", frame.get("id"), exc)
        Image.new("RGB", (cell_px, cell_px), (40, 40, 40)).save(tile, "JPEG")
    return tile


def _resolve_original(frame: dict) -> Optional[str]:
    """Prefer the original file; fall back to a cached thumbnail only if missing.

    Mirrors ``bird_species._resolve_inference_path``: cropping a 512 px thumbnail
    would defeat the point.
    """
    import os

    fp = frame.get("file_path")
    if fp and os.path.exists(fp):
        return fp
    try:
        from modules.thumbnails import get_thumb_wsl

        thumb = get_thumb_wsl(frame)
        if thumb and os.path.exists(thumb):
            logger.debug("image_id=%s: original missing, using thumbnail.", frame.get("id"))
            return thumb
    except Exception:  # noqa: BLE001
        pass
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--folders",
        default="",
        help="Comma-separated folder_id list to restrict the corpus (default: whole library)",
    )
    parser.add_argument(
        "--per-tercile",
        type=int,
        default=DEFAULT_PER_TERCILE,
        help=f"Bursts to sample per subject-size tercile (default: {DEFAULT_PER_TERCILE})",
    )
    parser.add_argument("--min-burst", type=int, default=3, help="Smallest burst to consider")
    parser.add_argument("--max-burst", type=int, default=8, help="Largest burst to consider")
    parser.add_argument("--seed", type=int, default=20260729, help="Sampling seed (reproducibility)")
    parser.add_argument(
        "--no-sheets",
        action="store_true",
        help="Write the CSV only; skip contact-sheet rendering (no image decode)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Report what would be sampled; write nothing and decode nothing",
    )
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args()

    prod.configure_logging(args.verbose)
    prod.assert_prod()

    folders = [int(x) for x in args.folders.split(",") if x.strip()] or None

    chosen, tercile_of_burst = select_bursts(
        folders=folders,
        per_tercile=args.per_tercile,
        min_size=args.min_burst,
        max_size=args.max_burst,
        seed=args.seed,
    )
    if not chosen:
        logger.error("No eligible bursts; nothing to label.")
        return 1

    rows = build_rows(chosen, tercile_of_burst)

    if args.dry_run:
        logger.info(
            "DRY RUN: would write %d row(s) across %d burst(s) to %s",
            len(rows), len(chosen), labels.LABEL_CSV,
        )
        for bid in sorted(chosen)[:5]:
            frames = chosen[bid]
            logger.info(
                "  burst %d (tercile %d, %d frames) folder=%s",
                bid, tercile_of_burst[bid], len(frames), frames[0].get("folder_path"),
            )
        return 0

    labels.write_template(rows)

    if not args.no_sheets:
        render_sheets(chosen, tercile_of_burst, out_dir=prod.SHEETS_DIR)

    prod.write_json(
        "label_set_provenance.json",
        {
            "folders": folders or "all",
            "per_tercile": args.per_tercile,
            "burst_size_range": [args.min_burst, args.max_burst],
            "gap_seconds": bursts.DEFAULT_GAP_SECONDS,
            "seed": args.seed,
            "n_bursts": len(chosen),
            "n_images": len(rows),
            "images_per_tercile": {
                str(t): sum(1 for r in rows if r["area_frac_tercile"] == t) for t in (1, 2, 3)
            },
        },
        subdir="labels",
    )

    logger.info(
        "Next: open %s and fill in the 'verdict' column (best|good|reject) for all %d rows, "
        "using the sheets in %s.",
        labels.LABEL_CSV, len(rows), prod.SHEETS_DIR,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

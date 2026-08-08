"""Freeze the study population to one explicit, auditable list of image ids.

Why this exists
---------------
The first Phase 2 sweep produced four mutually incomparable populations. Cause:
``input_size_embed._subset_rows`` takes a *strided* sample —
``rows[::step][:n]`` where ``step = len(rows) // n`` — of the rows that have a
usable ``bird_bbox``, and a ``backfill_bird_bbox.py --all-null`` job was growing
that population throughout (boxed count 21,194 -> 24,562 -> 35,322). Every process
that started at a different time therefore sampled a different 200 images.
``--boxed-only`` kept the crop and full-frame arms the same *size*; it did not pin
*which* images. The quarantined runs and the full breakdown are in
``reports/clip-culling/input-size/npz/archive_mixed_population/README.md``.

The set is pinned to the **human label set** rather than a folder sample, so all
five tracks (embedding, iqa, caption, species, degradation) share one population
and the within-burst human verdicts apply to every one of them. The previous
folder scope (62, 676) had *zero* overlap with the label set, which meant the
labels could never have evaluated Phase 2 at all.

Run in WSL with the app venv::

    source ~/.venvs/tf/bin/activate
    python -m scripts.research.bird_crop.pin_study_set            # write the list
    python -m scripts.research.bird_crop.pin_study_set --verify    # check the NPZs
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
from pathlib import Path
from typing import Optional

from scripts.research.bird_crop import labels, prod

logger = logging.getLogger("bird_crop.pin")

IDS_FILE = prod.REPORTS_DIR / "study_image_ids.txt"
PROVENANCE_FILE = prod.REPORTS_DIR / "study_image_ids_provenance.json"

#: NPZ tracks the population invariant applies to. ``native`` is excluded: it
#: measures model input geometry, not per-image inference, and is not pinned.
PINNED_TRACKS = ("embedding", "iqa", "caption")


def read_ids(path: Path = IDS_FILE) -> list[int]:
    """Read the pinned id list. Blank lines and ``#`` comments are ignored."""
    if not path.exists():
        raise FileNotFoundError(
            f"No pinned study set at {path}. Run "
            "`python -m scripts.research.bird_crop.pin_study_set` first."
        )
    ids: list[int] = []
    for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        text = line.split("#", 1)[0].strip()
        if not text:
            continue
        try:
            ids.append(int(text))
        except ValueError as exc:
            raise ValueError(f"{path}:{lineno}: not an integer image id: {line!r}") from exc
    if not ids:
        raise ValueError(f"{path} contains no image ids.")
    duplicates = len(ids) - len(set(ids))
    if duplicates:
        raise ValueError(f"{path} contains {duplicates} duplicate id(s).")
    return sorted(ids)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def collect_provenance(ids: list[int]) -> dict:
    """Describe the pinned set well enough to reproduce or audit it later.

    Records the boxed-population size *at generation time* precisely because that
    number moves: a future reader comparing it against a live count can tell
    whether the library has drifted since the sweep ran.
    """
    placeholders = ",".join(["%s"] * len(ids))
    rows = prod.select(
        f"SELECT i.id, i.folder_id, "
        f"       jsonb_exists(i.bird_bbox, 'x1') AS boxed, "
        f"       (i.bird_bbox->>'area_frac')::float AS area_frac "
        f"FROM images i WHERE i.id IN ({placeholders})",
        ids,
    )
    found = {r["id"]: r for r in rows}
    missing = [i for i in ids if i not in found]
    boxless = sorted(i for i, r in found.items() if not r["boxed"])
    per_folder: dict[str, int] = {}
    for r in rows:
        key = str(r["folder_id"])
        per_folder[key] = per_folder.get(key, 0) + 1

    boxed_total = prod.select(
        "SELECT COUNT(*) AS n FROM images WHERE jsonb_exists(bird_bbox, 'x1')"
    )[0]["n"]

    return {
        "source_csv": str(labels.LABEL_CSV.relative_to(prod.PROJECT_ROOT)),
        "source_csv_sha256": _sha256(labels.LABEL_CSV),
        "n_ids": len(ids),
        "n_missing_from_db": len(missing),
        "missing_ids": missing,
        "n_boxless": len(boxless),
        "boxless_ids": boxless,
        "folders": dict(sorted(per_folder.items(), key=lambda kv: -kv[1])),
        "n_folders": len(per_folder),
        "boxed_population_at_generation": boxed_total,
    }


def write_ids(ids: list[int], provenance: dict, *, force: bool = False) -> Path:
    """Write the pinned id list plus its provenance JSON."""
    if IDS_FILE.exists() and not force:
        raise FileExistsError(
            f"{IDS_FILE} already exists. The whole point of pinning is that this set "
            "stops moving — pass --force only if you intend to invalidate every cached "
            "NPZ and re-run the sweep."
        )
    IDS_FILE.parent.mkdir(parents=True, exist_ok=True)
    header = [
        "# Pinned bird-crop study population — one production images.id per line.",
        f"# Generated from {provenance['source_csv']} "
        f"(sha256 {provenance['source_csv_sha256'][:12]}).",
        "# Every track reads this file; do not edit by hand. See "
        "study_image_ids_provenance.json.",
    ]
    IDS_FILE.write_text(
        "\n".join(header + [str(i) for i in ids]) + "\n", encoding="utf-8", newline="\n"
    )
    logger.info("Wrote %s (%d ids)", IDS_FILE, len(ids))
    prod.write_json(PROVENANCE_FILE.name, provenance)
    return IDS_FILE


def verify_npz(npz_dir: Optional[Path] = None, ids: Optional[list[int]] = None) -> dict:
    """Assert every pinned-track NPZ holds exactly the pinned id set.

    This is the check whose absence caused the rework, so it is scripted rather
    than eyeballed. Subdirectories are skipped, which keeps the quarantined
    ``archive_mixed_population/`` runs out of the way.
    """
    import numpy as np

    if npz_dir is None:
        from scripts.research.clip_culling import common

        npz_dir = Path(common.INPUT_SIZE_NPZ_DIR)
    expected = set(ids if ids is not None else read_ids())

    checked, mismatched = [], []
    for path in sorted(npz_dir.glob("*.npz")):
        track = path.stem.split("_", 1)[0]
        if track not in PINNED_TRACKS:
            continue
        got = set(int(v) for v in np.load(path, allow_pickle=True)["image_ids"])
        entry = {
            "npz": path.name,
            "n": len(got),
            "n_missing": len(expected - got),
            "n_extra": len(got - expected),
        }
        checked.append(entry)
        if got != expected:
            mismatched.append(entry)

    result = {
        "npz_dir": str(npz_dir),
        "n_expected_ids": len(expected),
        "n_checked": len(checked),
        "n_mismatched": len(mismatched),
        "mismatched": mismatched,
    }
    if mismatched:
        for m in mismatched:
            logger.error(
                "POPULATION MISMATCH %s: n=%d missing=%d extra=%d",
                m["npz"], m["n"], m["n_missing"], m["n_extra"],
            )
    elif not checked:
        # "0 of 0 passed" must not read as a green light.
        logger.warning(
            "No pinned-track NPZ found in %s — nothing was verified. Run phase 2 first.",
            npz_dir,
        )
    else:
        logger.info(
            "All %d pinned-track NPZ(s) carry the same %d image ids.",
            len(checked), len(expected),
        )
    return result


def folders_for(ids: list[int]) -> list[int]:
    """Distinct ``folder_id`` values covering *ids*.

    ``input_size_eval`` reads metadata and capture times by folder, not by id,
    because burst grouping needs a pinned image's *neighbouring* frames to see the
    burst it belongs to. Its default scope is the E2E seed folders, which have zero
    overlap with the pin — evaluating with that default would join production NPZ
    ids against the wrong folders and quietly find nothing.
    """
    rows = prod.select(
        "SELECT DISTINCT folder_id FROM images WHERE id = ANY(%s) ORDER BY folder_id",
        [sorted(ids)],
    )
    return [r["folder_id"] for r in rows]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--verify", action="store_true",
        help="check cached NPZs against the pinned set instead of writing it",
    )
    ap.add_argument(
        "--print-folders", action="store_true",
        help=(
            "print the pinned population's folder_id list as a comma-separated string "
            "(for CLIP_CULLING_FOLDERS) instead of writing the set"
        ),
    )
    ap.add_argument(
        "--ids-file", default=None,
        help=f"pinned id list to read (default: {IDS_FILE})",
    )
    ap.add_argument("--force", action="store_true", help="overwrite an existing pinned set")
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()
    prod.configure_logging(args.verbose)

    ids_path = Path(args.ids_file) if args.ids_file else IDS_FILE

    if args.print_folders:
        prod.assert_prod()
        # Logging goes to stderr, so stdout stays a clean value for $(...).
        print(",".join(str(f) for f in folders_for(read_ids(ids_path))))
        return 0

    if args.verify:
        result = verify_npz(ids=read_ids(ids_path))
        print(json.dumps(result, indent=2))
        return 1 if result["n_mismatched"] else 0

    prod.assert_prod()
    rows = labels.load(labels.LABEL_CSV, require_complete=False)
    ids = sorted({r.image_id for r in rows})
    provenance = collect_provenance(ids)

    if provenance["n_missing_from_db"]:
        logger.error(
            "%d label-set id(s) are not in the database: %s",
            provenance["n_missing_from_db"], provenance["missing_ids"][:10],
        )
        return 2
    if provenance["n_boxless"]:
        logger.error(
            "%d label-set id(s) have no usable bird box: %s. The crop tracks would "
            "skip them, so the population would not be identical across sources.",
            provenance["n_boxless"], provenance["boxless_ids"][:10],
        )
        return 2

    write_ids(ids, provenance, force=args.force)
    logger.info(
        "Pinned %d images across %d folder(s); boxed population is %d at generation.",
        provenance["n_ids"], provenance["n_folders"],
        provenance["boxed_population_at_generation"],
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

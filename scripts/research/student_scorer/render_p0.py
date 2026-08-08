"""Resumable parallel P0 render cache for student-scorer image training.

Mirrors ``MultiModelMUSIQ.preprocess_image`` decode + fit/pad, with rawpy fed
from ``BytesIO`` (same bytes as the file) so WSL 9p mounts stay usable.

Writes JPEGs under ``~/.cache/student_scorer/<manifest_id>/p0_512/`` and a
durable ``render_index.json`` under the manifest artifacts tree.
"""

from __future__ import annotations

import argparse
import io
import json
import shutil
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Mapping, Sequence

from PIL import Image, ImageOps

from scripts.research.student_scorer.common import (
    ensure_artifacts_dir,
    read_json,
    sha256_file,
    write_json,
)
from scripts.research.student_scorer.data import validate_manifest_against_protocol
from scripts.research.student_scorer.export_embeddings_npz import load_manifest_rows

RAW_EXTENSIONS = {
    ".nef",
    ".nrw",
    ".cr2",
    ".cr3",
    ".arw",
    ".dng",
    ".orf",
    ".rw2",
    ".pef",
    ".raf",
    ".srw",
}

EXIFTOOL_TIMEOUT_S = 20
EXIFTOOL_TRANSIENT_RETRIES = 2
SAFETY_TIMEOUT_S = 2.0
INDEX_FLUSH_EVERY = 500


def is_raw_file(path: str | Path) -> bool:
    return Path(path).suffix.lower() in RAW_EXTENSIONS


def default_cache_dir(manifest_id: str) -> Path:
    home = Path.home()
    return home / ".cache" / "student_scorer" / manifest_id / "p0_512"


def shard_relpath(image_id: int) -> str:
    return f"{int(image_id) % 100}/{int(image_id)}.jpg"


def preprocessing_knobs(meta: Mapping[str, Any]) -> dict[str, Any]:
    prep = meta.get("preprocessing") or {}
    method = str(prep.get("raw_conversion_method") or "rawpy_half").strip().lower()
    max_resolution = int(prep.get("max_resolution") or 512)
    jpeg_quality = int(prep.get("jpeg_quality") or 85)
    max_resolution = max(224, min(2048, max_resolution))
    jpeg_quality = max(50, min(100, jpeg_quality))
    return {
        "method": method,
        "max_resolution": max_resolution,
        "jpeg_quality": jpeg_quality,
        "exiftool_timeout_s": EXIFTOOL_TIMEOUT_S,
        "transient_retries": EXIFTOOL_TRANSIENT_RETRIES,
    }


def is_safe_for_rawpy(raw_path: str) -> bool:
    """Mirror MultiModelMUSIQ._is_safe_for_rawpy (HE / Z8-Z9 compressed gate)."""
    if shutil.which("exiftool") is None:
        return True
    try:
        cmd = ["exiftool", "-Model", "-Compression", "-NEFCompression", "-j", raw_path]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=SAFETY_TIMEOUT_S)
        if result.returncode != 0:
            return True
        data = json.loads(result.stdout)
        if not data or not isinstance(data, list):
            return True
        info = data[0]
        model = info.get("Model", "") or ""
        compression = info.get("Compression", "") or ""
        nef_compression = info.get("NEFCompression", "") or ""
        if "Nikon HE" in compression:
            return False
        if "high efficiency" in nef_compression.lower():
            return False
        if ("Z 8" in model or "Z 9" in model) and "Nikon NEF Compressed" in compression:
            return False
        return True
    except Exception:
        return True


def _extract_jpeg_exiftool(
    file_path: str,
    *,
    timeout_s: float = EXIFTOOL_TIMEOUT_S,
    transient_retries: int = EXIFTOOL_TRANSIENT_RETRIES,
) -> tuple[Image.Image | None, str | None]:
    if shutil.which("exiftool") is None:
        return None, None
    max_attempts = max(1, int(transient_retries) + 1)
    min_len = 500
    for tag in ("JpgFromRaw", "PreviewImage", "OtherImage", "ThumbnailImage"):
        for attempt in range(1, max_attempts + 1):
            try:
                cmd = ["exiftool", "-b", f"-{tag}", file_path]
                result = subprocess.run(cmd, capture_output=True, text=False, timeout=timeout_s)
            except (subprocess.TimeoutExpired, OSError):
                if attempt < max_attempts:
                    time.sleep(0.5 * attempt)
                    continue
                break
            except Exception:
                break
            if result.returncode != 0 or len(result.stdout) < min_len:
                break
            data = result.stdout
            if data.startswith(b"\xff\xd8"):
                img = Image.open(io.BytesIO(data))
                img.load()
                return img.convert("RGB"), f"exiftool:{tag}"
            try:
                img = Image.open(io.BytesIO(data))
                img.load()
                return img.convert("RGB"), f"exiftool:{tag}"
            except Exception:
                break
    return None, None


def _extract_jpeg_rawpy_bytesio(file_path: str) -> Image.Image | None:
    """rawpy half-size decode fed from in-memory bytes (WSL 9p-safe)."""
    if not is_safe_for_rawpy(file_path):
        return None
    try:
        import rawpy
    except ImportError:
        return None
    try:
        with open(file_path, "rb") as fh:
            blob = fh.read()
        with rawpy.imread(io.BytesIO(blob)) as raw:
            rgb = raw.postprocess(use_camera_wb=True, half_size=True)
            return Image.fromarray(rgb)
    except Exception:
        return None


def fit_pad_to_square(pil_image: Image.Image, target_size: int) -> Image.Image:
    if pil_image.size == (target_size, target_size):
        return pil_image
    img = pil_image.copy()
    img.thumbnail((target_size, target_size), Image.BICUBIC)
    delta_w = target_size - img.size[0]
    delta_h = target_size - img.size[1]
    padding = (delta_w // 2, delta_h // 2, delta_w - (delta_w // 2), delta_h - (delta_h // 2))
    padded = ImageOps.expand(img, padding, fill=0)
    if padded.size != (target_size, target_size):
        padded = padded.resize((target_size, target_size), Image.BICUBIC)
    return padded


def decode_p0(
    path: str,
    *,
    method: str = "rawpy_half",
    max_resolution: int = 512,
    jpeg_quality: int = 85,
    exiftool_timeout_s: float = EXIFTOOL_TIMEOUT_S,
    transient_retries: int = EXIFTOOL_TRANSIENT_RETRIES,
) -> tuple[Image.Image, str]:
    """Decode + fit/pad to P0 square. Returns (RGB image, resolved_method)."""
    conversion_prefer = (method or "rawpy_half").strip().lower()
    target_size = max(224, min(2048, int(max_resolution)))
    pil_image: Image.Image | None = None
    decode_method: str | None = None

    if is_raw_file(path):
        if conversion_prefer == "rawpy_half":
            pil_image = _extract_jpeg_rawpy_bytesio(path)
            decode_method = "rawpy_half" if pil_image is not None else None
            if pil_image is None:
                pil_image, em = _extract_jpeg_exiftool(
                    path, timeout_s=exiftool_timeout_s, transient_retries=transient_retries
                )
                decode_method = em
        else:
            pil_image, em = _extract_jpeg_exiftool(
                path, timeout_s=exiftool_timeout_s, transient_retries=transient_retries
            )
            decode_method = em
            if pil_image is None:
                pil_image = _extract_jpeg_rawpy_bytesio(path)
                decode_method = "rawpy_half" if pil_image is not None else None
    else:
        pil_image = Image.open(path).convert("RGB")
        decode_method = "pil_open"

    if pil_image is None or not decode_method:
        raise RuntimeError(f"P0 decode failed for {path}")

    padded = fit_pad_to_square(pil_image, target_size)
    # jpeg_quality is applied by the caller on save; keep signature parity with knobs
    _ = jpeg_quality
    return padded, decode_method


def save_p0_jpeg(image: Image.Image, out_path: Path, jpeg_quality: int) -> str:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = out_path.with_suffix(".jpg.tmp")
    image.save(tmp, "JPEG", quality=int(jpeg_quality))
    tmp.replace(out_path)
    return sha256_file(out_path)


def _worker_render(payload: dict[str, Any]) -> dict[str, Any]:
    """Process-pool worker: decode one image into the cache."""
    image_id = int(payload["image_id"])
    path = str(payload["path"])
    out_path = Path(payload["out_path"])
    knobs = payload["knobs"]
    rel = payload["rel"]
    t0 = time.perf_counter()
    try:
        existing_method = payload.get("existing_method")
        # Only skip when the index already records how this JPEG was decoded; an orphaned
        # file from a killed run is re-rendered so resolved_method stays exact.
        if existing_method and out_path.is_file() and out_path.stat().st_size > 0:
            return {
                "image_id": image_id,
                "rel_path": rel,
                "resolved_method": existing_method,
                "jpeg_sha256": sha256_file(out_path),
                "status": "ok",
                "skipped": True,
                "seconds": time.perf_counter() - t0,
                "error": None,
            }
        if not Path(path).is_file():
            return {
                "image_id": image_id,
                "rel_path": rel,
                "resolved_method": None,
                "jpeg_sha256": None,
                "status": "missing_source",
                "skipped": False,
                "seconds": time.perf_counter() - t0,
                "error": "source_missing",
            }
        img, method = decode_p0(
            path,
            method=knobs["method"],
            max_resolution=knobs["max_resolution"],
            jpeg_quality=knobs["jpeg_quality"],
            exiftool_timeout_s=knobs["exiftool_timeout_s"],
            transient_retries=knobs["transient_retries"],
        )
        digest = save_p0_jpeg(img, out_path, knobs["jpeg_quality"])
        return {
            "image_id": image_id,
            "rel_path": rel,
            "resolved_method": method,
            "jpeg_sha256": digest,
            "status": "ok",
            "skipped": False,
            "seconds": time.perf_counter() - t0,
            "error": None,
        }
    except Exception as exc:  # noqa: BLE001 — enumerated failure classes for summary
        return {
            "image_id": image_id,
            "rel_path": rel,
            "resolved_method": None,
            "jpeg_sha256": None,
            "status": "error",
            "skipped": False,
            "seconds": time.perf_counter() - t0,
            "error": f"{type(exc).__name__}:{exc}",
        }


def _write_index_atomic(index_path: Path, payload: Mapping[str, Any]) -> None:
    """Write the index via tmp+replace so a kill mid-flush cannot truncate it."""
    index_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = index_path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
    tmp.replace(index_path)


def _load_existing_index(index_path: Path) -> dict[int, dict[str, Any]]:
    if not index_path.is_file():
        return {}
    data = read_json(index_path)
    rows = data.get("images") if isinstance(data, dict) else data
    out: dict[int, dict[str, Any]] = {}
    if isinstance(rows, list):
        for row in rows:
            out[int(row["image_id"])] = row
    elif isinstance(rows, dict):
        for k, v in rows.items():
            out[int(k)] = v
    return out


def run_render(
    *,
    manifest_dir: Path,
    out_dir: Path | None = None,
    workers: int = 12,
    split: str | None = None,
    limit: int | None = None,
    dry_run: bool = False,
    expected_protocol_id: str | None = None,
) -> dict[str, Any]:
    meta = read_json(manifest_dir / "manifest.meta.json")
    validate_manifest_against_protocol(
        meta,
        expected_checksum=meta.get("checksum"),
        expected_protocol_id=expected_protocol_id or meta.get("protocol_id"),
        expected_contract_hash=meta.get("contract_hash"),
    )
    knobs = preprocessing_knobs(meta)
    manifest_id = str(meta["manifest_id"])
    cache_dir = out_dir or default_cache_dir(manifest_id)
    cache_dir.mkdir(parents=True, exist_ok=True)

    rows = load_manifest_rows(manifest_dir)
    split_of: dict[int, str] = {}
    splits_path = manifest_dir / "splits.json"
    if splits_path.is_file():
        data = read_json(splits_path)
        split_of = {int(a["image_id"]): a["split"] for a in data["assignments"]}

    jobs: list[dict[str, Any]] = []
    for row in rows:
        iid = int(row["image_id"])
        if split is not None and split_of.get(iid) != split:
            continue
        path = str(row.get("path_token") or "")
        rel = shard_relpath(iid)
        jobs.append(
            {
                "image_id": iid,
                "path": path,
                "out_path": str(cache_dir / rel),
                "rel": rel,
                "knobs": knobs,
            }
        )
        if limit is not None and len(jobs) >= int(limit):
            break

    artifacts = ensure_artifacts_dir(manifest_id) / "renders"
    artifacts.mkdir(parents=True, exist_ok=True)
    index_path = artifacts / "render_index.json"
    summary_path = artifacts / "render_summary.json"
    existing = _load_existing_index(index_path)

    if dry_run:
        summary = {
            "dry_run": True,
            "n_jobs": len(jobs),
            "cache_dir": str(cache_dir),
            "knobs": knobs,
            "split": split,
            "limit": limit,
        }
        write_json(summary_path, summary)
        return summary

    # Attach existing method hints for skip path
    for job in jobs:
        prev = existing.get(int(job["image_id"]))
        if prev and prev.get("status") == "ok":
            job["existing_method"] = prev.get("resolved_method")

    t0 = time.perf_counter()
    results: dict[int, dict[str, Any]] = dict(existing)
    n_workers = max(1, int(workers))

    def _index_payload() -> dict[str, Any]:
        return {
            "images": [results[k] for k in sorted(results)],
            "cache_dir": str(cache_dir),
            "manifest_id": manifest_id,
        }

    def _record(res: Mapping[str, Any]) -> None:
        results[int(res["image_id"])] = {
            "image_id": res["image_id"],
            "rel_path": res["rel_path"],
            "resolved_method": res["resolved_method"],
            "jpeg_sha256": res["jpeg_sha256"],
            "status": res["status"],
            "error": res.get("error"),
        }

    # `results` is mutated only here on the main thread, so the flush needs no lock.
    n_done = 0
    if n_workers == 1:
        for job in jobs:
            _record(_worker_render(job))
            n_done += 1
            if n_done % INDEX_FLUSH_EVERY == 0:
                _write_index_atomic(index_path, _index_payload())
    else:
        with ThreadPoolExecutor(max_workers=n_workers) as pool:
            futs = [pool.submit(_worker_render, job) for job in jobs]
            for fut in as_completed(futs):
                _record(fut.result())
                n_done += 1
                if n_done % INDEX_FLUSH_EVERY == 0:
                    _write_index_atomic(index_path, _index_payload())

    payload = _index_payload()
    images = payload["images"]
    _write_index_atomic(index_path, payload)

    by_method: dict[str, int] = {}
    by_status: dict[str, int] = {}
    failures: dict[str, int] = {}
    for row in images:
        st = str(row.get("status") or "unknown")
        by_status[st] = by_status.get(st, 0) + 1
        if st == "ok":
            m = str(row.get("resolved_method") or "unknown")
            by_method[m] = by_method.get(m, 0) + 1
        else:
            err = str(row.get("error") or st)
            failures[err] = failures.get(err, 0) + 1

    summary = {
        "manifest_id": manifest_id,
        "protocol_id": meta.get("protocol_id"),
        "cache_dir": str(cache_dir),
        "knobs": knobs,
        "n_jobs_this_run": len(jobs),
        "n_index": len(images),
        "by_status": by_status,
        "by_resolved_method": by_method,
        "failures_by_class": failures,
        "wall_seconds": time.perf_counter() - t0,
        "workers": n_workers,
        "split": split,
        "limit": limit,
    }
    write_json(summary_path, summary)
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Render P0 JPEG cache for student scorer")
    parser.add_argument("--manifest-dir", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, default=None)
    parser.add_argument("--workers", type=int, default=12)
    parser.add_argument("--split", type=str, default=None)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--expected-protocol-id", type=str, default=None)
    args = parser.parse_args(argv)
    out = run_render(
        manifest_dir=args.manifest_dir,
        out_dir=args.out_dir,
        workers=args.workers,
        split=args.split,
        limit=args.limit,
        dry_run=args.dry_run,
        expected_protocol_id=args.expected_protocol_id,
    )
    print(json.dumps(out, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

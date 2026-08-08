"""Tests for P0 render cache (fast + ml)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.research.student_scorer import render_p0
from scripts.research.student_scorer.common import write_json
from scripts.research.student_scorer.render_p0 import (
    decode_p0,
    fit_pad_to_square,
    is_safe_for_rawpy,
    run_render,
    save_p0_jpeg,
    shard_relpath,
)


def _mini_meta(checksum: str = "abc", protocol_id: str = "ssp_test", contract_hash: str = "ch") -> dict:
    return {
        "manifest_id": "msm_test_render",
        "checksum": checksum,
        "protocol_id": protocol_id,
        "contract_hash": contract_hash,
        "teachers": ["arniqa", "ava", "liqe", "spaq", "topiq"],
        "preprocessing": {
            "raw_conversion_method": "rawpy_half",
            "max_resolution": 512,
            "jpeg_quality": 85,
            "musiq_version": "unknown",
            "fingerprint": "fp",
            "preprocess_source_hash": "h",
            "pad": "black_square",
            "resize": "bicubic_thumbnail_fit",
        },
        "fusion": {},
        "percentile_anchors": {},
        "gates": {},
    }


def _write_mini_manifest(tmp: Path, rows: list[dict], meta: dict | None = None) -> Path:
    meta = meta or _mini_meta()
    write_json(tmp / "manifest.meta.json", meta)
    with (tmp / "manifest.jsonl").open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row) + "\n")
    write_json(
        tmp / "splits.json",
        {"assignments": [{"image_id": r["image_id"], "split": "train"} for r in rows]},
    )
    return tmp


def test_render_is_resumable_and_refuses_protocol_mismatch(tmp_path, monkeypatch):
    from PIL import Image

    # Point artifacts under tmp
    monkeypatch.setattr(
        "scripts.research.student_scorer.render_p0.ensure_artifacts_dir",
        lambda run_id=None: tmp_path / "artifacts" / (run_id or "root"),
    )

    img_path = tmp_path / "src.jpg"
    Image.new("RGB", (64, 48), color=(10, 20, 30)).save(img_path, "JPEG")
    rows = [{"image_id": 7, "path_token": str(img_path)}]
    manifest = _write_mini_manifest(tmp_path / "m", rows)
    out_dir = tmp_path / "cache"

    s1 = run_render(manifest_dir=manifest, out_dir=out_dir, workers=1, limit=1)
    assert s1["by_status"].get("ok", 0) == 1
    jpg = out_dir / shard_relpath(7)
    assert jpg.is_file()
    mtime1 = jpg.stat().st_mtime

    s2 = run_render(manifest_dir=manifest, out_dir=out_dir, workers=1, limit=1)
    assert jpg.stat().st_mtime == mtime1
    # second pass should still report ok (skipped_existing or ok)
    assert s2["by_status"].get("ok", 0) >= 1

    with pytest.raises(ValueError):
        run_render(
            manifest_dir=manifest,
            out_dir=out_dir,
            workers=1,
            expected_protocol_id="ssp_wrong",
        )


def test_orphan_jpeg_without_index_row_is_rerendered(tmp_path, monkeypatch):
    """A JPEG left by a killed run must regain a real resolved_method, not a skip label."""
    from PIL import Image

    monkeypatch.setattr(
        "scripts.research.student_scorer.render_p0.ensure_artifacts_dir",
        lambda run_id=None: tmp_path / "artifacts" / (run_id or "root"),
    )
    img_path = tmp_path / "src.jpg"
    Image.new("RGB", (64, 48), color=(10, 20, 30)).save(img_path, "JPEG")
    manifest = _write_mini_manifest(tmp_path / "m", [{"image_id": 7, "path_token": str(img_path)}])
    out_dir = tmp_path / "cache"
    index_path = tmp_path / "artifacts" / "msm_test_render" / "renders" / "render_index.json"

    run_render(manifest_dir=manifest, out_dir=out_dir, workers=1, limit=1)
    assert (out_dir / shard_relpath(7)).is_file()

    # Simulate the killed run: cache JPEG survives, index does not.
    index_path.unlink()

    summary = run_render(manifest_dir=manifest, out_dir=out_dir, workers=1, limit=1)
    assert summary["by_resolved_method"] == {"pil_open": 1}
    rows = json.loads(index_path.read_text())["images"]
    assert [r["resolved_method"] for r in rows] == ["pil_open"]


def test_index_is_flushed_periodically(tmp_path, monkeypatch):
    """Progress survives a kill: the index exists before the run finishes."""
    from PIL import Image

    monkeypatch.setattr(
        "scripts.research.student_scorer.render_p0.ensure_artifacts_dir",
        lambda run_id=None: tmp_path / "artifacts" / (run_id or "root"),
    )
    monkeypatch.setattr("scripts.research.student_scorer.render_p0.INDEX_FLUSH_EVERY", 1)

    index_path = tmp_path / "artifacts" / "msm_test_render" / "renders" / "render_index.json"
    seen: list[int] = []
    real_flush = render_p0._write_index_atomic

    def spy(path, payload):
        real_flush(path, payload)
        seen.append(len(payload["images"]))

    monkeypatch.setattr("scripts.research.student_scorer.render_p0._write_index_atomic", spy)

    rows = []
    for iid in (1, 2, 3):
        p = tmp_path / f"src{iid}.jpg"
        Image.new("RGB", (32, 24), color=(iid, iid, iid)).save(p, "JPEG")
        rows.append({"image_id": iid, "path_token": str(p)})
    manifest = _write_mini_manifest(tmp_path / "m", rows)

    run_render(manifest_dir=manifest, out_dir=tmp_path / "cache", workers=1)

    # One flush per completion plus the final write — not a single write at the end.
    assert seen == [1, 2, 3, 3]
    assert len(json.loads(index_path.read_text())["images"]) == 3


def test_fit_pad_produces_exact_square():
    from PIL import Image

    img = Image.new("RGB", (100, 50), color=(1, 2, 3))
    out = fit_pad_to_square(img, 64)
    assert out.size == (64, 64)


@pytest.mark.ml
def test_torch_not_required_for_decode_jpeg(tmp_path):
    from PIL import Image

    p = tmp_path / "a.jpg"
    Image.new("RGB", (80, 60), color=(5, 6, 7)).save(p, "JPEG")
    img, method = decode_p0(str(p), method="rawpy_half", max_resolution=256, jpeg_quality=85)
    assert method == "pil_open"
    assert img.size == (256, 256)


def _discover_family_nefs() -> dict[str, list[Path]]:
    """Best-effort find ≥1 NEF per camera family from Photos or fixtures."""
    roots = [
        Path("/mnt/d/Photos"),
        Path("D:/Photos"),
        Path("tests/fixtures/testing_samples"),
    ]
    families = {"Z8": [], "Z6ii": [], "D90": []}
    patterns = {
        "Z8": ["**/Z8/**/*.NEF", "**/Z8/**/*.nef"],
        "Z6ii": ["**/Z6ii/**/*.NEF", "**/Z6*/**/*.NEF"],
        "D90": ["**/D90/**/*.NEF", "**/D300/**/*.NEF"],
    }
    for root in roots:
        if not root.is_dir():
            continue
        for fam, globs in patterns.items():
            if len(families[fam]) >= 2:
                continue
            for g in globs:
                for p in root.glob(g):
                    families[fam].append(p)
                    if len(families[fam]) >= 2:
                        break
                if len(families[fam]) >= 2:
                    break
    return families


@pytest.mark.ml
@pytest.mark.sample_data
def test_render_matches_production_preprocess_bytes(tmp_path):
    """Byte-identical P0 JPEG vs MultiModelMUSIQ.preprocess_image for live NEFs."""
    families = _discover_family_nefs()
    available = {k: v for k, v in families.items() if v}
    if len(available) < 1:
        pytest.skip("No camera-family NEFs found under Photos/fixtures")

    from scripts.python.run_all_musiq_models import MultiModelMUSIQ

    musiq = MultiModelMUSIQ()
    # Force knobs via config already set; compare JPEGs
    checked = 0
    for fam, paths in available.items():
        for path in paths[:2]:
            prod_out = musiq.preprocess_image(str(path), output_dir=str(tmp_path / f"prod_{checked}"))
            assert prod_out and Path(prod_out).is_file()
            img, method = decode_p0(str(path))
            ours = tmp_path / f"ours_{checked}.jpg"
            save_p0_jpeg(img, ours, 85)
            assert Path(prod_out).read_bytes() == ours.read_bytes(), (
                f"byte mismatch family={fam} path={path} method={method}"
            )
            if fam == "Z8":
                assert method.startswith("exiftool:"), method
            elif fam in ("Z6ii", "D90"):
                assert method == "rawpy_half", method
            checked += 1
    assert checked >= 1


@pytest.mark.ml
@pytest.mark.sample_data
def test_resolved_method_recorded_per_image(tmp_path, monkeypatch):
    families = _discover_family_nefs()
    samples = []
    for fam, paths in families.items():
        if paths:
            samples.append((fam, paths[0]))
    if len(samples) < 1:
        pytest.skip("No NEFs for resolved-method check")

    monkeypatch.setattr(
        "scripts.research.student_scorer.render_p0.ensure_artifacts_dir",
        lambda run_id=None: tmp_path / "artifacts" / (run_id or "root"),
    )
    rows = []
    for i, (fam, path) in enumerate(samples):
        rows.append({"image_id": i + 1, "path_token": str(path)})
    manifest = _write_mini_manifest(tmp_path / "m", rows)
    out_dir = tmp_path / "cache"
    run_render(manifest_dir=manifest, out_dir=out_dir, workers=1)
    index = json.loads(
        (tmp_path / "artifacts" / "msm_test_render" / "renders" / "render_index.json").read_text()
    )
    by_id = {int(r["image_id"]): r for r in index["images"]}
    for i, (fam, _) in enumerate(samples):
        method = by_id[i + 1]["resolved_method"]
        if fam == "Z8":
            assert str(method).startswith("exiftool:")
        else:
            assert method == "rawpy_half"

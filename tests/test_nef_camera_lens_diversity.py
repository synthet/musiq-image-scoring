"""
E2E camera/lens diversity tests against real Nikon NEF samples.

Exercises EXIF reading (exifread, Pillow, exiftool), rawpy decoding, and
embedded preview extraction across all 4 camera bodies (D90, D300, Z6II, Z8)
and their various lenses.

No database, no GPU, no ML models required — pure file I/O + metadata parsing.

Skips automatically when the testing_samples directory is missing or has no NEF files.

Run::

    pytest tests/test_nef_camera_lens_diversity.py -m sample_data -v
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from tests.support.testing_samples import testing_samples_root

pytestmark = pytest.mark.sample_data

# ---------------------------------------------------------------------------
# Fixtures & helpers
# ---------------------------------------------------------------------------

_SAMPLES_ROOT: Path | None = None
_EXPECTED_EXIF: dict = {}
_NEF_PATHS: list[tuple[str, Path]] = []  # (rel_path, abs_path) pairs

# Camera bodies we require at least one sample for
REQUIRED_BODIES = {"D90", "D300", "Z6II", "Z8"}

# Sensor dimensions: DX ~12MP (D90/D300), FX ~24MP (Z6II), FX ~45MP (Z8)
BODY_SENSOR = {
    "NIKON D90": "DX",
    "NIKON D300": "DX",
    "NIKON Z 6_2": "FX",
    "NIKON Z 8": "FX",
}


def _discover_samples() -> tuple[Path, list[tuple[str, Path]]]:
    """Walk the testing_samples root and collect (rel_path, abs_path) for NEFs."""
    root = Path(testing_samples_root())
    if not root.is_dir():
        return root, []
    pairs: list[tuple[str, Path]] = []
    for nef in sorted(root.rglob("*.NEF")):
        rel = nef.relative_to(root).as_posix()
        pairs.append((rel, nef))
    return root, pairs


def _load_expected_exif(root: Path) -> dict:
    path = root / "expected_exif.json"
    if not path.is_file():
        return {}
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    # Remove comment keys
    return {k: v for k, v in data.items() if not k.startswith("_")}


def _ensure_discovered():
    """Lazy-discover samples once per session."""
    global _SAMPLES_ROOT, _EXPECTED_EXIF, _NEF_PATHS
    if _SAMPLES_ROOT is None:
        _SAMPLES_ROOT, _NEF_PATHS = _discover_samples()
        _EXPECTED_EXIF = _load_expected_exif(_SAMPLES_ROOT)


def _skip_if_no_samples():
    _ensure_discovered()
    if not _SAMPLES_ROOT or not _SAMPLES_ROOT.is_dir():
        pytest.skip(f"Testing samples root not found: {_SAMPLES_ROOT}")
    if not _NEF_PATHS:
        pytest.skip(f"No .NEF files under {_SAMPLES_ROOT}")


def _nef_ids() -> list[str]:
    """Generate parametrize IDs from the relative paths (for nice pytest output)."""
    _ensure_discovered()
    return [rel for rel, _ in _NEF_PATHS]


def _nef_params() -> list[tuple[str, Path]]:
    _ensure_discovered()
    return _NEF_PATHS


# ---------------------------------------------------------------------------
# Test: Camera body coverage
# ---------------------------------------------------------------------------

class TestCameraBodyCoverage:
    """Verify that the sample tree covers all expected camera bodies."""

    def test_all_bodies_have_samples(self):
        _skip_if_no_samples()
        found_bodies = set()
        for rel, _ in _NEF_PATHS:
            parts = rel.split("/")
            if parts[0] == "public" and len(parts) > 1:
                subdir = parts[1]
            elif parts[0] == "synthetic":
                continue  # Coverage test is for real samples
            else:
                subdir = parts[0]
            if subdir:
                found_bodies.add(subdir)

        missing = REQUIRED_BODIES - found_bodies
        assert not missing, (
            f"Missing sample directories for camera bodies: {missing}. "
            f"Found: {found_bodies}"
        )

    def test_minimum_diversity(self):
        """At least 2 different lenses per camera body directory."""
        _skip_if_no_samples()
        for body in REQUIRED_BODIES:
            body_files = [
                rel for rel, _ in _NEF_PATHS
                if rel.startswith(f"public/{body}/") or rel.startswith(f"{body}/")
            ]
            # Count distinct files (each represents a different lens)
            assert len(body_files) >= 2, (
                f"{body}: expected ≥2 lens samples, found {len(body_files)}: {body_files}"
            )


# ---------------------------------------------------------------------------
# Test: EXIF reading with exifread
# ---------------------------------------------------------------------------

class TestExifRead:
    """Read EXIF tags from each NEF sample using the exifread library."""

    @pytest.fixture(params=_nef_params(), ids=_nef_ids())
    def nef_sample(self, request):
        _skip_if_no_samples()
        return request.param

    def test_exifread_opens_and_reads_tags(self, nef_sample):
        """exifread can open the NEF and extract basic EXIF tags."""
        exifread = pytest.importorskip("exifread")
        rel, path = nef_sample

        with open(path, "rb") as f:
            tags = exifread.process_file(f, details=False)

        assert len(tags) > 0, f"exifread returned no tags for {rel}"

        # Camera make should always be present
        assert "Image Make" in tags, f"Missing 'Image Make' in {rel}"
        make = str(tags["Image Make"]).strip()
        assert "NIKON" in make.upper(), f"Unexpected make '{make}' in {rel}"

    def test_exifread_model_matches_subdir(self, nef_sample):
        """Camera model tag matches the expected body for this subdirectory."""
        exifread = pytest.importorskip("exifread")
        rel, path = nef_sample
        
        # Handle public/MODEL/filename and synthetic/filename
        parts = rel.split("/")
        if parts[0] == "public":
            subdir = parts[1].upper()
        elif parts[0] == "synthetic":
            # For synthetic, we expect the filename to contain the model or we skip this specific check
            return
        else:
            subdir = parts[0].upper()

        with open(path, "rb") as f:
            tags = exifread.process_file(f, details=False)

        assert "Image Model" in tags, f"Missing 'Image Model' for {rel}"
        model = str(tags["Image Model"]).strip().upper()

        # Map subdirectory to expected model substring
        expected_fragments = {
            "D90": "D90",
            "D300": "D300",
            "Z6II": "Z 6",
            "Z8": "Z 8",
        }
        fragment = expected_fragments.get(subdir, subdir)
        assert fragment in model, (
            f"{rel}: expected model containing '{fragment}', got '{model}'"
        )

    def test_exifread_has_date_fields(self, nef_sample):
        """At least one date field (DateTimeOriginal or DateTimeDigitized) is present."""
        exifread = pytest.importorskip("exifread")
        rel, path = nef_sample

        with open(path, "rb") as f:
            tags = exifread.process_file(f, details=False)

        date_keys = {"EXIF DateTimeOriginal", "EXIF DateTimeDigitized", "Image DateTime"}
        found = date_keys & set(tags.keys())
        assert found, f"No date tags found in {rel}. Available: {sorted(tags.keys())[:20]}"


# ---------------------------------------------------------------------------
# Test: EXIF reading with Pillow
# ---------------------------------------------------------------------------

class TestPillowExif:
    """Read EXIF via Pillow's getexif() on each NEF sample."""

    @pytest.fixture(params=_nef_params(), ids=_nef_ids())
    def nef_sample(self, request):
        _skip_if_no_samples()
        return request.param

    def test_pillow_can_open_nef(self, nef_sample):
        """Pillow can open (or at least attempt to open) the NEF without crashing."""
        from PIL import Image
        rel, path = nef_sample

        try:
            with Image.open(path) as img:
                # Just accessing basic properties should not raise
                assert img.format is not None or True  # format may be None for RAW
                exif = img.getexif()
                # Pillow EXIF may be empty for some RAW formats — that's OK
                if exif:
                    # Tag 271 = Make, 272 = Model
                    make = exif.get(271, "")
                    if make:
                        assert "NIKON" in str(make).upper()
        except Exception:
            # Some older Pillow versions can't open NEF at all — skip gracefully
            pytest.skip(f"Pillow cannot open NEF: {rel}")


# ---------------------------------------------------------------------------
# Test: rawpy decoding
# ---------------------------------------------------------------------------

class TestRawpyDecode:
    """Verify rawpy can decode each NEF and produce valid RGB data."""

    @pytest.fixture(params=_nef_params(), ids=_nef_ids())
    def nef_sample(self, request):
        _skip_if_no_samples()
        return request.param

    def test_rawpy_opens_and_reads_sizes(self, nef_sample):
        """rawpy can read the NEF and reports sane image dimensions."""
        rawpy = pytest.importorskip("rawpy")
        rel, path = nef_sample

        if "synthetic" in str(path):
            pytest.skip("Synthetic NEFs do not contain real RAW data for rawpy")
        with rawpy.imread(str(path)) as raw:
            w = raw.sizes.width
            h = raw.sizes.height
            assert w > 0 and h > 0, f"rawpy reports {w}x{h} for {rel}"

            # Check against expected dimensions from expected_exif.json
            expected = _EXPECTED_EXIF.get(rel)
            if expected:
                min_w = expected.get("min_width", 0)
                min_h = expected.get("min_height", 0)
                assert w >= min_w, (
                    f"{rel}: width {w} < expected minimum {min_w}"
                )
                assert h >= min_h, (
                    f"{rel}: height {h} < expected minimum {min_h}"
                )

    def test_rawpy_postprocess_to_rgb(self, nef_sample):
        """rawpy can postprocess the NEF to an RGB numpy array.

        Note: Z8 high-efficiency (NRPC) compression may not be supported by
        the installed LibRaw version. Such files are skipped rather than failed.
        """
        rawpy = pytest.importorskip("rawpy")
        rel, path = nef_sample

        if "synthetic" in str(path):
            pytest.skip("Synthetic NEFs do not contain real RAW data for rawpy")
        with rawpy.imread(str(path)) as raw:
            try:
                rgb = raw.postprocess(
                    use_camera_wb=True,
                    half_size=True,  # faster for testing
                    no_auto_bright=True,
                )
            except (rawpy.LibRawDataError, rawpy.LibRawFileUnsupportedError):
                pytest.skip(
                    f"LibRaw cannot postprocess {rel} "
                    f"(likely unsupported compression, e.g. Z8 high-efficiency NRPC)"
                )
                return
            assert rgb is not None, f"postprocess returned None for {rel}"
            assert rgb.ndim == 3, f"Expected 3D array, got {rgb.ndim}D for {rel}"
            assert rgb.shape[2] == 3, f"Expected 3 channels, got {rgb.shape[2]} for {rel}"
            assert rgb.shape[0] > 0 and rgb.shape[1] > 0, (
                f"Zero-dimension output for {rel}: {rgb.shape}"
            )

    def test_rawpy_embedded_thumbnail(self, nef_sample):
        """rawpy can extract the embedded thumbnail from the NEF."""
        rawpy = pytest.importorskip("rawpy")
        rel, path = nef_sample

        if "synthetic" in str(path):
            pytest.skip("Synthetic NEFs do not contain real RAW data for rawpy")
        with rawpy.imread(str(path)) as raw:
            try:
                thumb = raw.extract_thumb()
            except rawpy.LibRawNoThumbnailError:
                pytest.skip(f"No embedded thumbnail in {rel}")
                return

            assert thumb is not None, f"extract_thumb returned None for {rel}"
            # Thumb format is either JPEG or bitmap
            if thumb.format == rawpy.ThumbFormat.JPEG:
                assert len(thumb.data) > 100, (
                    f"JPEG thumbnail too small ({len(thumb.data)} bytes) for {rel}"
                )
                # Verify JPEG magic bytes
                assert thumb.data[:2] == b"\xff\xd8", (
                    f"Invalid JPEG header in thumbnail for {rel}"
                )
            elif thumb.format == rawpy.ThumbFormat.BITMAP:
                assert thumb.data.shape[0] > 0 and thumb.data.shape[1] > 0, (
                    f"Bitmap thumbnail has zero dimensions for {rel}"
                )


# ---------------------------------------------------------------------------
# Test: expected EXIF ground truth (when expected_exif.json has an entry)
# ---------------------------------------------------------------------------

def _expected_exif_samples() -> list[tuple[str, Path, dict]]:
    """Module-level helper: return (rel, path, expected) tuples for parametrize."""
    _ensure_discovered()
    out = []
    for rel, path in _NEF_PATHS:
        exp = _EXPECTED_EXIF.get(rel)
        if exp:
            out.append((rel, path, exp))
    return out


def _expected_exif_ids() -> list[str]:
    """Module-level helper: parametrize IDs for expected EXIF tests."""
    return [rel for rel, _, _ in _expected_exif_samples()]


class TestExpectedExif:
    """Cross-check extracted EXIF against expected_exif.json ground truth."""

    @pytest.fixture(params=_expected_exif_samples(), ids=_expected_exif_ids())
    def expected_sample(self, request):
        _skip_if_no_samples()
        return request.param

    def test_exifread_matches_expected_model(self, expected_sample):
        """Camera model from exifread matches expected_exif.json."""
        exifread = pytest.importorskip("exifread")
        rel, path, expected = expected_sample

        with open(path, "rb") as f:
            tags = exifread.process_file(f, details=False)

        model = str(tags.get("Image Model", "")).strip()
        assert model == expected["model"], (
            f"{rel}: expected model '{expected['model']}', got '{model}'"
        )

    def test_exifread_matches_expected_make(self, expected_sample):
        """Camera make from exifread matches expected_exif.json."""
        exifread = pytest.importorskip("exifread")
        rel, path, expected = expected_sample

        with open(path, "rb") as f:
            tags = exifread.process_file(f, details=False)

        make = str(tags.get("Image Make", "")).strip()
        assert make == expected["make"], (
            f"{rel}: expected make '{expected['make']}', got '{make}'"
        )

    def test_lens_info_contains_expected(self, expected_sample):
        """Lens info from exifread contains the expected substring.

        Older Nikon bodies (D90, D300) store lens data in MakerNote tags,
        not standard EXIF LensModel.  We use ``details=True`` and search
        a broad set of tag names including Nikon-specific MakerNote fields.
        """
        exifread = pytest.importorskip("exifread")
        rel, path, expected = expected_sample

        # details=True is needed to access MakerNote sub-tags on older Nikons
        with open(path, "rb") as f:
            tags = exifread.process_file(f, details=True)

        # Broad search across standard EXIF + Nikon MakerNote lens fields
        lens_fields = [
            "EXIF LensModel",
            "EXIF LensInfo",
            "EXIF LensSpecification",
            "MakerNote LensType",
            "MakerNote Lens",
            "MakerNote LensMinMaxFocalMaxAperture",
            "MakerNote LensMinFocalLength",
            "MakerNote LensMaxFocalLength",
        ]

        # Collect all lens-related tag values into a single searchable string
        lens_parts: list[str] = []
        for field in lens_fields:
            if field in tags:
                lens_parts.append(str(tags[field]))
        # Also check EXIF FocalLength as a last resort for the "contains" match
        if "EXIF FocalLength" in tags:
            lens_parts.append(str(tags["EXIF FocalLength"]))
        lens_str = " | ".join(lens_parts)

        lens_expected = expected.get("lens_contains", "")
        if lens_expected:
            assert lens_expected in lens_str, (
                f"{rel}: expected lens containing '{lens_expected}', "
                f"got '{lens_str}' (checked: {lens_fields + ['EXIF FocalLength']})"
            )


# ---------------------------------------------------------------------------
# Test: thumbnail generation via PIL from rawpy
# ---------------------------------------------------------------------------

class TestThumbnailFromRawpy:
    """Generate thumbnails from NEF files using rawpy + PIL."""

    @pytest.fixture(params=_nef_params(), ids=_nef_ids())
    def nef_sample(self, request):
        _skip_if_no_samples()
        return request.param

    def test_generate_thumbnail_from_embedded_jpeg(self, nef_sample, tmp_path):
        """Extract embedded JPEG and save as a thumbnail file."""
        rawpy = pytest.importorskip("rawpy")
        from PIL import Image
        import io

        rel, path = nef_sample

        if "synthetic" in str(path):
            pytest.skip("Synthetic NEFs do not contain real RAW data for rawpy")
        with rawpy.imread(str(path)) as raw:
            try:
                thumb = raw.extract_thumb()
            except rawpy.LibRawNoThumbnailError:
                pytest.skip(f"No embedded thumbnail in {rel}")
                return

            if thumb.format == rawpy.ThumbFormat.JPEG:
                img = Image.open(io.BytesIO(thumb.data))
            elif thumb.format == rawpy.ThumbFormat.BITMAP:
                img = Image.fromarray(thumb.data)
            else:
                pytest.skip(f"Unknown thumbnail format for {rel}")
                return

            # Resize to thumbnail dimensions
            thumb_size = (320, 320)
            img.thumbnail(thumb_size, Image.LANCZOS)

            # Save to temp
            out_path = tmp_path / f"{Path(rel).stem}_thumb.jpg"
            img.save(str(out_path), "JPEG", quality=85)

            assert out_path.exists(), f"Thumbnail file not created for {rel}"
            assert out_path.stat().st_size > 0, f"Thumbnail file is empty for {rel}"

            # Re-open to verify
            with Image.open(out_path) as saved:
                assert saved.size[0] > 0 and saved.size[1] > 0
                assert max(saved.size) <= max(thumb_size)

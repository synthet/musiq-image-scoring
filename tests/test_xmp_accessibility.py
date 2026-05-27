"""Round-trip tests for IPTC accessibility fields in XMP sidecars."""

from modules import xmp


def _image_path(tmp_path, name="photo.jpg"):
    return str(tmp_path / name)


def test_write_read_accessibility_roundtrip(tmp_path):
    img = _image_path(tmp_path)
    alt = "A red barn beside a field at sunset."
    extended = "A rural scene with a barn. Keywords: barn, sunset."

    assert xmp.write_metadata_unified(
        img,
        alt_text=alt,
        extended_description=extended,
        use_sidecar=True,
        use_embedded=False,
    ) is True

    data = xmp.read_xmp_full(img)
    assert data["alt_text"] == alt
    assert data["extended_description"] == extended


def test_read_accessibility_empty_when_missing(tmp_path):
    img = _image_path(tmp_path)
    xmp.write_rating(img, 3)
    data = xmp.read_xmp_full(img)
    assert data["alt_text"] is None
    assert data["extended_description"] is None


def test_overwrite_accessibility_updates_sidecar(tmp_path):
    img = _image_path(tmp_path)
    xmp.write_metadata_unified(
        img,
        alt_text="First alt.",
        extended_description="First extended.",
        use_sidecar=True,
        use_embedded=False,
    )
    xmp.write_metadata_unified(
        img,
        alt_text="Second alt.",
        extended_description="Second extended.",
        use_sidecar=True,
        use_embedded=False,
    )
    data = xmp.read_xmp_full(img)
    assert data["alt_text"] == "Second alt."
    assert data["extended_description"] == "Second extended."

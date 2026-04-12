"""Parity tests for ``camera_folder_from_exif_model`` — mirror ``image-scoring-gallery/electron/cameraFolderName.test.ts``."""

import pytest

from modules.camera_folder_name import camera_folder_from_exif_model


@pytest.mark.parametrize(
    ("model", "expected"),
    [
        (None, "unknown"),
        ("", "unknown"),
        ("unknown", "unknown"),
        ("Nikon Z 8", "Z8"),
        ("NIKON Z 6 II", "Z6ii"),
        ("NIKON Z 6_2", "Z6ii"),
        ("nikon z 6", "Z6ii"),  # override
        ("NIKON D300", "D300"),
        ("Nikon D90", "D90"),
        ("D500", "D500"),
        ("Canon EOS R5", "R5"),
        ("NIKON D800E", "D800"),  # trailing letter not in S|X|H pattern
    ],
)
def test_camera_folder_from_exif_model(model, expected):
    assert camera_folder_from_exif_model(model) == expected

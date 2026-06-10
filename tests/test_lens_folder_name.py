"""Parity tests for ``lens_folder_from_exif_model`` — mirror ``image-scoring-gallery/electron/lensFolderName.test.ts``."""

import pytest

from modules.lens_folder_name import UNKNOWN_LENS_FOLDER, lens_folder_from_exif_model


@pytest.mark.parametrize(
    ("lens_model", "expected"),
    [
        ("NIKKOR Z 180-600mm f/5.6-6.3 VR", "180-600mm"),
        ("NIKKOR Z 180-600mm f_5.6-6.3 VR", "180-600mm"),
        ("NIKKOR Z 105mm f/2.8", "105mm"),
        ("Some 10.5mm lens", "10.5mm"),
        ("24-70mm f/2.8", "24-70mm"),
        ("NIKKOR 35mm f/1.8", "35mm"),
        ("35 35 1.8 1.8", "35mm"),
        ("35 35 2 2", "35mm"),
        ("50 50 1.4 1.4", "50mm"),
        ("50 50 1.8 1.8", "50mm"),
        ("28 105 3.5 4.5", "28-105mm"),
        ("28 70 2.8 2.8", "28-70mm"),
        ("10.5 10.5 2.8 2.8", "10.5mm"),
        (None, UNKNOWN_LENS_FOLDER),
        ("", UNKNOWN_LENS_FOLDER),
        ("   ", UNKNOWN_LENS_FOLDER),
        ("FTZ Adapter", "FTZ Adapter"),
    ],
)
def test_lens_folder_from_exif_model(lens_model, expected):
    assert lens_folder_from_exif_model(lens_model) == expected

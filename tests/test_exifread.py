import sys
import os
from pathlib import Path
import pytest

pytest.importorskip("exifread")
import exifread

pytestmark = [pytest.mark.sample_data]

def _get_public_samples():
    root = Path("tests/fixtures/testing_samples/public")
    if not root.exists():
        return []
    return list(root.rglob("*.NEF"))

@pytest.mark.parametrize("sample_path", _get_public_samples(), ids=lambda p: p.name)
def test_exif_reading(sample_path):
    print(f"Testing {sample_path} with exifread")

    try:
        with open(sample_path, 'rb') as f:
            tags = exifread.process_file(f, details=False)
            print(f"Found {len(tags)} tags")
            assert len(tags) > 0, f"No tags found in {sample_path}"
            
            # Check standard EXIF tags for date
            keys_to_check = ['EXIF DateTimeOriginal', 'EXIF DateTimeDigitized', 'Image DateTime']
            found_any = False
            for k in keys_to_check:
                if k in tags:
                    print(f"{k}: {tags[k]}")
                    found_any = True
            
            # Note: Some samples might not have these tags if they were stripped,
            # but usually Nikon RAWs have them.
            if not found_any:
                print(f"Warning: No date tags found in {sample_path}")
                    
    except Exception as e:
        pytest.fail(f"exifread processing failed for {sample_path}: {e}")

if __name__ == "__main__":
    for sample in _get_public_samples():
        test_exif_reading(sample)

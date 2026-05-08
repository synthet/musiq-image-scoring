import sys
import os
from pathlib import Path
import pytest
try:
    from modules import thumbnails
except ImportError:
    # Fix import path for script execution
    sys.path.append(os.getcwd())
    from modules import thumbnails

pytestmark = [pytest.mark.wsl, pytest.mark.sample_data]

def _get_public_samples():
    root = Path("tests/fixtures/testing_samples/public")
    if not root.exists():
        return []
    return list(root.rglob("*.NEF"))

@pytest.mark.parametrize("sample_path", _get_public_samples(), ids=lambda p: p.name)
def test_thumbnail_generation(sample_path):
    print(f"Generating thumbnail for: {sample_path}")
    try:
        thumb_path = thumbnails.generate_thumbnail(str(sample_path))
        print(f"Result Path: {thumb_path}")
        assert thumb_path and os.path.exists(thumb_path), f"Thumbnail does not exist for {sample_path}"
        print("Success: Thumbnail exists.")
    except Exception as e:
        pytest.fail(f"Exception during thumbnail generation for {sample_path}: {e}")

if __name__ == "__main__":
    # Allow manual execution
    for sample in _get_public_samples():
        test_thumbnail_generation(sample)

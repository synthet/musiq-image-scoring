import sys
import os
import pytest
try:
    from modules import thumbnails
except ImportError:
    # Fix import path for script execution
    sys.path.append(os.getcwd())
    from modules import thumbnails

pytestmark = pytest.mark.wsl


def test_thumbnail_generation():
    print("Thumbnails module imported.")

    # Test file from logs
    # Use a mock path or find one generally, but don't exit if not found
    test_file = "/mnt/d/Photos/Z6ii/28-400mm/2025/2025-11-18/DSC_6332.NEF"

    if not os.path.exists(test_file):
        print(f"Test file not found: {test_file}")
        # Try finding any NEF file
        import glob
        # Check both Windows and WSL paths if possible, but keep simple
        files = glob.glob("D:/Photos/**/*.NEF", recursive=True)
        if not files:
             files = glob.glob("/mnt/d/Photos/**/*.NEF", recursive=True)
             
        if files:
            test_file = files[0]
            print(f"Using alternative file: {test_file}")
        else:
            print("No NEF files found to test.")
            if "pytest" in sys.modules:
                pytest.skip("No NEF files found for testing")
            return

    print(f"Generating thumbnail for: {test_file}")
    try:
        thumb_path = thumbnails.generate_thumbnail(test_file)
        print(f"Result Path: {thumb_path}")
        if thumb_path and os.path.exists(thumb_path):
            print("Success: Thumbnail exists.")
        else:
            print("Failure: Thumbnail does not exist.")
            if "pytest" in sys.modules:
                pytest.fail("Thumbnail generation failed")
    except Exception as e:
        print(f"Exception: {e}")
        if "pytest" in sys.modules:
            pytest.fail(f"Exception during thumbnail generation: {e}")

if __name__ == "__main__":
    test_thumbnail_generation()


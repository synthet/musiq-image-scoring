import sys
import os
import datetime
import importlib
import pytest

pytestmark = pytest.mark.wsl

try:
    import rawpy
    print(f"rawpy version: {rawpy.__version__}")
except ImportError:
    print("rawpy not installed")


if __name__ == "__main__":
    TARGET_FILE = r"D:/Photos/Z8/180-600mm/2025/2025-11-01/DSC_3953.NEF"

    if not os.path.exists(TARGET_FILE):
        print("File not found")
        sys.exit(1)

    print(f"Testing {TARGET_FILE}")

    # Test rawpy direct
    try:
        with rawpy.imread(TARGET_FILE) as raw:
            print(f"Sizes: {raw.sizes}")
            try:
                print(f"img_other.timestamp: {raw.img_other.timestamp}")
                print(f"Converted: {datetime.datetime.fromtimestamp(raw.img_other.timestamp)}")
            except Exception as e:
                print(f"img_other.timestamp error: {e}")
            
            # Check other props?
            print(dir(raw))
    except Exception as e:
        print(f"rawpy error: {e}")

    # Test utils function
    sys.path.append(os.getcwd())
    try:
        from modules import utils
        print(f"Utils result: {utils.get_image_creation_time(TARGET_FILE)}")
    except ImportError:
        print("Could not import modules.utils")

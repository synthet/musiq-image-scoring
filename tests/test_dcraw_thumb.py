import subprocess
import os
import pytest

pytestmark = pytest.mark.wsl

target_file = "/mnt/d/Photos/Z8/180-600mm/2025/2025-11-16/DSC_6008.NEF"

def test_extract():
    print(f"Testing extraction on {target_file}")
    if not os.path.exists(target_file):
        print("File not found")
        return

    # Try extraction to stdout
    cmd = ["dcraw", "-e", "-c", target_file]
    print(f"Running: {' '.join(cmd)}")
    
    res = subprocess.run(cmd, capture_output=True, text=False)
    print(f"Return code: {res.returncode}")
    print(f"Output size: {len(res.stdout)} bytes")
    
    if len(res.stdout) > 0:
        header = res.stdout[:2]
        print(f"Header: {header.hex()}")
        if header == b'\xff\xd8':
            print("Valid JPEG header detected.")
        else:
            print("Not a JPEG.")
            
if __name__ == "__main__":
    test_extract()

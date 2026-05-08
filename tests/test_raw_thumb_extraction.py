import subprocess
import shutil
import os
from pathlib import Path
import pytest

pytestmark = [pytest.mark.wsl, pytest.mark.sample_data]

def _get_public_samples():
    root = Path("tests/fixtures/testing_samples/public")
    if not root.exists():
        return []
    return list(root.rglob("*.NEF"))

@pytest.mark.parametrize("sample_path", _get_public_samples(), ids=lambda p: p.name)
def test_extract_dcraw(sample_path):
    if not shutil.which("dcraw"):
        pytest.skip("dcraw not found in PATH")
        
    print(f"Testing dcraw extraction on {sample_path}")
    
    cmd = ["dcraw", "-e", "-c", str(sample_path)]
    res = subprocess.run(cmd, capture_output=True, text=False)
    assert res.returncode == 0, f"dcraw failed with error: {res.stderr}"
    assert len(res.stdout) > 0, f"No output from dcraw for {sample_path}"
    assert res.stdout.startswith(b'\xff\xd8'), f"Not a valid JPEG header from dcraw: {res.stdout[:2].hex()}"

@pytest.mark.parametrize("sample_path", _get_public_samples(), ids=lambda p: p.name)
def test_extract_exiftool(sample_path):
    if not shutil.which("exiftool"):
        pytest.skip("exiftool not found in PATH")
        
    print(f"Testing exiftool extraction on {sample_path}")
    
    # Try -JpgFromRaw or -PreviewImage
    found = False
    for tag in ["-JpgFromRaw", "-PreviewImage"]:
        cmd = ["exiftool", "-b", tag, str(sample_path)]
        res = subprocess.run(cmd, capture_output=True, text=False)
        if res.returncode == 0 and len(res.stdout) > 0 and res.stdout.startswith(b'\xff\xd8'):
            found = True
            break
            
    assert found, f"exiftool failed to extract a valid JPEG preview from {sample_path}"

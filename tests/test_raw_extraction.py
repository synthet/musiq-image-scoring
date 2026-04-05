#!/usr/bin/env python3
"""
Test script for RAW embedded JPEG extraction methods.
Tests ExifTool, dcraw, and rawpy extraction on various Nikon RAW formats.

Usage:
    python tests/test_raw_extraction.py <path_to_nef_file>
    python tests/test_raw_extraction.py /mnt/d/Projects/image-scoring-backend/tests/fixtures/testing_samples/Z8/example.NEF
"""

import os
import sys
import time
from pathlib import Path

import pytest

pytestmark = [pytest.mark.wsl, pytest.mark.sample_data]

if sys.platform.startswith("win"):
    pytest.skip("WSL-only (RAW extraction relies on Linux tooling like dcraw/exiftool)", allow_module_level=True)

# Add project root to path
project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from modules import thumbnails


def run_extraction_methods(nef_path: str) -> bool:
    """Test all extraction methods on a NEF file."""
    print("=" * 70)
    print(f"Testing RAW extraction methods on: {nef_path}")
    print("=" * 70)
    
    if not os.path.exists(nef_path):
        print(f"✗ File not found: {nef_path}")
        return False
    
    file_size = os.path.getsize(nef_path)
    print(f"\nFile size: {file_size / 1024 / 1024:.2f} MB")
    
    results = []
    
    # Test extract_embedded_jpeg() helper (combines ExifTool + dcraw)
    print("\n" + "-" * 70)
    print("Test 1: extract_embedded_jpeg() (ExifTool → dcraw)")
    print("-" * 70)
    try:
        start_time = time.time()
        img = thumbnails.extract_embedded_jpeg(nef_path, min_size=1000)
        elapsed = time.time() - start_time
        
        if img:
            print(f"✓ Success in {elapsed:.3f}s")
            print(f"  Dimensions: {img.width}x{img.height}")
            print(f"  Mode: {img.mode}")
            results.append(("extract_embedded_jpeg", True, elapsed, img.size))
        else:
            print(f"✗ Failed (no image returned)")
            results.append(("extract_embedded_jpeg", False, elapsed, None))
    except Exception as e:
        print(f"✗ Error: {e}")
        results.append(("extract_embedded_jpeg", False, 0, None))
    
    # Test thumbnail generation
    print("\n" + "-" * 70)
    print("Test 2: generate_thumbnail()")
    print("-" * 70)
    try:
        # Remove existing thumbnail if any
        thumb_path = thumbnails.get_thumb_path(nef_path)
        if os.path.exists(thumb_path):
            os.remove(thumb_path)
        
        start_time = time.time()
        result_path = thumbnails.generate_thumbnail(nef_path)
        elapsed = time.time() - start_time
        
        if result_path and os.path.exists(result_path):
            from PIL import Image
            thumb_img = Image.open(result_path)
            print(f"✓ Success in {elapsed:.3f}s")
            print(f"  Thumbnail path: {result_path}")
            print(f"  Dimensions: {thumb_img.width}x{thumb_img.height}")
            results.append(("generate_thumbnail", True, elapsed, thumb_img.size))
        else:
            print(f"✗ Failed (no thumbnail generated)")
            results.append(("generate_thumbnail", False, elapsed, None))
    except Exception as e:
        print(f"✗ Error: {e}")
        results.append(("generate_thumbnail", False, 0, None))
    
    # Test preview generation
    print("\n" + "-" * 70)
    print("Test 3: generate_preview()")
    print("-" * 70)
    try:
        # Remove existing preview if any
        preview_path = thumbnails.get_preview_filename(nef_path)
        if os.path.exists(preview_path):
            os.remove(preview_path)
        
        start_time = time.time()
        result_path = thumbnails.generate_preview(nef_path)
        elapsed = time.time() - start_time
        
        if result_path and os.path.exists(result_path):
            from PIL import Image
            preview_img = Image.open(result_path)
            print(f"✓ Success in {elapsed:.3f}s")
            print(f"  Preview path: {result_path}")
            print(f"  Dimensions: {preview_img.width}x{preview_img.height}")
            file_size_preview = os.path.getsize(result_path)
            print(f"  Preview size: {file_size_preview / 1024:.1f} KB")
            results.append(("generate_preview", True, elapsed, preview_img.size))
        else:
            print(f"✗ Failed (no preview generated)")
            results.append(("generate_preview", False, elapsed, None))
    except Exception as e:
        print(f"✗ Error: {e}")
        results.append(("generate_preview", False, 0, None))
    
    # Summary
    print("\n" + "=" * 70)
    print("Summary")
    print("=" * 70)
    print(f"{'Method':<30} {'Status':<10} {'Time (s)':<12} {'Dimensions':<20}")
    print("-" * 70)
    for method, success, elapsed, size in results:
        status = "✓ PASS" if success else "✗ FAIL"
        dims = f"{size[0]}x{size[1]}" if size else "N/A"
        print(f"{method:<30} {status:<10} {elapsed:<12.3f} {dims:<20}")
    
    all_passed = all(success for _, success, _, _ in results)
    return all_passed


def test_extraction_methods_from_env():
    """
    Run RAW extraction tests against a user-provided RAW file.

    Configure the file path via:
      - IMAGE_SCORING_TEST_RAW_FILE=/mnt/d/Photos/.../DSC_0001.NEF
    """
    raw_file = os.environ.get("IMAGE_SCORING_TEST_RAW_FILE")
    if not raw_file:
        pytest.skip("Set IMAGE_SCORING_TEST_RAW_FILE to run RAW extraction tests")

    if not os.path.exists(raw_file):
        pytest.skip(f"RAW test file not found: {raw_file}")

    assert run_extraction_methods(raw_file), "Extraction methods failed"



def test_extraction_methods_pytest():
    # Backwards compatible name; now driven by IMAGE_SCORING_TEST_RAW_FILE.
    raw_file = os.environ.get("IMAGE_SCORING_TEST_RAW_FILE")
    if not raw_file:
        pytest.skip("Set IMAGE_SCORING_TEST_RAW_FILE to run RAW extraction tests")
    if not os.path.exists(raw_file):
        pytest.skip(f"RAW test file not found: {raw_file}")

    assert run_extraction_methods(raw_file), "Extraction methods failed"



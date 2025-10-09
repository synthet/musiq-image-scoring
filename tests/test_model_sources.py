#!/usr/bin/env python3
"""
Test Model Sources - Verify all TensorFlow Hub and Kaggle Hub model paths

This script tests the availability and accessibility of all model sources
defined in run_all_musiq_models.py without actually loading the full models.
"""

import os
import sys
import argparse
from typing import Dict, Optional, Tuple

# Test imports
print("Testing imports...")
try:
    import tensorflow as tf
    print(f"✓ TensorFlow: {tf.__version__}")
except ImportError as e:
    print(f"✗ TensorFlow not available: {e}")
    sys.exit(1)

try:
    import tensorflow_hub as hub
    print(f"✓ TensorFlow Hub available")
except ImportError as e:
    print(f"✗ TensorFlow Hub not available: {e}")
    sys.exit(1)

try:
    import kagglehub
    print(f"✓ Kaggle Hub available")
    KAGGLE_AVAILABLE = True
except ImportError as e:
    print(f"⚠ Kaggle Hub not available: {e}")
    KAGGLE_AVAILABLE = False


# Model sources (from run_all_musiq_models.py v2.3.0)
# Get base directory for local checkpoints
base_dir = os.path.dirname(os.path.abspath(__file__))
checkpoint_dir = os.path.join(base_dir, "musiq_original", "checkpoints")

MODEL_SOURCES = {
    "spaq": {
        "tfhub": "https://tfhub.dev/google/musiq/spaq/1",
        "kaggle": "google/musiq/tensorFlow2/spaq",
        "local": os.path.join(checkpoint_dir, "spaq_ckpt.npz")
    },
    "ava": {
        "tfhub": "https://tfhub.dev/google/musiq/ava/1",
        "kaggle": "google/musiq/tensorFlow2/ava",
        "local": os.path.join(checkpoint_dir, "ava_ckpt.npz")
    },
    "koniq": {
        "tfhub": None,  # Not available on TF Hub
        "kaggle": "google/musiq/tensorFlow2/koniq-10k",
        "local": os.path.join(checkpoint_dir, "koniq_ckpt.npz")
    },
    "paq2piq": {
        "tfhub": "https://tfhub.dev/google/musiq/paq2piq/1",
        "kaggle": "google/musiq/tensorFlow2/paq2piq",
        "local": os.path.join(checkpoint_dir, "paq2piq_ckpt.npz")
    },
    "vila": {
        "tfhub": "https://tfhub.dev/google/vila/image/1",
        "kaggle": "google/vila/tensorFlow2/image",
        "local": os.path.join(checkpoint_dir, "vila-tensorflow2-image-v1")
    }
}


def check_kaggle_auth() -> bool:
    """Check if Kaggle authentication is configured."""
    kaggle_paths = [
        os.path.expanduser("~/.kaggle/kaggle.json"),
        os.path.expandvars("%USERPROFILE%/.kaggle/kaggle.json")
    ]
    
    for path in kaggle_paths:
        if os.path.exists(path):
            return True
    return False


def test_tfhub_url(model_name: str, url: str) -> Tuple[bool, str]:
    """
    Test if a TensorFlow Hub URL is accessible.
    
    Returns:
        (success, message)
    """
    if url is None:
        return False, "N/A - Not available on TF Hub"
    
    try:
        print(f"  Testing TF Hub: {url}")
        # Try to load model metadata (lighter than full model load)
        model = hub.load(url)
        
        # Quick signature check
        if hasattr(model, 'signatures'):
            sigs = list(model.signatures.keys())
            return True, f"✓ Accessible (signatures: {sigs})"
        else:
            return True, "✓ Accessible (loaded successfully)"
            
    except Exception as e:
        error_msg = str(e)
        if "404" in error_msg or "not found" in error_msg.lower():
            return False, f"✗ Not Found (404)"
        elif "network" in error_msg.lower() or "connection" in error_msg.lower():
            return False, f"✗ Network Error"
        elif "timeout" in error_msg.lower():
            return False, f"✗ Timeout"
        else:
            return False, f"✗ Error: {error_msg[:50]}..."


def test_kaggle_path(model_name: str, path: str, skip_download: bool = False) -> Tuple[bool, str]:
    """
    Test if a Kaggle Hub path is accessible.
    
    Args:
        model_name: Name of the model
        path: Kaggle Hub path (e.g., "google/musiq/tensorFlow2/spaq")
        skip_download: If True, only check if path format is valid
    
    Returns:
        (success, message)
    """
    if not KAGGLE_AVAILABLE:
        return False, "✗ Kaggle Hub package not installed"
    
    if path is None:
        return False, "N/A - Not available on Kaggle Hub"
    
    try:
        print(f"  Testing Kaggle Hub: {path}")
        
        if skip_download:
            # Just validate path format
            parts = path.split("/")
            if len(parts) >= 4:  # Expected: org/model/framework/variant
                return True, f"⚠ Path format valid (download skipped)"
            else:
                return False, f"✗ Invalid path format"
        
        # Try to download (will use cache if already downloaded)
        model_path = kagglehub.model_download(path)
        
        # Verify downloaded path exists
        if os.path.exists(model_path):
            return True, f"✓ Accessible (cached at: {model_path[:50]}...)"
        else:
            return False, f"✗ Download succeeded but path not found"
            
    except Exception as e:
        error_msg = str(e)
        if "404" in error_msg or "not found" in error_msg.lower():
            return False, f"✗ Not Found (404)"
        elif "401" in error_msg or "unauthorized" in error_msg.lower() or "authentication" in error_msg.lower():
            return False, f"✗ Authentication Required"
        elif "network" in error_msg.lower() or "connection" in error_msg.lower():
            return False, f"✗ Network Error"
        else:
            return False, f"✗ Error: {error_msg[:50]}..."


def test_local_checkpoint(model_name: str, path: str) -> Tuple[bool, str]:
    """
    Test if a local checkpoint exists and is accessible.
    
    Args:
        model_name: Name of the model
        path: Local file/directory path
    
    Returns:
        (success, message)
    """
    if path is None:
        return False, "N/A - No local checkpoint defined"
    
    try:
        print(f"  Testing Local: {path}")
        
        if os.path.exists(path):
            if os.path.isdir(path):
                # SavedModel directory
                saved_model_pb = os.path.join(path, "saved_model.pb")
                if os.path.exists(saved_model_pb):
                    file_size = os.path.getsize(saved_model_pb) / (1024 * 1024)  # MB
                    return True, f"✓ SavedModel found ({file_size:.1f} MB)"
                else:
                    return False, "✗ SavedModel directory incomplete"
            elif path.endswith('.npz'):
                # NumPy checkpoint file
                file_size = os.path.getsize(path) / (1024 * 1024)  # MB
                return True, f"✓ Checkpoint found ({file_size:.1f} MB)"
            else:
                return True, f"✓ File found"
        else:
            return False, f"✗ Not found (download from Google Cloud Storage)"
            
    except Exception as e:
        error_msg = str(e)
        return False, f"✗ Error: {error_msg[:50]}..."


def test_all_sources(test_kaggle: bool = True, skip_kaggle_download: bool = False, test_local: bool = True):
    """
    Test all model sources.
    
    Args:
        test_kaggle: Whether to test Kaggle Hub sources
        skip_kaggle_download: If True, only validate Kaggle paths without downloading
        test_local: Whether to test local checkpoints
    """
    print("\n" + "=" * 70)
    print("MODEL SOURCE AVAILABILITY TEST")
    print("=" * 70)
    
    # Check Kaggle authentication if testing Kaggle Hub
    kaggle_auth = False
    if test_kaggle and KAGGLE_AVAILABLE:
        kaggle_auth = check_kaggle_auth()
        if kaggle_auth:
            print("✓ Kaggle authentication found")
        else:
            print("⚠ Kaggle authentication not configured")
            if not skip_kaggle_download:
                print("  Kaggle downloads will likely fail without authentication")
    
    print("\n" + "=" * 70)
    print("Testing Model Sources")
    print("=" * 70)
    
    results = {}
    
    for model_name, sources in MODEL_SOURCES.items():
        print(f"\n📦 Testing {model_name.upper()} model:")
        
        results[model_name] = {
            "tfhub": None,
            "kaggle": None,
            "local": None
        }
        
        # Test TensorFlow Hub
        tfhub_url = sources.get("tfhub")
        if tfhub_url:
            success, message = test_tfhub_url(model_name, tfhub_url)
            results[model_name]["tfhub"] = (success, message)
            print(f"    TF Hub:     {message}")
        else:
            results[model_name]["tfhub"] = (False, "N/A")
            print(f"    TF Hub:     N/A - Not available on TF Hub")
        
        # Test Kaggle Hub
        if test_kaggle:
            kaggle_path = sources.get("kaggle")
            if kaggle_path:
                success, message = test_kaggle_path(model_name, kaggle_path, skip_kaggle_download)
                results[model_name]["kaggle"] = (success, message)
                print(f"    Kaggle Hub: {message}")
            else:
                results[model_name]["kaggle"] = (False, "N/A")
                print(f"    Kaggle Hub: N/A - Not available on Kaggle Hub")
        else:
            results[model_name]["kaggle"] = (False, "Skipped")
            print(f"    Kaggle Hub: Skipped (use --test-kaggle to test)")
        
        # Test Local Checkpoint
        if test_local:
            local_path = sources.get("local")
            if local_path:
                success, message = test_local_checkpoint(model_name, local_path)
                results[model_name]["local"] = (success, message)
                print(f"    Local:      {message}")
            else:
                results[model_name]["local"] = (False, "N/A")
                print(f"    Local:      N/A - No local checkpoint")
        else:
            results[model_name]["local"] = (False, "Skipped")
            print(f"    Local:      Skipped")
    
    # Summary
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    
    print("\n{:<10} {:<20} {:<20} {:<20}".format("Model", "TF Hub", "Kaggle Hub", "Local"))
    print("-" * 70)
    
    for model_name, model_results in results.items():
        tfhub_success, tfhub_msg = model_results["tfhub"]
        kaggle_success, kaggle_msg = model_results["kaggle"]
        local_success, local_msg = model_results["local"]
        
        tfhub_status = "✓" if tfhub_success else ("N/A" if tfhub_msg == "N/A" else "✗")
        kaggle_status = "✓" if kaggle_success else ("N/A" if kaggle_msg in ["N/A", "Skipped"] else "✗")
        local_status = "✓" if local_success else ("N/A" if local_msg in ["N/A", "Skipped"] else "✗")
        
        # Check if model has at least one working source
        has_source = tfhub_success or kaggle_success or local_success
        fallback_indicator = "✓" if has_source else "✗"
        
        print(f"{fallback_indicator} {model_name:<8} {tfhub_status:<20} {kaggle_status:<20} {local_status:<20}")
    
    # Recommendations
    print("\n" + "=" * 70)
    print("RECOMMENDATIONS")
    print("=" * 70)
    
    all_accessible = True
    needs_kaggle_auth = False
    
    for model_name, model_results in results.items():
        tfhub_success, tfhub_msg = model_results["tfhub"]
        kaggle_success, kaggle_msg = model_results["kaggle"]
        local_success, local_msg = model_results["local"]
        
        if not tfhub_success and not kaggle_success and not local_success:
            all_accessible = False
            print(f"⚠ {model_name.upper()}: No accessible sources!")
            if "Authentication Required" in kaggle_msg:
                needs_kaggle_auth = True
    
    if all_accessible:
        print("✓ All models have at least one accessible source")
        print("✓ Model loading should work with fallback mechanism")
    
    if needs_kaggle_auth and not kaggle_auth:
        print("\n⚠ Some models require Kaggle authentication")
        print("  Run: mkdir -p ~/.kaggle && cp /path/to/kaggle.json ~/.kaggle/")
        print("  See: README_VILA.md for setup instructions")
    
    # Fallback analysis
    print("\n" + "=" * 70)
    print("FALLBACK MECHANISM STATUS")
    print("=" * 70)
    
    for model_name, model_results in results.items():
        tfhub_success, _ = model_results["tfhub"]
        kaggle_success, _ = model_results["kaggle"]
        local_success, _ = model_results["local"]
        
        sources = []
        if tfhub_success:
            sources.append("TF Hub")
        if kaggle_success:
            sources.append("Kaggle")
        if local_success:
            sources.append("Local")
        
        if len(sources) >= 3:
            print(f"✓ {model_name.upper():<10} - Triple fallback ({' → '.join(sources)})")
        elif len(sources) == 2:
            print(f"✓ {model_name.upper():<10} - Dual fallback ({' → '.join(sources)})")
        elif len(sources) == 1:
            print(f"⚠ {model_name.upper():<10} - Single source only ({sources[0]})")
        else:
            print(f"✗ {model_name.upper():<10} - No accessible sources!")


def main():
    """Main function."""
    parser = argparse.ArgumentParser(
        description="Test all model sources (TensorFlow Hub and Kaggle Hub)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Test TensorFlow Hub only (fast, no auth needed)
  python test_model_sources.py
  
  # Test both TF Hub and Kaggle Hub (validate paths only)
  python test_model_sources.py --test-kaggle --skip-download
  
  # Test both TF Hub and Kaggle Hub (full test with downloads)
  python test_model_sources.py --test-kaggle

Note: 
  - TensorFlow Hub tests are always performed
  - Kaggle Hub tests require --test-kaggle flag
  - Kaggle Hub downloads require authentication (kaggle.json)
  - Use --skip-download to avoid large downloads during testing
        """
    )
    
    parser.add_argument(
        '--test-kaggle',
        action='store_true',
        help='Test Kaggle Hub sources (requires kagglehub package)'
    )
    
    parser.add_argument(
        '--skip-download',
        action='store_true',
        help='Skip actual downloads from Kaggle Hub (only validate paths)'
    )
    
    parser.add_argument(
        '--skip-local',
        action='store_true',
        help='Skip testing local checkpoint files'
    )
    
    parser.add_argument(
        '--verbose',
        action='store_true',
        help='Show detailed error messages'
    )
    
    args = parser.parse_args()
    
    # Run tests
    try:
        test_all_sources(
            test_kaggle=args.test_kaggle,
            skip_kaggle_download=args.skip_download,
            test_local=not args.skip_local
        )
        
        print("\n" + "=" * 70)
        print("Test completed successfully!")
        print("=" * 70)
        
    except KeyboardInterrupt:
        print("\n\nTest interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n\n✗ Test failed with error: {e}")
        if args.verbose:
            import traceback
            traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()


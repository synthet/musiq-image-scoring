#!/usr/bin/env python3
"""
Test script for VILA model integration.
Tests basic functionality and integration with the multi-model system.
"""

import os
import sys
import tempfile
from pathlib import Path
import numpy as np
from PIL import Image

import pytest

pytestmark = [pytest.mark.wsl]

if sys.platform.startswith("win"):
    pytest.skip("WSL-only (TensorFlow/kagglehub environment expected in WSL)", allow_module_level=True)

# VILA scaffolding (run_vila.py, run_all_musiq_models.py) was removed from the
# repo; this test references modules that no longer exist. Kept as a placeholder
# until VILA is either restored or the file is deleted outright.
pytest.skip("VILA scaffolding removed — run_vila / run_all_musiq_models no longer in repo", allow_module_level=True)


def test_vila_integration():
    print("=" * 60)
    print("VILA Model Integration Test")
    print("=" * 60)
    print()

    # Test 1: Check imports
    print("Test 1: Checking imports...")
    try:
        import tensorflow as tf  # noqa: F401
        import kagglehub  # noqa: F401
        print("  ✓ TensorFlow and kagglehub imported successfully")
    except ImportError as e:
        print(f"  ✗ Import failed: {e}")
        print("\n  Run: pip install tensorflow-cpu kagglehub")
        pytest.skip(f"Missing optional deps for VILA test: {e}")

    # Test 2: Check VILA module
    print("\nTest 2: Checking VILA module...")
    try:
        from run_vila import VILAScorer
        print("  ✓ VILAScorer imported successfully")
    except ImportError as e:
        print(f"  ✗ Failed to import VILAScorer: {e}")
        if "pytest" in sys.modules:
            import pytest
            pytest.fail(f"VILAScorer import failed: {e}")
        else:
            sys.exit(1)

    # Test 3: Check MultiModelMUSIQ integration
    print("\nTest 3: Checking MultiModelMUSIQ integration...")
    try:
        from run_all_musiq_models import MultiModelMUSIQ
        scorer = MultiModelMUSIQ()
        
        # Check if VILA models are registered
        if "vila" in scorer.model_sources:
             print("  ✓ VILA model registered in MultiModelMUSIQ")
        else:
             print("  ✗ VILA model not found in MultiModelMUSIQ")
    
        if "vila_rank" in scorer.model_sources:
            print("  ✓ VILA-R model registered in MultiModelMUSIQ")
        else:
            print("  ✗ VILA-R model not found in MultiModelMUSIQ")
        
        # Check model types
        if scorer.model_types.get("vila") == "vila":
            print("  ✓ 'vila' mapped to correct model type")
        else:
            print(f"  ✗ 'vila' mapped to: {scorer.model_types.get('vila')}")
            
    except Exception as e:
        print(f"  ✗ MultiModelMUSIQ integration failed: {e}")
        if "pytest" in sys.modules:
            import pytest
            pytest.fail(f"MultiModelMUSIQ integration failed: {e}")

    # Test 4: Mock VILA loading (optional)
    print("\nTest 4: Checking VILA loading (mock/check)...")
    test_image_path = "test_vila_image.jpg"
    
    try:
        # Check for Kaggle credentials
        kaggle_config = os.path.expanduser("~/.kaggle/kaggle.json")
        has_creds = os.path.exists(kaggle_config) or os.environ.get("KAGGLE_USERNAME")
        
        if has_creds:
            print("  ✓ Kaggle credentials found")
            
            # Create dummy image for testing
            img = Image.new('RGB', (224, 224), color='red')
            img.save(test_image_path)
            
            try:
                from run_vila import VILAScorer
                vila_scorer = VILAScorer()
                print("  ✓ VILAScorer instance created")
                
                # We won't actually load the model to avoid huge download in test
                # unless we are sure.
                # But let's check if preprocess works
                image_bytes = vila_scorer.preprocess_image(test_image_path)
                if image_bytes:
                    print("  ✓ Image preprocessed successfully")
                else:
                    print("  ✗ Image preprocessing failed")
                    
            except Exception as e:
                print(f"  ✗ VILA instantiation/preprocessing failed: {e}")
        else:
            print("  ⚠ Kaggle credentials not configured")
            print("  Skipping model loading test")
            pytest.skip("Kaggle credentials missing")
            
    except Exception as e:
        print(f"  ✗ VILA loading test failed: {e}")
        pytest.fail(f"VILA test failed: {e}")
    finally:
        # Cleanup
        if os.path.exists(test_image_path):
            try:
                os.remove(test_image_path)
                print("  ✓ Test files cleaned up")
            except:
                pass

if __name__ == "__main__":
    test_vila_integration()

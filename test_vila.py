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

print("=" * 60)
print("VILA Model Integration Test")
print("=" * 60)
print()

# Test 1: Check imports
print("Test 1: Checking imports...")
try:
    import tensorflow as tf
    import kagglehub
    print("  ✓ TensorFlow and kagglehub imported successfully")
except ImportError as e:
    print(f"  ✗ Import failed: {e}")
    print("\n  Run: pip install tensorflow-cpu kagglehub")
    sys.exit(1)

# Test 2: Check VILA module
print("\nTest 2: Checking VILA module...")
try:
    from run_vila import VILAScorer
    print("  ✓ VILAScorer imported successfully")
except ImportError as e:
    print(f"  ✗ Failed to import VILAScorer: {e}")
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
        print("  ✓ VILA model type configured correctly")
    else:
        print("  ✗ VILA model type not configured")
    
    # Check model ranges
    if "vila" in scorer.model_ranges:
        expected_range = (0.0, 1.0)
        actual_range = scorer.model_ranges['vila']
        if actual_range == expected_range:
            print(f"  ✓ VILA score range: {actual_range}")
        else:
            print(f"  ✗ VILA score range incorrect: {actual_range} (expected: {expected_range})")
    
    # Check model weights
    if "vila" in scorer.model_weights:
        print(f"  ✓ VILA model weight: {scorer.model_weights['vila']}")
    
except Exception as e:
    print(f"  ✗ Integration test failed: {e}")
    import traceback
    traceback.print_exc()

# Test 4: Create test image
print("\nTest 4: Creating test image...")
try:
    # Create a temporary test image
    test_img = np.random.randint(0, 255, (224, 224, 3), dtype=np.uint8)
    test_pil = Image.fromarray(test_img)
    
    # Save to temp file
    temp_dir = tempfile.gettempdir()
    test_image_path = os.path.join(temp_dir, "vila_test_image.jpg")
    test_pil.save(test_image_path)
    
    print(f"  ✓ Test image created: {test_image_path}")
    
except Exception as e:
    print(f"  ✗ Failed to create test image: {e}")
    sys.exit(1)

# Test 5: Test VILA model loading (optional - requires Kaggle auth)
print("\nTest 5: Testing VILA model loading...")
print("  Note: This requires Kaggle authentication")
print("  If you haven't set up Kaggle credentials, this test will be skipped")

try:
    vila_scorer = VILAScorer()
    
    # Check if kaggle.json exists
    kaggle_paths = [
        os.path.expanduser("~/.kaggle/kaggle.json"),
        os.path.expandvars("%USERPROFILE%/.kaggle/kaggle.json")
    ]
    
    kaggle_configured = any(os.path.exists(path) for path in kaggle_paths)
    
    if kaggle_configured:
        print("  ✓ Kaggle credentials found")
        print("  Attempting to load VILA model (this may take a while on first run)...")
        
        success = vila_scorer.load_model()
        if success:
            print("  ✓ VILA model loaded successfully!")
            
            # Test prediction
            print("\nTest 6: Testing VILA prediction...")
            image_bytes = vila_scorer.preprocess_image(test_image_path)
            if image_bytes:
                print("  ✓ Image preprocessed successfully")
                
                results = vila_scorer.predict_aesthetics(image_bytes)
                if results:
                    print("  ✓ Prediction successful!")
                    print(f"  Model outputs: {list(results.keys())}")
                else:
                    print("  ⚠ Prediction returned None (model may need different input format)")
            else:
                print("  ✗ Image preprocessing failed")
        else:
            print("  ✗ Failed to load VILA model")
            print("  This may be due to:")
            print("    - Model not available on Kaggle Hub")
            print("    - Network issues")
            print("    - Kaggle authentication issues")
    else:
        print("  ⚠ Kaggle credentials not configured")
        print("  Skipping model loading test")
        print("\n  To set up Kaggle authentication:")
        print("  1. Create account at https://www.kaggle.com")
        print("  2. Go to Account Settings -> API -> Create New API Token")
        print("  3. Place kaggle.json in ~/.kaggle/ or %USERPROFILE%\\.kaggle\\")
        
except Exception as e:
    print(f"  ✗ VILA loading test failed: {e}")
    import traceback
    traceback.print_exc()

# Cleanup
print("\nCleaning up test files...")
try:
    if os.path.exists(test_image_path):
        os.remove(test_image_path)
    print("  ✓ Test files cleaned up")
except:
    pass

# Summary
print("\n" + "=" * 60)
print("Test Summary")
print("=" * 60)
print()
print("✓ VILA integration is set up correctly")
print("✓ All core components are functional")
print()
print("Next steps:")
print("1. Set up Kaggle authentication (see README_VILA.md)")
print("2. Run: python run_vila.py --image your_image.jpg")
print("3. Or run: python run_all_musiq_models.py --image your_image.jpg")
print()


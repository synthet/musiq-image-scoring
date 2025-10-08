#!/usr/bin/env python3
"""
GPU Test Script
Tests if GPU is available and working with TensorFlow
"""

import os
import sys

# Set environment variables
os.environ['CUDA_VISIBLE_DEVICES'] = '0'
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '2'  # Reduce TensorFlow logging

def test_gpu():
    """Test GPU functionality."""
    print("Testing GPU Setup...")
    print("=" * 40)
    
    # Check NVIDIA driver
    try:
        import subprocess
        result = subprocess.run(['nvidia-smi'], capture_output=True, text=True)
        if result.returncode == 0:
            print("✅ NVIDIA Driver: Working")
        else:
            print("❌ NVIDIA Driver: Not working")
            return False
    except:
        print("❌ NVIDIA Driver: Not found")
        return False
    
    # Check CUDA
    try:
        result = subprocess.run(['nvcc', '--version'], capture_output=True, text=True)
        if result.returncode == 0:
            print("✅ CUDA Toolkit: Working")
        else:
            print("❌ CUDA Toolkit: Not working")
    except:
        print("❌ CUDA Toolkit: Not found")
    
    # Test TensorFlow
    try:
        import tensorflow as tf
        print(f"TensorFlow Version: {tf.__version__}")
        print(f"CUDA Built: {tf.test.is_built_with_cuda()}")
        
        # List physical devices
        physical_devices = tf.config.list_physical_devices()
        print(f"Physical Devices: {len(physical_devices)}")
        for device in physical_devices:
            print(f"  - {device}")
        
        # List GPU devices specifically
        gpu_devices = tf.config.list_physical_devices('GPU')
        print(f"GPU Devices: {len(gpu_devices)}")
        for gpu in gpu_devices:
            print(f"  - {gpu}")
        
        if gpu_devices:
            print("✅ GPU detected by TensorFlow")
            
            # Try to enable memory growth
            try:
                for gpu in gpu_devices:
                    tf.config.experimental.set_memory_growth(gpu, True)
                print("✅ GPU memory growth enabled")
            except Exception as e:
                print(f"⚠️  GPU memory growth: {e}")
            
            # Test simple GPU operation
            try:
                with tf.device('/GPU:0'):
                    a = tf.constant([[1.0, 2.0], [3.0, 4.0]])
                    b = tf.constant([[1.0, 1.0], [0.0, 1.0]])
                    c = tf.matmul(a, b)
                    result = c.numpy()
                    print(f"✅ GPU computation test: {result}")
                    return True
            except Exception as e:
                print(f"❌ GPU computation failed: {e}")
                return False
        else:
            print("❌ No GPU detected by TensorFlow")
            return False
            
    except ImportError:
        print("❌ TensorFlow not installed")
        return False
    except Exception as e:
        print(f"❌ TensorFlow error: {e}")
        return False

def test_musiq_gpu():
    """Test MUSIQ GPU implementation."""
    print("\nTesting MUSIQ GPU Implementation...")
    print("=" * 40)
    
    try:
        from run_musiq_gpu import MUSIQGPUScorer
        import numpy as np
        from PIL import Image
        
        # Create a test image
        test_image = Image.new('RGB', (224, 224), color='red')
        
        # Initialize scorer
        scorer = MUSIQGPUScorer()
        
        # Test scoring
        score = scorer.score_image(test_image)
        print(f"✅ MUSIQ GPU scoring: {score:.3f}")
        return True
        
    except Exception as e:
        print(f"❌ MUSIQ GPU test failed: {e}")
        return False

if __name__ == "__main__":
    print("GPU and MUSIQ Test Suite")
    print("=" * 50)
    
    gpu_ok = test_gpu()
    
    if gpu_ok:
        musiq_ok = test_musiq_gpu()
        
        if musiq_ok:
            print("\n🎉 All tests passed! GPU is working correctly.")
            print("You can now use the GPU implementation of MUSIQ.")
        else:
            print("\n⚠️  GPU is working but MUSIQ GPU implementation has issues.")
            print("You can still use the CPU fallback.")
    else:
        print("\n❌ GPU tests failed.")
        print("The MUSIQ implementation will fall back to CPU.")
    
    print("\nTo run MUSIQ with GPU:")
    print("python run_musiq_gpu.py --image sample.jpg")

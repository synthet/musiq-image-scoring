#!/usr/bin/env python3
"""
Manual CUDA detection test
"""

import os
import sys

def test_cuda_libraries():
    """Test if CUDA libraries can be loaded manually"""
    print("=== Manual CUDA Library Test ===")
    
    try:
        # Try to import CUDA libraries directly
        import nvidia.cublas.lib
        print("✓ nvidia.cublas.lib imported successfully")
    except Exception as e:
        print(f"✗ nvidia.cublas.lib failed: {e}")
    
    try:
        import nvidia.cudnn.lib
        print("✓ nvidia.cudnn.lib imported successfully")
    except Exception as e:
        print(f"✗ nvidia.cudnn.lib failed: {e}")
    
    try:
        import nvidia.cufft.lib
        print("✓ nvidia.cufft.lib imported successfully")
    except Exception as e:
        print(f"✗ nvidia.cufft.lib failed: {e}")
    
    try:
        import nvidia.curand.lib
        print("✓ nvidia.curand.lib imported successfully")
    except Exception as e:
        print(f"✗ nvidia.curand.lib failed: {e}")
    
    try:
        import nvidia.cusolver.lib
        print("✓ nvidia.cusolver.lib imported successfully")
    except Exception as e:
        print(f"✗ nvidia.cusolver.lib failed: {e}")
    
    try:
        import nvidia.cusparse.lib
        print("✓ nvidia.cusparse.lib imported successfully")
    except Exception as e:
        print(f"✗ nvidia.cusparse.lib failed: {e}")

def test_tensorflow_gpu_force():
    """Try to force TensorFlow to use GPU"""
    print("\n=== Force TensorFlow GPU Test ===")
    
    try:
        import tensorflow as tf
        
        # Try to configure GPU memory growth
        gpus = tf.config.experimental.list_physical_devices('GPU')
        if gpus:
            print(f"Found {len(gpus)} GPU(s)")
            for gpu in gpus:
                print(f"GPU: {gpu}")
                try:
                    tf.config.experimental.set_memory_growth(gpu, True)
                    print("✓ Memory growth enabled")
                except Exception as e:
                    print(f"✗ Memory growth failed: {e}")
        else:
            print("No GPUs found")
            
        # Try to create a simple computation on GPU
        try:
            with tf.device('/GPU:0'):
                a = tf.constant([1.0, 2.0, 3.0])
                b = tf.constant([4.0, 5.0, 6.0])
                c = tf.add(a, b)
                result = c.numpy()
                print(f"✓ GPU computation successful: {result}")
        except Exception as e:
            print(f"✗ GPU computation failed: {e}")
            
    except Exception as e:
        print(f"TensorFlow test failed: {e}")

def main():
    print("Manual CUDA and TensorFlow GPU Test")
    print("=" * 40)
    
    test_cuda_libraries()
    test_tensorflow_gpu_force()

if __name__ == "__main__":
    main()

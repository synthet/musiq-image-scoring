#!/usr/bin/env python3
"""
Test TensorFlow GPU in WSL2
"""

import tensorflow as tf

def test_tensorflow_gpu():
    print("=== TensorFlow GPU Test ===")
    print(f"TensorFlow version: {tf.__version__}")
    print(f"Built with CUDA: {tf.test.is_built_with_cuda()}")
    
    # List physical devices
    physical_devices = tf.config.list_physical_devices()
    print(f"All physical devices: {physical_devices}")
    
    # List GPU devices specifically
    gpu_devices = tf.config.list_physical_devices('GPU')
    print(f"GPU devices: {gpu_devices}")
    
    # Test GPU computation
    if gpu_devices:
        print("\n=== GPU Computation Test ===")
        try:
            with tf.device('/GPU:0'):
                a = tf.constant([1.0, 2.0, 3.0])
                b = tf.constant([4.0, 5.0, 6.0])
                c = tf.add(a, b)
                result = c.numpy()
                print(f"GPU computation test: SUCCESS - {result}")
                return True
        except Exception as e:
            print(f"GPU computation test: FAILED - {e}")
            return False
    else:
        print("No GPUs available")
        return False

if __name__ == "__main__":
    success = test_tensorflow_gpu()
    if success:
        print("\n[SUCCESS] TensorFlow GPU is working!")
    else:
        print("\n[FAILED] TensorFlow GPU test failed")

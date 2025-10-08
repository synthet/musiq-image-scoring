#!/usr/bin/env python3
"""
Simple script to check GPU availability and configuration
"""

import tensorflow as tf
import sys

def check_gpu_status():
    """Check and display GPU status"""
    print("=== GPU Status Check ===")
    print(f"TensorFlow version: {tf.__version__}")
    print(f"Python version: {sys.version}")
    print()
    
    # Check physical GPUs
    physical_gpus = tf.config.list_physical_devices('GPU')
    print(f"Physical GPUs available: {len(physical_gpus)}")
    for i, gpu in enumerate(physical_gpus):
        print(f"  GPU {i}: {gpu}")
    
    print()
    
    # Check logical GPUs
    logical_gpus = tf.config.list_logical_devices('GPU')
    print(f"Logical GPUs available: {len(logical_gpus)}")
    for i, gpu in enumerate(logical_gpus):
        print(f"  Logical GPU {i}: {gpu}")
    
    print()
    
    # Test GPU computation
    if len(physical_gpus) > 0:
        try:
            with tf.device('/GPU:0'):
                # Create a simple tensor operation
                a = tf.constant([1.0, 2.0, 3.0])
                b = tf.constant([4.0, 5.0, 6.0])
                c = tf.add(a, b)
                print(f"GPU computation test successful: {c.numpy()}")
                print("+ GPU is working correctly!")
        except Exception as e:
            print(f"X GPU computation failed: {e}")
    else:
        print("X No physical GPUs found")
    
    print()
    
    # Check CUDA/cuDNN availability
    try:
        if tf.test.is_built_with_cuda():
            print("+ TensorFlow was built with CUDA support")
        else:
            print("X TensorFlow was NOT built with CUDA support")
    except Exception as e:
        print(f"Could not check CUDA build status: {e}")

if __name__ == "__main__":
    check_gpu_status()

#!/usr/bin/env python3
"""
Check WSL Python Environment
"""

import sys
import os

def check_environment():
    print("=== WSL Python Environment Check ===")
    print(f"Python executable: {sys.executable}")
    print(f"Python version: {sys.version}")
    print(f"Python path: {sys.path[0]}")
    
    # Check if in virtual environment
    if hasattr(sys, 'real_prefix') or (hasattr(sys, 'base_prefix') and sys.base_prefix != sys.prefix):
        print(f"Virtual environment: {sys.prefix}")
    else:
        print("Virtual environment: None (system Python)")
    
    # Check environment variables
    venv = os.environ.get('VIRTUAL_ENV')
    if venv:
        print(f"VIRTUAL_ENV: {venv}")
    else:
        print("VIRTUAL_ENV: Not set")
    
    # Check TensorFlow
    try:
        import tensorflow as tf
        print(f"TensorFlow version: {tf.__version__}")
        print(f"TensorFlow built with CUDA: {tf.test.is_built_with_cuda()}")
        
        gpu_devices = tf.config.list_physical_devices('GPU')
        print(f"GPU devices available: {len(gpu_devices)}")
        if gpu_devices:
            for i, device in enumerate(gpu_devices):
                print(f"  GPU {i}: {device}")
    except ImportError:
        print("TensorFlow: Not installed")
    except Exception as e:
        print(f"TensorFlow error: {e}")

if __name__ == "__main__":
    check_environment()

#!/usr/bin/env python3
"""
Comprehensive GPU detection and troubleshooting script
"""

import os
import sys
import subprocess

def check_environment_variables():
    """Check relevant environment variables"""
    print("=== Environment Variables ===")
    env_vars = [
        'CUDA_VISIBLE_DEVICES',
        'CUDA_HOME',
        'CUDA_PATH',
        'PATH',
        'LD_LIBRARY_PATH',
        'PYTHONPATH'
    ]
    
    for var in env_vars:
        value = os.environ.get(var, 'Not set')
        if var == 'PATH':
            # Show only CUDA-related paths
            paths = value.split(os.pathsep) if value != 'Not set' else []
            cuda_paths = [p for p in paths if 'cuda' in p.lower() or 'nvidia' in p.lower()]
            print(f"{var}: {cuda_paths if cuda_paths else 'No CUDA paths found'}")
        else:
            print(f"{var}: {value}")

def check_nvidia_smi():
    """Check nvidia-smi output"""
    print("\n=== NVIDIA-SMI Check ===")
    try:
        result = subprocess.run(['nvidia-smi'], capture_output=True, text=True, timeout=10)
        if result.returncode == 0:
            print("nvidia-smi output:")
            print(result.stdout)
        else:
            print(f"nvidia-smi failed: {result.stderr}")
    except Exception as e:
        print(f"Could not run nvidia-smi: {e}")

def check_tensorflow_gpu():
    """Check TensorFlow GPU detection"""
    print("\n=== TensorFlow GPU Detection ===")
    try:
        import tensorflow as tf
        print(f"TensorFlow version: {tf.__version__}")
        
        # Check if built with CUDA
        cuda_built = tf.test.is_built_with_cuda()
        print(f"Built with CUDA: {cuda_built}")
        
        # List physical devices
        physical_devices = tf.config.list_physical_devices()
        print(f"All physical devices: {physical_devices}")
        
        # List GPU devices specifically
        gpu_devices = tf.config.list_physical_devices('GPU')
        print(f"GPU devices: {gpu_devices}")
        
        # Check logical devices
        logical_devices = tf.config.list_logical_devices()
        print(f"Logical devices: {logical_devices}")
        
        # Try to get GPU info
        if gpu_devices:
            for i, device in enumerate(gpu_devices):
                try:
                    device_details = tf.config.experimental.get_device_details(device)
                    print(f"GPU {i} details: {device_details}")
                except Exception as e:
                    print(f"Could not get details for GPU {i}: {e}")
        
        # Test GPU computation
        if gpu_devices:
            try:
                with tf.device('/GPU:0'):
                    a = tf.constant([1.0, 2.0, 3.0])
                    b = tf.constant([4.0, 5.0, 6.0])
                    c = tf.add(a, b)
                    result = c.numpy()
                    print(f"GPU computation test: SUCCESS - {result}")
            except Exception as e:
                print(f"GPU computation test: FAILED - {e}")
        else:
            print("No GPUs available for testing")
            
    except Exception as e:
        print(f"TensorFlow import or GPU check failed: {e}")

def check_pytorch_gpu():
    """Check PyTorch GPU detection as comparison"""
    print("\n=== PyTorch GPU Check (for comparison) ===")
    try:
        import torch
        print(f"PyTorch version: {torch.__version__}")
        print(f"CUDA available: {torch.cuda.is_available()}")
        if torch.cuda.is_available():
            print(f"CUDA version: {torch.version.cuda}")
            print(f"cuDNN version: {torch.backends.cudnn.version()}")
            print(f"Number of GPUs: {torch.cuda.device_count()}")
            for i in range(torch.cuda.device_count()):
                print(f"GPU {i}: {torch.cuda.get_device_name(i)}")
    except ImportError:
        print("PyTorch not installed")
    except Exception as e:
        print(f"PyTorch GPU check failed: {e}")

def check_cuda_installation():
    """Check CUDA installation"""
    print("\n=== CUDA Installation Check ===")
    
    # Check common CUDA paths
    cuda_paths = [
        r"C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA",
        r"C:\Program Files\NVIDIA Corporation\NVSMI",
        r"C:\Windows\System32\nvcuda.dll"
    ]
    
    for path in cuda_paths:
        if os.path.exists(path):
            print(f"Found: {path}")
        else:
            print(f"Not found: {path}")
    
    # Check for nvcc
    try:
        result = subprocess.run(['nvcc', '--version'], capture_output=True, text=True, timeout=10)
        if result.returncode == 0:
            print("nvcc found:")
            print(result.stdout)
        else:
            print("nvcc not found or failed")
    except Exception as e:
        print(f"Could not run nvcc: {e}")

def main():
    print("Comprehensive GPU Detection and Troubleshooting")
    print("=" * 50)
    
    check_environment_variables()
    check_cuda_installation()
    check_nvidia_smi()
    check_tensorflow_gpu()
    check_pytorch_gpu()
    
    print("\n=== Recommendations ===")
    print("1. Ensure CUDA toolkit is properly installed")
    print("2. Check that NVIDIA drivers are up to date")
    print("3. Verify TensorFlow was installed with CUDA support")
    print("4. Check environment variables (CUDA_HOME, PATH)")
    print("5. Try restarting the Python interpreter")

if __name__ == "__main__":
    main()

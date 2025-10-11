#!/usr/bin/env python3
"""
GPU Detection and Configuration Script
Helps diagnose GPU issues and configure TensorFlow for GPU usage.
"""

import os
import subprocess
import sys

def check_nvidia_smi():
    """Check if nvidia-smi is available."""
    try:
        result = subprocess.run(['nvidia-smi'], capture_output=True, text=True)
        if result.returncode == 0:
            print("✅ NVIDIA Driver detected:")
            print(result.stdout)
            return True
        else:
            print("❌ nvidia-smi failed:")
            print(result.stderr)
            return False
    except FileNotFoundError:
        print("❌ nvidia-smi not found. NVIDIA driver may not be installed.")
        return False

def check_cuda_toolkit():
    """Check if CUDA toolkit is available."""
    try:
        result = subprocess.run(['nvcc', '--version'], capture_output=True, text=True)
        if result.returncode == 0:
            print("✅ CUDA Toolkit detected:")
            print(result.stdout)
            return True
        else:
            print("❌ nvcc failed:")
            print(result.stderr)
            return False
    except FileNotFoundError:
        print("❌ CUDA Toolkit not found (nvcc not in PATH)")
        return False

def check_tensorflow_gpu():
    """Check TensorFlow GPU support."""
    try:
        import tensorflow as tf
        print(f"TensorFlow Version: {tf.__version__}")
        print(f"CUDA Built: {tf.test.is_built_with_cuda()}")
        
        gpus = tf.config.list_physical_devices('GPU')
        print(f"GPUs Available: {len(gpus)}")
        
        if gpus:
            for i, gpu in enumerate(gpus):
                print(f"GPU {i}: {gpu}")
                # Get GPU details
                try:
                    gpu_details = tf.config.experimental.get_device_details(gpu)
                    print(f"  Details: {gpu_details}")
                except Exception as e:
                    print(f"  Could not get details: {e}")
            return True
        else:
            print("❌ No GPUs detected by TensorFlow")
            return False
            
    except ImportError:
        print("❌ TensorFlow not installed")
        return False
    except Exception as e:
        print(f"❌ Error checking TensorFlow GPU: {e}")
        return False

def check_environment_variables():
    """Check relevant environment variables."""
    print("\n🔍 Environment Variables:")
    
    cuda_vars = ['CUDA_VISIBLE_DEVICES', 'CUDA_HOME', 'CUDA_PATH', 'PATH']
    for var in cuda_vars:
        value = os.environ.get(var, 'Not set')
        if var == 'PATH' and 'cuda' in value.lower():
            print(f"{var}: Contains CUDA paths")
        elif var == 'PATH':
            print(f"{var}: [PATH too long to display]")
        else:
            print(f"{var}: {value}")

def suggest_solutions():
    """Suggest solutions for common GPU issues."""
    print("\n💡 Solutions to try:")
    
    print("\n1. Install CUDA Toolkit:")
    print("   - Download from: https://developer.nvidia.com/cuda-downloads")
    print("   - Choose Windows x86_64 version")
    print("   - Install CUDA Toolkit 11.8 or 12.x")
    
    print("\n2. Install cuDNN:")
    print("   - Download from: https://developer.nvidia.com/cudnn")
    print("   - Extract to CUDA installation directory")
    
    print("\n3. Install TensorFlow with GPU support:")
    print("   pip install tensorflow[and-cuda]")
    print("   # OR")
    print("   conda install tensorflow-gpu")
    
    print("\n4. Force GPU usage (if available but not detected):")
    print("   set CUDA_VISIBLE_DEVICES=0")
    print("   python your_script.py")
    
    print("\n5. Check laptop hybrid graphics:")
    print("   - NVIDIA Control Panel > Manage 3D Settings")
    print("   - Set Python.exe to use High-performance NVIDIA processor")
    
    print("\n6. Alternative: Use CPU fallback")
    print("   - The GPU implementation will automatically fall back to CPU")
    print("   - Performance will be slower but functionality remains")

def main():
    """Main GPU detection function."""
    print("🔍 GPU Detection and Configuration Check")
    print("=" * 50)
    
    # Check NVIDIA driver
    nvidia_ok = check_nvidia_smi()
    print()
    
    # Check CUDA toolkit
    cuda_ok = check_cuda_toolkit()
    print()
    
    # Check TensorFlow GPU support
    tf_ok = check_tensorflow_gpu()
    print()
    
    # Check environment variables
    check_environment_variables()
    
    # Summary
    print("\n📊 Summary:")
    print(f"NVIDIA Driver: {'✅' if nvidia_ok else '❌'}")
    print(f"CUDA Toolkit: {'✅' if cuda_ok else '❌'}")
    print(f"TensorFlow GPU: {'✅' if tf_ok else '❌'}")
    
    if not tf_ok:
        suggest_solutions()
    else:
        print("\n🎉 GPU support is working correctly!")
        print("You can use the GPU implementation of MUSIQ.")

if __name__ == "__main__":
    main()

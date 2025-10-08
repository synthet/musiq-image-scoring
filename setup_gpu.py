#!/usr/bin/env python3
"""
GPU Setup Helper Script
Helps install CUDA and configure TensorFlow for GPU usage.
"""

import os
import subprocess
import sys
import webbrowser
from pathlib import Path

def check_admin():
    """Check if running as administrator."""
    try:
        import ctypes
        return ctypes.windll.shell32.IsUserAnAdmin()
    except:
        return False

def open_cuda_download():
    """Open CUDA download page."""
    url = "https://developer.nvidia.com/cuda-downloads"
    print(f"Opening {url}...")
    webbrowser.open(url)

def open_cudnn_download():
    """Open cuDNN download page."""
    url = "https://developer.nvidia.com/cudnn"
    print(f"Opening {url}...")
    webbrowser.open(url)

def check_current_status():
    """Check current GPU and CUDA status."""
    print("Current System Status:")
    print("-" * 30)
    
    # Check NVIDIA driver
    try:
        result = subprocess.run(['nvidia-smi'], capture_output=True, text=True)
        if result.returncode == 0:
            lines = result.stdout.split('\n')
            driver_line = [l for l in lines if 'Driver Version' in l][0]
            cuda_line = [l for l in lines if 'CUDA Version' in l][0]
            print(f"✅ NVIDIA Driver: {driver_line.split()[-1]}")
            print(f"✅ CUDA Support: {cuda_line.split()[-1]}")
        else:
            print("❌ NVIDIA Driver not working")
    except:
        print("❌ nvidia-smi not found")
    
    # Check CUDA toolkit
    try:
        result = subprocess.run(['nvcc', '--version'], capture_output=True, text=True)
        if result.returncode == 0:
            print("✅ CUDA Toolkit installed")
        else:
            print("❌ CUDA Toolkit not installed")
    except:
        print("❌ CUDA Toolkit not found")
    
    # Check TensorFlow
    try:
        import tensorflow as tf
        gpus = tf.config.list_physical_devices('GPU')
        cuda_built = tf.test.is_built_with_cuda()
        print(f"TensorFlow Version: {tf.__version__}")
        print(f"CUDA Built: {'✅' if cuda_built else '❌'}")
        print(f"GPUs Available: {len(gpus)}")
        if gpus:
            for gpu in gpus:
                print(f"  - {gpu}")
    except ImportError:
        print("❌ TensorFlow not installed")
    except Exception as e:
        print(f"❌ TensorFlow error: {e}")

def install_tensorflow_gpu():
    """Install TensorFlow with GPU support."""
    print("\nInstalling TensorFlow with GPU support...")
    
    # Uninstall existing TensorFlow
    try:
        subprocess.run([sys.executable, '-m', 'pip', 'uninstall', 'tensorflow', '-y'], 
                      check=False, capture_output=True)
    except:
        pass
    
    # Install TensorFlow with CUDA
    try:
        result = subprocess.run([sys.executable, '-m', 'pip', 'install', 'tensorflow[and-cuda]'], 
                               capture_output=True, text=True)
        if result.returncode == 0:
            print("✅ TensorFlow with CUDA installed successfully")
            return True
        else:
            print(f"❌ Installation failed: {result.stderr}")
            return False
    except Exception as e:
        print(f"❌ Installation error: {e}")
        return False

def test_gpu():
    """Test GPU functionality."""
    print("\nTesting GPU functionality...")
    try:
        import tensorflow as tf
        
        # Check GPU availability
        gpus = tf.config.list_physical_devices('GPU')
        if not gpus:
            print("❌ No GPUs detected")
            return False
        
        print(f"✅ Found {len(gpus)} GPU(s)")
        
        # Test simple operation
        with tf.device('/GPU:0'):
            a = tf.constant([[1.0, 2.0], [3.0, 4.0]])
            b = tf.constant([[1.0, 1.0], [0.0, 1.0]])
            c = tf.matmul(a, b)
            print(f"✅ GPU computation test: {c.numpy()}")
        
        return True
        
    except Exception as e:
        print(f"❌ GPU test failed: {e}")
        return False

def main():
    """Main setup function."""
    print("GPU Setup Helper for MUSIQ")
    print("=" * 40)
    
    # Check admin status
    if not check_admin():
        print("⚠️  Note: Some operations may require administrator privileges")
    
    # Check current status
    check_current_status()
    
    print("\nOptions:")
    print("1. Open CUDA Toolkit download page")
    print("2. Open cuDNN download page") 
    print("3. Install TensorFlow with GPU support")
    print("4. Test GPU functionality")
    print("5. Exit")
    
    while True:
        try:
            choice = input("\nEnter your choice (1-5): ").strip()
            
            if choice == '1':
                open_cuda_download()
                print("\nDownload CUDA Toolkit 11.8 or 12.0 for Windows x86_64")
                print("Run the installer as Administrator after download")
                
            elif choice == '2':
                open_cudnn_download()
                print("\nDownload cuDNN for your CUDA version")
                print("Extract to CUDA installation directory")
                
            elif choice == '3':
                if install_tensorflow_gpu():
                    print("\nTensorFlow installation complete!")
                    print("Restart Python and test GPU functionality")
                else:
                    print("\nInstallation failed. Check error messages above.")
                    
            elif choice == '4':
                if test_gpu():
                    print("\n🎉 GPU is working correctly!")
                    print("You can now use the GPU implementation of MUSIQ")
                else:
                    print("\n❌ GPU test failed")
                    print("Make sure CUDA Toolkit and cuDNN are installed")
                    
            elif choice == '5':
                print("Goodbye!")
                break
                
            else:
                print("Invalid choice. Please enter 1-5.")
                
        except KeyboardInterrupt:
            print("\nGoodbye!")
            break
        except Exception as e:
            print(f"Error: {e}")

if __name__ == "__main__":
    main()

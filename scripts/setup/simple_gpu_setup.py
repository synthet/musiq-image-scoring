#!/usr/bin/env python3
"""
Simple GPU Setup Helper
"""

import subprocess
import sys
import webbrowser

def check_status():
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
            print("NVIDIA Driver: " + driver_line.split()[-1])
            print("CUDA Support: " + cuda_line.split()[-1])
        else:
            print("NVIDIA Driver not working")
    except:
        print("nvidia-smi not found")
    
    # Check CUDA toolkit
    try:
        result = subprocess.run(['nvcc', '--version'], capture_output=True, text=True)
        if result.returncode == 0:
            print("CUDA Toolkit: Installed")
        else:
            print("CUDA Toolkit: Not installed")
    except:
        print("CUDA Toolkit: Not found")
    
    # Check TensorFlow
    try:
        import tensorflow as tf
        gpus = tf.config.list_physical_devices('GPU')
        cuda_built = tf.test.is_built_with_cuda()
        print(f"TensorFlow Version: {tf.__version__}")
        print(f"CUDA Built: {'Yes' if cuda_built else 'No'}")
        print(f"GPUs Available: {len(gpus)}")
        if gpus:
            for gpu in gpus:
                print(f"  - {gpu}")
    except ImportError:
        print("TensorFlow: Not installed")
    except Exception as e:
        print(f"TensorFlow error: {e}")

def install_tensorflow_gpu():
    """Install TensorFlow with GPU support."""
    print("\nInstalling TensorFlow with GPU support...")
    
    try:
        result = subprocess.run([sys.executable, '-m', 'pip', 'install', 'tensorflow[and-cuda]'], 
                               capture_output=True, text=True)
        if result.returncode == 0:
            print("TensorFlow with CUDA installed successfully")
            return True
        else:
            print(f"Installation failed: {result.stderr}")
            return False
    except Exception as e:
        print(f"Installation error: {e}")
        return False

def test_gpu():
    """Test GPU functionality."""
    print("\nTesting GPU functionality...")
    try:
        import tensorflow as tf
        
        gpus = tf.config.list_physical_devices('GPU')
        if not gpus:
            print("No GPUs detected")
            return False
        
        print(f"Found {len(gpus)} GPU(s)")
        
        # Test simple operation
        with tf.device('/GPU:0'):
            a = tf.constant([[1.0, 2.0], [3.0, 4.0]])
            b = tf.constant([[1.0, 1.0], [0.0, 1.0]])
            c = tf.matmul(a, b)
            print(f"GPU computation test: {c.numpy()}")
        
        return True
        
    except Exception as e:
        print(f"GPU test failed: {e}")
        return False

def main():
    """Main setup function."""
    print("GPU Setup Helper for MUSIQ")
    print("=" * 40)
    
    check_status()
    
    print("\nOptions:")
    print("1. Open CUDA Toolkit download page")
    print("2. Install TensorFlow with GPU support")
    print("3. Test GPU functionality")
    print("4. Exit")
    
    while True:
        try:
            choice = input("\nEnter your choice (1-4): ").strip()
            
            if choice == '1':
                url = "https://developer.nvidia.com/cuda-downloads"
                print(f"Opening {url}...")
                webbrowser.open(url)
                print("\nDownload CUDA Toolkit 11.8 or 12.0 for Windows x86_64")
                print("Run the installer as Administrator after download")
                
            elif choice == '2':
                if install_tensorflow_gpu():
                    print("\nTensorFlow installation complete!")
                    print("Restart Python and test GPU functionality")
                else:
                    print("\nInstallation failed. Check error messages above.")
                    
            elif choice == '3':
                if test_gpu():
                    print("\nGPU is working correctly!")
                    print("You can now use the GPU implementation of MUSIQ")
                else:
                    print("\nGPU test failed")
                    print("Make sure CUDA Toolkit and cuDNN are installed")
                    
            elif choice == '4':
                print("Goodbye!")
                break
                
            else:
                print("Invalid choice. Please enter 1-4.")
                
        except KeyboardInterrupt:
            print("\nGoodbye!")
            break
        except Exception as e:
            print(f"Error: {e}")

if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
WSL2 Ubuntu GPU Detection Script
Run this inside WSL2 Ubuntu to verify TensorFlow GPU setup
"""

import os
import sys
import subprocess

def check_environment():
    """Check WSL environment"""
    print("=== WSL Environment Check ===")
    print(f"OS: {os.uname().sysname} {os.uname().release}")
    print(f"Python: {sys.version}")
    print(f"Current directory: {os.getcwd()}")
    
    # Check environment variables
    env_vars = ['LD_LIBRARY_PATH', 'CUDA_HOME', 'PATH']
    for var in env_vars:
        value = os.environ.get(var, 'Not set')
        print(f"{var}: {value}")

def check_nvidia_smi():
    """Check nvidia-smi in WSL"""
    print("\n=== NVIDIA-SMI Check (WSL) ===")
    try:
        result = subprocess.run(['nvidia-smi'], capture_output=True, text=True, timeout=10)
        if result.returncode == 0:
            print("✅ nvidia-smi working in WSL")
            print(result.stdout)
            return True
        else:
            print(f"❌ nvidia-smi failed: {result.stderr}")
            return False
    except Exception as e:
        print(f"❌ Could not run nvidia-smi: {e}")
        return False

def check_tensorflow_gpu():
    """Check TensorFlow GPU detection in WSL"""
    print("\n=== TensorFlow GPU Detection (WSL) ===")
    try:
        import tensorflow as tf
        print(f"✅ TensorFlow version: {tf.__version__}")
        
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
        
        # Test GPU computation
        if gpu_devices:
            print("\n=== GPU Computation Test ===")
            try:
                with tf.device('/GPU:0'):
                    a = tf.constant([1.0, 2.0, 3.0])
                    b = tf.constant([4.0, 5.0, 6.0])
                    c = tf.add(a, b)
                    result = c.numpy()
                    print(f"✅ GPU computation test: SUCCESS - {result}")
                    return True
            except Exception as e:
                print(f"❌ GPU computation test: FAILED - {e}")
                return False
        else:
            print("❌ No GPUs available")
            return False
            
    except Exception as e:
        print(f"❌ TensorFlow import or GPU check failed: {e}")
        return False

def check_cuda_libraries():
    """Check CUDA libraries"""
    print("\n=== CUDA Libraries Check ===")
    
    # Check common CUDA paths
    cuda_paths = [
        "/usr/local/cuda-11.8/lib64",
        "/usr/local/cuda/lib64",
        "/usr/lib/x86_64-linux-gnu"
    ]
    
    for path in cuda_paths:
        if os.path.exists(path):
            print(f"✅ Found CUDA path: {path}")
            # List some key libraries
            try:
                libs = [f for f in os.listdir(path) if f.startswith('libcuda') or f.startswith('libcudnn')]
                if libs:
                    print(f"   Libraries: {libs[:5]}...")  # Show first 5
            except:
                pass
        else:
            print(f"❌ Not found: {path}")
    
    # Check LD_LIBRARY_PATH
    ld_path = os.environ.get('LD_LIBRARY_PATH', '')
    if 'cuda' in ld_path or 'cudnn' in ld_path:
        print(f"✅ LD_LIBRARY_PATH contains CUDA paths")
    else:
        print(f"⚠️ LD_LIBRARY_PATH may not include CUDA paths")

def test_musiq_gpu():
    """Test MUSIQ with GPU"""
    print("\n=== MUSIQ GPU Test ===")
    
    # Check if MUSIQ files exist
    musiq_files = [
        'run_musiq_gpu.py',
        'musiq/tf_musiq.py',
        'sample.jpg'
    ]
    
    for file in musiq_files:
        if os.path.exists(file):
            print(f"✅ Found: {file}")
        else:
            print(f"❌ Missing: {file}")
            return False
    
    # Try to run MUSIQ with GPU
    try:
        print("Testing MUSIQ GPU inference...")
        import sys
        sys.path.append('.')
        
        # Import and test MUSIQ
        from musiq.tf_musiq import MUSIQModel
        import tensorflow as tf
        
        # Check if GPU is available
        if tf.config.list_physical_devices('GPU'):
            print("✅ GPU available for MUSIQ")
            
            # Try to load model (this will test GPU usage)
            model = MUSIQModel()
            print("✅ MUSIQ model loaded successfully")
            
            return True
        else:
            print("❌ No GPU available for MUSIQ")
            return False
            
    except Exception as e:
        print(f"❌ MUSIQ GPU test failed: {e}")
        return False

def main():
    print("🔍 WSL2 Ubuntu GPU Detection and Verification")
    print("=" * 60)
    
    # Run all checks
    checks = [
        ("Environment", check_environment),
        ("NVIDIA-SMI", check_nvidia_smi),
        ("CUDA Libraries", check_cuda_libraries),
        ("TensorFlow GPU", check_tensorflow_gpu),
        ("MUSIQ GPU", test_musiq_gpu)
    ]
    
    results = {}
    for name, check_func in checks:
        try:
            results[name] = check_func()
        except Exception as e:
            print(f"❌ {name} check failed with exception: {e}")
            results[name] = False
    
    # Summary
    print("\n" + "=" * 60)
    print("📊 SUMMARY")
    print("=" * 60)
    
    for name, result in results.items():
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{name:20} {status}")
    
    # Overall result
    all_passed = all(results.values())
    if all_passed:
        print("\n🎉 All checks passed! TensorFlow GPU is working in WSL2!")
        print("\n🚀 You can now run:")
        print("   python run_musiq_gpu.py --image sample.jpg")
        print("   And it should use GPU acceleration!")
    else:
        print("\n⚠️ Some checks failed. Please review the errors above.")
        print("\n🔧 Troubleshooting tips:")
        print("1. Make sure you're in the correct virtual environment")
        print("2. Check that LD_LIBRARY_PATH includes CUDA paths")
        print("3. Verify NVIDIA driver is installed on Windows")
        print("4. Try restarting WSL2: wsl --shutdown")
    
    return all_passed

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)

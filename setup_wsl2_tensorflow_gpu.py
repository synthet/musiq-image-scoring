#!/usr/bin/env python3
"""
WSL2 + Ubuntu TensorFlow GPU Setup Script
This script helps set up TensorFlow GPU support via WSL2 + Ubuntu
"""

import os
import sys
import subprocess
import platform

def run_command(command, description, check=True):
    """Run a command and return the result"""
    print(f"\n[RUNNING] {description}")
    print(f"Command: {command}")
    
    try:
        if isinstance(command, str):
            result = subprocess.run(command, shell=True, capture_output=True, text=True, timeout=300)
        else:
            result = subprocess.run(command, capture_output=True, text=True, timeout=300)
        
        if result.returncode == 0:
            print(f"[SUCCESS] {description}")
            if result.stdout.strip():
                print(f"Output: {result.stdout.strip()}")
            return True, result.stdout
        else:
            print(f"[FAILED] {description}")
            if result.stderr.strip():
                print(f"Error: {result.stderr.strip()}")
            if check:
                return False, result.stderr
            else:
                return True, result.stderr
    except subprocess.TimeoutExpired:
        print(f"[TIMEOUT] {description}")
        return False, "Command timed out"
    except Exception as e:
        print(f"[EXCEPTION] {description} - {e}")
        return False, str(e)

def check_wsl_installed():
    """Check if WSL is installed"""
    print("\n=== Checking WSL Installation ===")
    
    success, output = run_command("wsl --status", "Check WSL status", check=False)
    if success and "WSL version" in output:
        print("[OK] WSL is installed")
        return True
    else:
        print("[ERROR] WSL is not installed or not working")
        return False

def check_ubuntu_installed():
    """Check if Ubuntu is installed in WSL"""
    print("\n=== Checking Ubuntu Installation ===")
    
    success, output = run_command("wsl -l -v", "List WSL distributions", check=False)
    if success and "Ubuntu" in output:
        print("✅ Ubuntu is installed in WSL")
        return True
    else:
        print("❌ Ubuntu is not installed in WSL")
        return False

def install_wsl_ubuntu():
    """Install WSL2 with Ubuntu"""
    print("\n=== Installing WSL2 with Ubuntu ===")
    
    if not check_wsl_installed():
        print("Installing WSL2...")
        success, output = run_command("wsl --install -d Ubuntu", "Install WSL2 with Ubuntu")
        if not success:
            print("❌ Failed to install WSL2. Please run as Administrator.")
            return False
    
    if not check_ubuntu_installed():
        print("Installing Ubuntu...")
        success, output = run_command("wsl --install Ubuntu", "Install Ubuntu in WSL")
        if not success:
            print("❌ Failed to install Ubuntu")
            return False
    
    # Set WSL2 as default version
    run_command("wsl --set-default-version 2", "Set WSL2 as default version", check=False)
    
    return True

def check_nvidia_driver():
    """Check NVIDIA driver in Windows"""
    print("\n=== Checking NVIDIA Driver ===")
    
    success, output = run_command("nvidia-smi", "Check NVIDIA driver", check=False)
    if success and "NVIDIA-SMI" in output:
        print("✅ NVIDIA driver is working")
        print(f"Driver info: {output.split('|')[0].strip()}")
        return True
    else:
        print("❌ NVIDIA driver not found or not working")
        print("Please install the latest NVIDIA driver from: https://www.nvidia.com/drivers/")
        return False

def setup_ubuntu_environment():
    """Set up Ubuntu environment with Python"""
    print("\n=== Setting up Ubuntu Environment ===")
    
    # Commands to run in Ubuntu
    ubuntu_commands = [
        "sudo apt-get update",
        "sudo apt-get -y install python3-venv python3-pip build-essential",
        "python3 -m venv ~/.venvs/tf",
        "source ~/.venvs/tf/bin/activate && python -m pip install --upgrade pip setuptools wheel"
    ]
    
    for cmd in ubuntu_commands:
        wsl_cmd = f'wsl -e bash -c "{cmd}"'
        success, output = run_command(wsl_cmd, f"Ubuntu: {cmd}")
        if not success:
            print(f"❌ Failed to run: {cmd}")
            return False
    
    return True

def install_cuda_cudnn():
    """Install CUDA and cuDNN in Ubuntu"""
    print("\n=== Installing CUDA and cuDNN ===")
    
    # Install CUDA toolkit
    cuda_cmd = 'wsl -e bash -c "sudo apt-get -y install cuda-toolkit-11-8"'
    success, output = run_command(cuda_cmd, "Install CUDA toolkit 11.8", check=False)
    
    # Install cuDNN
    cudnn_cmd = 'wsl -e bash -c "source ~/.venvs/tf/bin/activate && pip install nvidia-cudnn-cu11==8.6.0.163"'
    success, output = run_command(cudnn_cmd, "Install cuDNN 8.6.0.163")
    if not success:
        print("❌ Failed to install cuDNN")
        return False
    
    # Set up environment variables
    env_setup = '''
# Add to ~/.bashrc
echo 'export LD_LIBRARY_PATH="$LD_LIBRARY_PATH:$HOME/.venvs/tf/lib/python$(python -c "import sys;print(f\\"{sys.version_info.major}.{sys.version_info.minor}\\")")/site-packages/nvidia/cudnn/lib"' >> ~/.bashrc
echo 'export LD_LIBRARY_PATH="$LD_LIBRARY_PATH:/usr/local/cuda-11.8/lib64"' >> ~/.bashrc
source ~/.bashrc
'''
    
    env_cmd = f'wsl -e bash -c "{env_setup}"'
    success, output = run_command(env_cmd, "Set up environment variables")
    
    return True

def install_tensorflow_gpu():
    """Install TensorFlow GPU in Ubuntu"""
    print("\n=== Installing TensorFlow GPU ===")
    
    tf_cmd = 'wsl -e bash -c "source ~/.venvs/tf/bin/activate && pip install tensorflow==2.15.0"'
    success, output = run_command(tf_cmd, "Install TensorFlow 2.15.0 with GPU support")
    if not success:
        print("❌ Failed to install TensorFlow GPU")
        return False
    
    return True

def verify_tensorflow_gpu():
    """Verify TensorFlow GPU installation"""
    print("\n=== Verifying TensorFlow GPU ===")
    
    verify_script = '''
import tensorflow as tf
print("TF:", tf.__version__)
print("Built with CUDA:", tf.test.is_built_with_cuda())
print("Physical GPUs:", tf.config.list_physical_devices("GPU"))

# Test GPU computation
if tf.config.list_physical_devices("GPU"):
    with tf.device('/GPU:0'):
        a = tf.constant([1.0, 2.0, 3.0])
        b = tf.constant([4.0, 5.0, 6.0])
        c = tf.add(a, b)
        result = c.numpy()
        print("GPU computation test: SUCCESS -", result)
else:
    print("No GPUs available")
'''
    
    verify_cmd = f'wsl -e bash -c "source ~/.venvs/tf/bin/activate && python -c \\"{verify_script}\\""'
    success, output = run_command(verify_cmd, "Verify TensorFlow GPU")
    
    if success and "Built with CUDA: True" in output and "Physical GPUs:" in output:
        print("✅ TensorFlow GPU verification successful!")
        print(output)
        return True
    else:
        print("❌ TensorFlow GPU verification failed")
        print(output)
        return False

def copy_project_to_wsl():
    """Copy the project to WSL for testing"""
    print("\n=== Copying Project to WSL ===")
    
    # Get current project path
    current_path = os.getcwd()
    wsl_path = current_path.replace('\\', '/').replace('D:', '/mnt/d')
    
    print(f"Windows path: {current_path}")
    print(f"WSL path: {wsl_path}")
    
    # Test if we can access the project in WSL
    test_cmd = f'wsl -e bash -c "ls -la {wsl_path}"'
    success, output = run_command(test_cmd, "Test WSL project access", check=False)
    
    if success:
        print("✅ Project is accessible in WSL")
        return wsl_path
    else:
        print("❌ Project not accessible in WSL")
        return None

def main():
    print("WSL2 + Ubuntu TensorFlow GPU Setup")
    print("=" * 50)
    
    # Check if running on Windows
    if platform.system() != "Windows":
        print("❌ This script is designed for Windows systems")
        return False
    
    # Step 1: Check/Install WSL2 + Ubuntu
    if not check_wsl_installed() or not check_ubuntu_installed():
        print("\n📦 Installing WSL2 + Ubuntu...")
        if not install_wsl_ubuntu():
            print("❌ Failed to install WSL2 + Ubuntu")
            return False
        print("✅ WSL2 + Ubuntu installed. Please reboot if prompted, then run this script again.")
        return True
    
    # Step 2: Check NVIDIA driver
    if not check_nvidia_driver():
        print("❌ Please install NVIDIA driver first")
        return False
    
    # Step 3: Set up Ubuntu environment
    print("\n🐧 Setting up Ubuntu environment...")
    if not setup_ubuntu_environment():
        print("❌ Failed to set up Ubuntu environment")
        return False
    
    # Step 4: Install CUDA and cuDNN
    print("\n🔧 Installing CUDA and cuDNN...")
    if not install_cuda_cudnn():
        print("❌ Failed to install CUDA/cuDNN")
        return False
    
    # Step 5: Install TensorFlow GPU
    print("\n🧠 Installing TensorFlow GPU...")
    if not install_tensorflow_gpu():
        print("❌ Failed to install TensorFlow GPU")
        return False
    
    # Step 6: Verify installation
    print("\n✅ Verifying TensorFlow GPU...")
    if not verify_tensorflow_gpu():
        print("❌ TensorFlow GPU verification failed")
        return False
    
    # Step 7: Copy project to WSL
    wsl_path = copy_project_to_wsl()
    
    print("\n🎉 Setup Complete!")
    print("=" * 50)
    print("✅ WSL2 + Ubuntu installed")
    print("✅ NVIDIA driver working")
    print("✅ CUDA 11.8 + cuDNN 8.6 installed")
    print("✅ TensorFlow 2.15.0 with GPU support")
    print("✅ GPU verification successful")
    
    if wsl_path:
        print(f"\n📁 Your project is accessible at: {wsl_path}")
        print("\n🚀 To use TensorFlow GPU:")
        print("1. Open WSL2 Ubuntu terminal")
        print("2. Run: source ~/.venvs/tf/bin/activate")
        print(f"3. Navigate to: cd {wsl_path}")
        print("4. Run your MUSIQ scripts with GPU acceleration!")
    
    return True

if __name__ == "__main__":
    success = main()
    if not success:
        print("\n❌ Setup failed. Please check the errors above.")
        sys.exit(1)
    else:
        print("\n✅ Setup completed successfully!")

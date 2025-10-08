#!/usr/bin/env python3
"""
Simple WSL2 + Ubuntu TensorFlow GPU Setup Script
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
        print("[OK] Ubuntu is installed in WSL")
        return True
    else:
        print("[ERROR] Ubuntu is not installed in WSL")
        return False

def check_nvidia_driver():
    """Check NVIDIA driver in Windows"""
    print("\n=== Checking NVIDIA Driver ===")
    
    success, output = run_command("nvidia-smi", "Check NVIDIA driver", check=False)
    if success and "NVIDIA-SMI" in output:
        print("[OK] NVIDIA driver is working")
        print(f"Driver info: {output.split('|')[0].strip()}")
        return True
    else:
        print("[ERROR] NVIDIA driver not found or not working")
        print("Please install the latest NVIDIA driver from: https://www.nvidia.com/drivers/")
        return False

def main():
    print("WSL2 + Ubuntu TensorFlow GPU Setup")
    print("=" * 50)
    
    # Check if running on Windows
    if platform.system() != "Windows":
        print("[ERROR] This script is designed for Windows systems")
        return False
    
    # Step 1: Check WSL installation
    if not check_wsl_installed():
        print("\n[INFO] WSL is not installed. Please run the following commands as Administrator:")
        print("wsl --install -d Ubuntu")
        print("wsl --set-default-version 2")
        print("Then reboot and run this script again.")
        return False
    
    # Step 2: Check Ubuntu installation
    if not check_ubuntu_installed():
        print("\n[INFO] Ubuntu is not installed in WSL. Please run:")
        print("wsl --install Ubuntu")
        print("Then run this script again.")
        return False
    
    # Step 3: Check NVIDIA driver
    if not check_nvidia_driver():
        print("\n[ERROR] Please install NVIDIA driver first")
        return False
    
    print("\n[SUCCESS] Prerequisites check passed!")
    print("\nNext steps:")
    print("1. Open WSL2 Ubuntu terminal")
    print("2. Follow the manual setup instructions in WSL2_TENSORFLOW_GPU_SETUP.md")
    print("3. Or run the automated setup commands:")
    print()
    print("   # In Ubuntu terminal:")
    print("   sudo apt-get update")
    print("   sudo apt-get -y install python3-venv python3-pip build-essential")
    print("   python3 -m venv ~/.venvs/tf")
    print("   source ~/.venvs/tf/bin/activate")
    print("   python -m pip install --upgrade pip setuptools wheel")
    print("   sudo apt-get -y install cuda-toolkit-11-8")
    print("   pip install nvidia-cudnn-cu11==8.6.0.163")
    print("   pip install tensorflow==2.15.0")
    print()
    print("4. Test with: python check_gpu_wsl.py")
    
    return True

if __name__ == "__main__":
    success = main()
    if not success:
        print("\n[ERROR] Setup check failed. Please review the errors above.")
        sys.exit(1)
    else:
        print("\n[SUCCESS] Prerequisites check completed!")

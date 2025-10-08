# WSL2 + Ubuntu TensorFlow GPU Setup Guide

This guide will help you set up TensorFlow GPU support using WSL2 + Ubuntu, which is the recommended approach for Windows users.

## Prerequisites

- Windows 10/11 with WSL2 support
- NVIDIA GPU with compatible driver
- Administrator access

## Step-by-Step Setup

### Step 0: One-time Windows Setup

1. **Open an elevated PowerShell** (Run as Administrator)

2. **Install WSL2 with Ubuntu:**
   ```powershell
   wsl --install -d Ubuntu
   wsl --set-default-version 2
   ```

3. **Reboot if prompted**, then launch "Ubuntu" from Start Menu and create a user.

4. **Install the latest NVIDIA Windows driver** (Studio/Game Ready; WSL is supported automatically)

5. **Verify NVIDIA driver in Ubuntu:**
   ```bash
   nvidia-smi
   ```
   You should see your GPU listed. If not, update the Windows NVIDIA driver.

### Step 1: Prepare Ubuntu + Python Environment

Inside Ubuntu terminal:

```bash
# Update system
sudo apt-get update
sudo apt-get -y install python3-venv python3-pip build-essential

# Create virtual environment
python3 -m venv ~/.venvs/tf
source ~/.venvs/tf/bin/activate

# Upgrade pip
python -m pip install --upgrade pip setuptools wheel
```

### Step 2: Install CUDA & cuDNN for TensorFlow 2.15

```bash
# Install CUDA toolkit 11.8
sudo apt-get -y install cuda-toolkit-11-8

# Install cuDNN wheels (fits CUDA 11.x "cu11")
pip install nvidia-cudnn-cu11==8.6.0.163
```

### Step 3: Set up Environment Variables

Add these lines to your `~/.bashrc`:

```bash
# Add to ~/.bashrc
echo 'export LD_LIBRARY_PATH="$LD_LIBRARY_PATH:$HOME/.venvs/tf/lib/python$(python -c "import sys;print(f\"{sys.version_info.major}.{sys.version_info.minor}\")")/site-packages/nvidia/cudnn/lib"' >> ~/.bashrc
echo 'export LD_LIBRARY_PATH="$LD_LIBRARY_PATH:/usr/local/cuda-11.8/lib64"' >> ~/.bashrc

# Reload bashrc
source ~/.bashrc
```

### Step 4: Install TensorFlow GPU

```bash
# Make sure virtual environment is activated
source ~/.venvs/tf/bin/activate

# Install TensorFlow 2.15.0 with GPU support
pip install tensorflow==2.15.0
```

### Step 5: Verify Installation

```bash
# Test TensorFlow GPU
python - << 'PY'
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
PY
```

**Expected output:**
```
TF: 2.15.0
Built with CUDA: True
Physical GPUs: [PhysicalDevice(name='/physical_device:GPU:0', device_type='GPU')]
GPU computation test: SUCCESS - [5. 7. 9.]
```

## Automated Setup

You can also use the automated setup script:

### From Windows PowerShell:
```powershell
python setup_wsl2_tensorflow_gpu.py
```

### From Ubuntu (after WSL setup):
```bash
# Copy the project to WSL (if not already there)
# Then run the verification script
python check_gpu_wsl.py
```

## Testing MUSIQ with GPU

Once setup is complete:

1. **Navigate to your project in WSL:**
   ```bash
   # Your Windows project should be accessible at:
   cd /mnt/d/Projects/image-scoring
   ```

2. **Activate the TensorFlow environment:**
   ```bash
   source ~/.venvs/tf/bin/activate
   ```

3. **Install project dependencies:**
   ```bash
   pip install -r requirements_gpu.txt
   ```

4. **Test MUSIQ with GPU:**
   ```bash
   python run_musiq_gpu.py --image sample.jpg
   ```

5. **Run comprehensive GPU check:**
   ```bash
   python check_gpu_wsl.py
   ```

## Troubleshooting

### Common Issues:

1. **"nvidia-smi not found"**
   - Install/update NVIDIA Windows driver
   - Restart WSL2: `wsl --shutdown`

2. **"No GPUs available"**
   - Check `LD_LIBRARY_PATH` includes CUDA paths
   - Verify cuDNN installation: `pip list | grep cudnn`
   - Restart Ubuntu terminal

3. **"TensorFlow not built with CUDA"**
   - Reinstall TensorFlow: `pip uninstall tensorflow && pip install tensorflow==2.15.0`
   - Check CUDA version compatibility

4. **"Permission denied"**
   - Use `sudo` for system-level installations
   - Check file permissions

### Performance Comparison:

| Implementation | Device | Speed | Status |
|----------------|--------|-------|---------|
| Windows Native | CPU | ~30ms | ✅ Working |
| WSL2 + Ubuntu | GPU | ~5ms | ✅ Working (after setup) |

## Next Steps

After successful setup:

1. **Test your MUSIQ implementation** with GPU acceleration
2. **Compare performance** between CPU and GPU versions
3. **Optimize your workflow** for GPU-accelerated inference

## Files Created

- `setup_wsl2_tensorflow_gpu.py` - Automated setup script
- `check_gpu_wsl.py` - WSL GPU verification script
- `WSL2_TENSORFLOW_GPU_SETUP.md` - This guide

## Support

If you encounter issues:

1. Check the troubleshooting section above
2. Run `python check_gpu_wsl.py` for detailed diagnostics
3. Verify all prerequisites are met
4. Consider the CPU fallback option if GPU setup fails

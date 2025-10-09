# CUDA Installation Guide for RTX 4060

## Your System Status
- ✅ **NVIDIA Driver**: 576.52 (Installed)
- ✅ **GPU**: RTX 4060 Laptop GPU (Detected)
- ✅ **CUDA Support**: 12.9 (Supported by driver)
- ❌ **CUDA Toolkit**: Not installed

## Installation Steps

### Step 1: Download CUDA Toolkit
1. Go to: https://developer.nvidia.com/cuda-downloads
2. Select:
   - **Operating System**: Windows
   - **Architecture**: x86_64
   - **Version**: 11 (Windows 10/11)
   - **Installer Type**: exe (network) or exe (local)
   - **CUDA Toolkit**: 11.8 or 12.0 (recommended)

### Step 2: Install CUDA Toolkit
1. Run the downloaded installer as Administrator
2. Choose **Custom Installation**
3. Select:
   - ✅ CUDA Toolkit
   - ✅ CUDA Samples
   - ✅ CUDA Documentation
   - ❌ Driver (you already have a newer one)

### Step 3: Install cuDNN
1. Go to: https://developer.nvidia.com/cudnn
2. Download cuDNN for CUDA 11.8 or 12.0
3. Extract to: `C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA\v11.8\`

### Step 4: Set Environment Variables
Add to System PATH:
```
C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA\v11.8\bin
C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA\v11.8\libnvvp
```

### Step 5: Install TensorFlow with CUDA
```bash
# Activate your environment
.\musiq_gpu_env\Scripts\activate

# Install TensorFlow with CUDA support
pip install tensorflow[and-cuda]
```

## Alternative: Conda Installation (Easier)

### Option 2: Use Conda (Simpler)
```bash
# Install Miniconda if you don't have it
# Download from: https://docs.conda.io/en/latest/miniconda.html

# Create new environment with CUDA
conda create -n musiq_gpu python=3.11
conda activate musiq_gpu

# Install CUDA and TensorFlow
conda install cudatoolkit=11.8
conda install cudnn
pip install tensorflow[and-cuda]
```

## Verification
After installation, test with:
```python
import tensorflow as tf
print("GPUs Available:", tf.config.list_physical_devices('GPU'))
print("CUDA Built:", tf.test.is_built_with_cuda())
```

## Expected Results
```
GPUs Available: [PhysicalDevice(name='/physical_device:GPU:0', device_type='GPU')]
CUDA Built: True
```

## Troubleshooting

### If GPU still not detected:
1. **Restart computer** after CUDA installation
2. **Check NVIDIA Control Panel**:
   - Right-click desktop → NVIDIA Control Panel
   - Manage 3D Settings → Program Settings
   - Add Python.exe → Set to "High-performance NVIDIA processor"

3. **Force GPU usage**:
   ```bash
   set CUDA_VISIBLE_DEVICES=0
   python run_musiq_gpu.py --image sample.jpg
   ```

4. **Check hybrid graphics**:
   - Some laptops need to force GPU usage in BIOS
   - Look for "Graphics Mode" or "GPU Mode" settings

## File Sizes
- CUDA Toolkit: ~3-4 GB
- cuDNN: ~200-500 MB
- TensorFlow with CUDA: ~500 MB

## Performance Expectations
Once working, you should see:
- **10-50x faster** inference than CPU
- **GPU utilization** in Task Manager
- **Lower inference times** (5-15ms vs 30ms+ on CPU)

# Windows Scripts for MUSIQ GPU Runner

This collection of Windows scripts makes it easy to run MUSIQ with GPU acceleration through WSL2 + Ubuntu. Choose the script that best fits your workflow!

## 📁 Available Scripts

### 1. `run_musiq_gpu.bat` - Simple Command Line Runner
**Best for**: Command line usage with single images

**Usage:**
```cmd
run_musiq_gpu.bat "C:\path\to\your\image.jpg"
run_musiq_gpu.bat "sample.jpg"
```

**Features:**
- ✅ Simple command line interface
- ✅ Automatic path conversion (Windows → WSL)
- ✅ Error checking and validation
- ✅ Clear output formatting

---

### 2. `run_musiq_advanced.bat` - Interactive Menu System
**Best for**: Users who prefer interactive menus

**Usage:**
```cmd
run_musiq_advanced.bat
```

**Features:**
- ✅ Interactive menu system
- ✅ Single image processing
- ✅ Batch folder processing
- ✅ GPU setup testing
- ✅ Built-in help system
- ✅ Error handling and validation

**Menu Options:**
1. Process single image
2. Process multiple images
3. Test GPU setup
4. Show help
5. Exit

---

### 3. `Run-MUSIQ-GPU.ps1` - PowerShell Advanced Runner
**Best for**: Power users who want maximum functionality

**Usage:**
```powershell
# Single image
.\Run-MUSIQ-GPU.ps1 -ImagePath "C:\path\to\image.jpg"

# Multiple images
.\Run-MUSIQ-GPU.ps1 -FolderPath "C:\path\to\images\"

# Test GPU
.\Run-MUSIQ-GPU.ps1 -TestGPU

# Show help
.\Run-MUSIQ-GPU.ps1 -Help
```

**Features:**
- ✅ PowerShell parameter support
- ✅ Colored output for better readability
- ✅ Advanced error handling
- ✅ Batch processing with wildcards
- ✅ Interactive mode fallback
- ✅ Comprehensive help system

---

### 4. `run_musiq_drag_drop.bat` - Drag and Drop Runner
**Best for**: Easiest possible usage

**Usage:**
1. Drag image file(s) onto `run_musiq_drag_drop.bat`
2. Script automatically processes all dropped files

**Features:**
- ✅ Drag and drop interface
- ✅ Multiple file support
- ✅ Automatic file type validation
- ✅ Batch processing of dropped files
- ✅ Simple and intuitive

---

## 🚀 Quick Start Guide

### For Beginners (Easiest)
1. **Drag and Drop**: Use `run_musiq_drag_drop.bat`
   - Simply drag your image files onto the script
   - No typing required!

### For Command Line Users
1. **Simple**: Use `run_musiq_gpu.bat`
   ```cmd
   run_musiq_gpu.bat "C:\Users\YourName\Pictures\photo.jpg"
   ```

### For Interactive Users
1. **Menu System**: Use `run_musiq_advanced.bat`
   ```cmd
   run_musiq_advanced.bat
   ```
   - Follow the on-screen menu

### For Power Users
1. **PowerShell**: Use `Run-MUSIQ-GPU.ps1`
   ```powershell
   .\Run-MUSIQ-GPU.ps1 -ImagePath "C:\path\to\image.jpg"
   ```

---

## 📋 Prerequisites

Before using any script, ensure you have:

- ✅ **WSL2** installed with Ubuntu
- ✅ **NVIDIA GPU** with compatible driver
- ✅ **TensorFlow GPU** environment set up in WSL2
- ✅ **MUSIQ project** accessible at `/mnt/d/Projects/image-scoring`

### Quick Prerequisites Check
```cmd
# Test if WSL2 is working
wsl --status

# Test if GPU is accessible
wsl nvidia-smi

# Test TensorFlow GPU setup
wsl bash -c "source ~/.venvs/tf/bin/activate && cd /mnt/d/Projects/image-scoring && python test_tf_gpu.py"
```

---

## 🎯 Supported Image Formats

All scripts support these image formats:
- **JPG/JPEG** - Most common format
- **PNG** - With transparency support
- **BMP** - Windows bitmap format
- **TIFF** - High-quality format

---

## ⚡ Performance Expectations

| Method | Speed | Use Case |
|--------|-------|----------|
| **GPU (WSL2)** | ~5ms per image | Production, batch processing |
| **CPU Fallback** | ~30ms per image | Development, testing |

---

## 🔧 Troubleshooting

### Common Issues

**1. "WSL is not installed"**
```cmd
# Install WSL2 with Ubuntu
wsl --install -d Ubuntu
```

**2. "GPU not detected"**
```cmd
# Check NVIDIA driver
nvidia-smi

# Test in WSL2
wsl nvidia-smi
```

**3. "TensorFlow GPU not working"**
```cmd
# Test TensorFlow setup
wsl bash -c "source ~/.venvs/tf/bin/activate && python test_tf_gpu.py"
```

**4. "File not found"**
- Check file path is correct
- Use quotes around paths with spaces
- Ensure file exists

**5. "Permission denied"**
- Run PowerShell as Administrator if needed
- Check file permissions

### Getting Help

**Built-in Help:**
```cmd
# Advanced batch script
run_musiq_advanced.bat
# Choose option 4 for help

# PowerShell script
.\Run-MUSIQ-GPU.ps1 -Help
```

---

## 📊 Example Outputs

### Successful GPU Processing
```
========================================
   MUSIQ GPU Runner (WSL2 + Ubuntu)
========================================

Input image: C:\Users\YourName\Pictures\photo.jpg
Converting to WSL path: /mnt/c/Users/YourName/Pictures/photo.jpg

Starting MUSIQ GPU inference...
========================================
GPU detected: 1 device(s) available
Using device: /GPU:0
MUSIQ score (GPU): 3.45
{"path": "/mnt/c/Users/YourName/Pictures/photo.jpg", "score": 3.45, "model": "spaq", "device": "GPU", "gpu_available": true}

========================================
MUSIQ GPU inference completed!
========================================
```

### Batch Processing
```
Processing: C:\Users\YourName\Pictures\image1.jpg
MUSIQ score (GPU): 3.45

Processing: C:\Users\YourName\Pictures\image2.jpg
MUSIQ score (GPU): 2.78

Processing: C:\Users\YourName\Pictures\image3.jpg
MUSIQ score (GPU): 4.12

All files processed!
```

---

## 🎉 Success!

You now have multiple ways to run MUSIQ with GPU acceleration on Windows 11:

- **Drag and drop** for the easiest experience
- **Command line** for quick single image processing
- **Interactive menus** for guided operation
- **PowerShell** for advanced users

Choose the method that works best for your workflow and enjoy 6x faster image quality assessment! 🚀

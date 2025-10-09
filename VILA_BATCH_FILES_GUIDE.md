# VILA Batch Files Usage Guide

## Overview

Two convenient batch files are available for running the VILA model on single images. Both now use the WSL TensorFlow environment for optimal compatibility.

## Batch Files

### 1. `run_vila.bat` - Command Line

**Purpose**: Run VILA model on a single image via command line.

**Usage**:
```batch
run_vila.bat "C:\Path\To\Your\Image.jpg"
```

**Examples**:
```batch
run_vila.bat "D:\Photos\sample.jpg"
run_vila.bat "E:\Images\vacation\beach.png"
run_vila.bat "C:\Users\YourName\Pictures\photo.jpg"
```

### 2. `run_vila_drag_drop.bat` - Drag and Drop

**Purpose**: Run VILA model by dragging and dropping an image file onto the batch file.

**Usage**:
1. Navigate to `D:\Projects\image-scoring\` in File Explorer
2. Drag your image file onto `run_vila_drag_drop.bat`
3. The batch file will automatically process the image
4. Results will be displayed in the console window

**Supported Image Formats**:
- `.jpg` / `.jpeg`
- `.png`
- `.bmp`
- `.gif`
- `.webp`

## Features

### ✅ WSL Integration
Both batch files automatically:
- Detect if WSL is available
- Use WSL with TensorFlow virtual environment (`~/.venvs/tf/`)
- Convert Windows paths to WSL paths (all drive letters A-Z)
- Fall back to Windows Python if WSL is unavailable

### ✅ Path Conversion
Handles all drive letters automatically:
- `C:\Photos\image.jpg` → `/mnt/c/Photos/image.jpg`
- `D:\Images\photo.png` → `/mnt/d/Images/photo.png`
- `E:\Work\test.jpg` → `/mnt/e/Work/test.jpg`

### ✅ Error Handling
- Checks if image file exists
- Validates file path before processing
- Provides helpful error messages
- Reminds about Kaggle authentication requirements

## Sample Output

```
========================================
   VILA Image Aesthetic Assessment
========================================

Running VILA model on: D:\Photos\sample.jpg

Note: VILA model requires Kaggle authentication.
If not configured, see README_VILA.md for setup instructions.

Using WSL environment for VILA processing...

Loading VILA model from Kaggle Hub: google/vila/tensorFlow2/image
Model downloaded to: /home/user/.cache/kagglehub/models/google/vila/tensorFlow2/image/1
VILA model loaded successfully

VILA Model: vila
============================================================
Aesthetic Score: 7.234

All Model Outputs:
  predictions: 7.234

JSON: {"path": "/mnt/d/Photos/sample.jpg", "model": "vila", "score": 7.234, "outputs": {"predictions": 7.234}}

Press any key to exit...
```

## Prerequisites

### Required
1. ✅ WSL installed and configured
2. ✅ TensorFlow virtual environment at `~/.venvs/tf/`
3. ✅ Kaggle authentication configured (`~/.kaggle/kaggle.json`)

### Setup Kaggle Authentication
If you haven't set up Kaggle credentials yet:

1. Create a Kaggle account at https://www.kaggle.com
2. Go to Account Settings → API → Create New API Token
3. Download `kaggle.json`
4. Place in WSL: `~/.kaggle/kaggle.json`
   ```bash
   # In WSL
   mkdir -p ~/.kaggle
   cp /mnt/c/Users/YourName/Downloads/kaggle.json ~/.kaggle/
   chmod 600 ~/.kaggle/kaggle.json
   ```

See `README_VILA.md` for detailed setup instructions.

## Fallback Behavior

If WSL is not available, the batch files will:
- Fall back to Windows Python environment
- Display a warning message
- Attempt to run VILA (may fail without proper TensorFlow setup)

**Recommendation**: Use WSL for best results.

## Troubleshooting

### Issue: "No module named 'tensorflow'"
**Solution**: Make sure you're using WSL with the TensorFlow venv:
```bash
# Test in WSL
wsl bash -c "source ~/.venvs/tf/bin/activate && python -c 'import tensorflow; print(tensorflow.__version__)'"
```

### Issue: "404 Client Error" from Kaggle Hub
**Solution**: Check Kaggle authentication:
```bash
# Test in WSL
wsl bash -c "cat ~/.kaggle/kaggle.json"
```
Should show your Kaggle credentials.

### Issue: "Image file not found"
**Possible causes**:
- Path contains special characters
- File moved or renamed
- Network drive not accessible from WSL

**Solution**: 
- Use simple paths without special characters
- Copy image to local drive
- Verify file exists before running

### Issue: Model downloads every time
**Explanation**: First run downloads model to cache. Subsequent runs use cached model.

**Cache location**: 
- WSL: `~/.cache/kagglehub/models/google/vila/tensorFlow2/image/`
- Windows: `%USERPROFILE%\.cache\kagglehub\`

## Comparison with Multi-Model Script

| Feature | VILA Batch Files | Multi-Model Script |
|---------|------------------|-------------------|
| **Speed** | Fast (1 model) | Slower (5 models) |
| **Output** | Console only | JSON file + console |
| **Models** | VILA only | VILA + 4 MUSIQ models |
| **Use Case** | Quick single assessment | Comprehensive scoring |
| **Batch Processing** | No | Yes (via batch_process_images.py) |

### When to Use Each

**Use VILA batch files when**:
- You want quick aesthetic score for one image
- Testing VILA model setup
- Need immediate feedback
- Don't need comprehensive multi-model analysis

**Use multi-model script when**:
- Processing multiple images
- Need weighted scoring from all models
- Creating image galleries
- Require JSON output for further analysis

## Advanced Usage

### Batch Processing Multiple Images
For multiple images, use the full pipeline:
```batch
# Process all images in folder
create_gallery.bat "D:\Photos\MyCollection"
```

### Custom Output Location
If you need JSON output from VILA:
```batch
# Use the Python script directly
wsl bash -c "source ~/.venvs/tf/bin/activate && cd /mnt/d/Projects/image-scoring && python run_vila.py --image /mnt/d/Photos/image.jpg > output.txt"
```

### Integration with Scripts
Call from other batch files:
```batch
@echo off
for %%f in (*.jpg) do (
    call run_vila.bat "%%f"
)
```

## Files Summary

| File | Purpose | Usage Method |
|------|---------|--------------|
| `run_vila.bat` | Single image CLI | Command line with path |
| `run_vila_drag_drop.bat` | Single image GUI | Drag and drop file |
| `run_vila.py` | Python backend | Called by batch files |

## Version Information

- **VILA Model Version**: v1 (google/vila/tensorFlow2/image)
- **Script Version**: 2.1.1
- **Last Updated**: 2025-10-09
- **WSL Integration**: ✅ Enabled
- **Path Conversion**: ✅ All drive letters supported

## Next Steps

1. ✅ Verify WSL is working: `wsl --version`
2. ✅ Test VILA batch file: Drop an image onto `run_vila_drag_drop.bat`
3. ✅ Check Kaggle auth if model fails to load
4. ✅ For batch processing, use `create_gallery.bat` instead

## Support

For issues or questions:
- See `README_VILA.md` for VILA-specific setup
- See `VILA_FIXES_SUMMARY.md` for recent fixes
- See `WSL_WRAPPER_VERIFICATION.md` for WSL configuration

---

**Quick Start**: Just drag your image onto `run_vila_drag_drop.bat`! 🎨


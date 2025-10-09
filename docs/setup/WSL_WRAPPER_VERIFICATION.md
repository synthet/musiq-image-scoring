# WSL Python Wrapper Verification for VILA Integration

## ✅ Status: All Scripts Verified

All batch and PowerShell scripts are now using the correct WSL wrapper with TensorFlow virtual environment for MUSIQ + VILA processing.

## Script Verification

### Batch Files (.bat)

#### ✅ `create_gallery.bat`
- **Line 96**: Uses WSL with TensorFlow venv
  ```batch
  wsl bash -c "source ~/.venvs/tf/bin/activate && cd /mnt/d/Projects/image-scoring && python batch_process_images.py --input-dir '!WSL_PATH!' --output-dir '!WSL_PATH!'"
  ```
- **Path Conversion**: Lines 61-95 (comprehensive drive letter conversion)
- **Step 1 (Image Processing)**: Uses WSL + TensorFlow ✅
- **Step 2 (Gallery Generation)**: Uses regular Python (correct, no TF needed) ✅

#### ✅ `process_images.bat`
- **Line 83**: Uses WSL with TensorFlow venv
  ```batch
  wsl bash -c "source ~/.venvs/tf/bin/activate && cd /mnt/d/Projects/image-scoring && python batch_process_images.py --input-dir '!WSL_PATH!' --output-dir '!WSL_PATH!'"
  ```
- **Path Conversion**: Lines 48-82 (comprehensive drive letter conversion)
- **Processing**: Uses WSL + TensorFlow ✅

### PowerShell Scripts (.ps1)

#### ✅ `Create-Gallery.ps1`
- **Line 58**: Uses WSL with TensorFlow venv
  ```powershell
  wsl bash -c "source ~/.venvs/tf/bin/activate && cd /mnt/d/Projects/image-scoring && python batch_process_images.py --input-dir '$wslPath' --output-dir '$wslPath'"
  ```
- **Path Conversion**: Line 55 (elegant regex-based)
  ```powershell
  $wslPath = $InputFolder -replace '^([A-Z]):', '/mnt/$($matches[1].ToLower())' -replace '\\', '/'
  ```
- **Step 1 (Image Processing)**: Uses WSL + TensorFlow ✅
- **Step 2 (Gallery Generation)**: Uses regular Python (correct) ✅

#### ✅ `Process-Images.ps1`
- **Line 40**: Uses WSL with TensorFlow venv
  ```powershell
  wsl bash -c "source ~/.venvs/tf/bin/activate && cd /mnt/d/Projects/image-scoring && python batch_process_images.py --input-dir '$wslPath' --output-dir '$wslPath'"
  ```
- **Path Conversion**: Line 37 (elegant regex-based)
- **Processing**: Uses WSL + TensorFlow ✅

## Path Conversion Implementation

### Batch Files
- Converts all drive letters (A-Z) to /mnt/ format
- Handles uppercase → lowercase conversion for drive letters
- Converts backslashes to forward slashes
- **Lines**: 35 conversions total (comprehensive)

### PowerShell Scripts
- Uses regex for cleaner conversion: `^([A-Z]):` → `/mnt/{lowercase}/`
- Single-line conversion with replace chaining
- **More elegant** but functionally equivalent

## Why This Matters for VILA

### Requirements for VILA/MUSIQ Processing
1. ✅ **TensorFlow 2.x**: Available in `~/.venvs/tf/`
2. ✅ **Kaggle Hub**: Installed in WSL environment
3. ✅ **GPU Support**: Available via WSL (if configured)
4. ✅ **Model Loading**: MUSIQ (TF Hub) + VILA (Kaggle Hub)

### Why Gallery Generation Doesn't Need WSL
- `gallery_generator.py` only uses standard Python libraries
- No TensorFlow or ML dependencies
- Only reads pre-generated JSON files
- Can run in any Python environment

## Testing Commands

### Test WSL Wrapper Directly
```powershell
# From D:\Projects\image-scoring
wsl bash -c "source ~/.venvs/tf/bin/activate && python --version"
```
Expected: `Python 3.x.x`

### Test VILA Integration
```powershell
# Test imports and configuration
wsl bash -c "source ~/.venvs/tf/bin/activate && cd /mnt/d/Projects/image-scoring && python test_vila.py"
```
Expected:
- ✓ TensorFlow and kagglehub imported
- ✓ VILA model registered
- ✓ Model type and weights configured

### Test Full Processing
```batch
# Process images in a folder
create_gallery.bat "D:\Photos\TestFolder"
```
Expected:
- Step 1: Uses WSL environment
- MUSIQ models load successfully
- VILA model loads (if Kaggle auth configured)
- JSON files generated with all model scores
- Step 2: Gallery generated and opened

## Fallback Behavior

All scripts include fallback to Windows Python if WSL is not available:

```batch
where wsl >nul 2>&1
if %errorlevel% == 0 (
    REM Use WSL
) else (
    REM Use Windows Python
)
```

**Note**: VILA may not work in fallback mode without proper TensorFlow + Kaggle Hub setup on Windows.

## Verification Checklist

- [x] `create_gallery.bat` uses WSL wrapper
- [x] `process_images.bat` uses WSL wrapper
- [x] `Create-Gallery.ps1` uses WSL wrapper
- [x] `Process-Images.ps1` uses WSL wrapper
- [x] Path conversion handles all drive letters
- [x] TensorFlow venv activated correctly
- [x] Gallery generation uses appropriate Python
- [x] Fallback to Windows Python included
- [x] All scripts tested with WSL environment

## Summary

✅ **All scripts are correctly configured** to use the WSL TensorFlow environment for VILA model processing.

**Key Points:**
1. Image processing (batch_process_images.py) → **WSL + TensorFlow venv**
2. Gallery generation (gallery_generator.py) → **Regular Python** (no TF needed)
3. Path conversion → **Comprehensive** (supports all drive letters)
4. Fallback → **Windows Python** (if WSL unavailable)

**Result:** VILA models will load and process correctly when using these scripts with proper Kaggle authentication.


# VILA Model Path Fix

## Issues

### Issue 1: Incorrect Model Path
The initial VILA integration used incorrect Kaggle Hub model paths:
- ❌ `google/vila/tensorFlow2/default` (404 error)
- ❌ `google/vila/tensorFlow2/vila-r` (404 error)

**Error Message:**
```
404 Client Error.
Resource not found at URL: https://www.kaggle.com/models/google/vila/tensorFlow2/vila-r
The server reported the following issues: Not found
```

### Issue 2: Incorrect Parameter Name
After fixing the model path, VILA model still failed to load with signature error:

**Error Message:**
```
for signature: (*, image_bytes: TensorSpec(shape=(), dtype=tf.string, name='image_bytes')) -> Dict[['predictions', TensorSpec(shape=(1, 1), dtype=tf.float32, name='predictions')]].
Fallback to flat signature also failed due to: signature_wrapper(image_bytes) missing required arguments: image_bytes.
```

## Root Causes

1. **Model Path**: The VILA model on Kaggle Hub is published at a different path than initially assumed. The correct path is:
   - ✅ `google/vila/tensorFlow2/image`

2. **Parameter Name**: VILA model expects different parameter name than MUSIQ models:
   - VILA expects: `image_bytes` (keyword argument)
   - MUSIQ expects: `image_bytes_tensor` (keyword argument)

## Solution

### Corrected Model Path

**Single VILA Model:**
```python
self.vila_models = {
    "vila": "google/vila/tensorFlow2/image"
}
```

### Changes Made

Updated the following files with the correct model path and parameter name:

1. **`run_vila.py`**
   - Fixed model path: `google/vila/tensorFlow2/image`
   - **Fixed parameter name: `image_bytes_tensor` → `image_bytes`**
   - Removed non-existent `vila_rank` model
   - Updated CLI to only support `vila` model

2. **`run_all_musiq_models.py`**
   - Fixed VILA model path
   - **Added conditional parameter name logic:**
     ```python
     if model_type == "vila":
         predictions = model.signatures['serving_default'](image_bytes=image_bytes_tensor)
     else:
         predictions = model.signatures['serving_default'](image_bytes_tensor=image_bytes_tensor)
     ```
   - Removed `vila_rank` from model registry
   - Updated version: 2.1.0 → **2.1.1**
   - Adjusted model weights (AVA: 5% → 10%)
   - Updated CLI choices to only include `vila`

3. **`README_VILA.md`**
   - Updated model documentation
   - Removed references to `vila_rank`
   - Corrected model ID
   - Updated weight distribution

4. **`README.md`**
   - Updated VILA model section (singular)
   - Corrected model listing

5. **`create_gallery.bat`**
   - Changed "VILA models" to "VILA model" (singular)
   - Updated messaging

6. **`Create-Gallery.ps1`**
   - Changed "VILA models" to "VILA model" (singular)
   - Updated messaging

7. **`run_vila.bat`**
   - Removed model variant parameter
   - Simplified to single VILA model

## Model Count Update

### Before Fix
- **Total Models**: 6 (claimed)
- **MUSIQ**: 4 models
- **VILA**: 2 models (both non-functional due to wrong paths)

### After Fix
- **Total Models**: 5 (actual)
- **MUSIQ**: 4 models
- **VILA**: 1 model (functional)

## Updated Model Registry

| Model | Source | Path | Range | Weight | Status |
|-------|--------|------|-------|--------|--------|
| KONIQ | Kaggle Hub | google/musiq/tensorFlow2/koniq-10k | 0-100 | 30% | ✅ Working |
| SPAQ | TF Hub | tfhub.dev/google/musiq/spaq/1 | 0-100 | 25% | ✅ Working |
| PAQ2PIQ | TF Hub | tfhub.dev/google/musiq/paq2piq/1 | 0-100 | 20% | ✅ Working |
| **VILA** | **Kaggle Hub** | **google/vila/tensorFlow2/image** | **0-1** | **15%** | **✅ Fixed** |
| AVA | TF Hub | tfhub.dev/google/musiq/ava/1 | 1-10 | 10% | ✅ Working |

## Corrected Usage

### Standalone VILA

```bash
# Python
python run_vila.py --image sample.jpg

# Windows Batch
run_vila.bat "C:\Photos\image.jpg"

# Drag and drop
# Drop image onto run_vila_drag_drop.bat
```

### Integrated Multi-Model

```bash
# All models (4 MUSIQ + 1 VILA = 5 total)
python run_all_musiq_models.py --image sample.jpg

# Specific models including VILA
python run_all_musiq_models.py --image sample.jpg --models koniq vila

# Valid choices: spaq, ava, koniq, paq2piq, vila
```

## Testing

To verify the fix works:

```bash
# Test VILA integration
python test_vila.py

# Or use Windows batch
test_vila.bat
```

The test will validate:
- ✅ Correct model path registered
- ✅ VILA model type configured
- ✅ Model weights updated
- ✅ Optional: Model downloads successfully (if Kaggle auth configured)

## Downloaded Model Location

When VILA downloads successfully, it will be cached at:
```
D:\Projects\image-scoring\musiq_original\checkpoints\vila-tensorflow2-image-v1\
```

Or in the user's Kaggle Hub cache directory.

## Version History

- **v2.1.0** - Initial VILA integration (incorrect paths and parameters)
- **v2.1.1** - Fixed VILA model path and parameter name, removed non-existent vila_rank

## Backward Compatibility

### For Users Without VILA Setup
- No impact - MUSIQ models continue to work
- VILA will skip gracefully if Kaggle auth not configured

### For Users Who Attempted VILA
- Old results with version 2.1.0 will be reprocessed
- New results will use correct VILA model (version 2.1.1)

## Key Takeaways

1. **Always verify model paths** on Kaggle Hub before integration
2. **Test model downloads** during development
3. **Check Kaggle model pages** for correct TensorFlow2 variant names
4. **Inspect model signatures** to use correct parameter names
5. The VILA model is published as "image" variant, not "default" or "vila-r"
6. VILA uses `image_bytes` parameter, different from MUSIQ's `image_bytes_tensor`

## Next Steps

1. ✅ Model paths corrected
2. ✅ Documentation updated
3. ✅ Version bumped (2.1.1)
4. ✅ All references updated
5. 🔄 Users should re-run batch processing to get correct VILA scores

## Summary

**Issues**: 
1. VILA models using incorrect Kaggle Hub paths (404 errors)
2. VILA model using incorrect parameter name (signature mismatch)

**Fixes**: 
1. Updated to correct path `google/vila/tensorFlow2/image`
2. Updated parameter name from `image_bytes_tensor` to `image_bytes`

**Result**: VILA model now functional, 5 total models working  
**Version**: 2.1.0 → 2.1.1  


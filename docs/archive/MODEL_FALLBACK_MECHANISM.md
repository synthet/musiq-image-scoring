# Model Fallback Mechanism (Legacy)

> [!WARNING]
> **Deprecated System**: This document describes the unified fallback mechanism (TFHub -> Kaggle) primarily designed for the **VILA** model. Since VILA has been disabled in v2.5.1, this mechanism is largely irrelevant for the current Hybrid (MUSIQ + LIQE) pipeline.



**Version**: 2.2.0  
**Date**: 2025-10-09  
**Feature**: Unified TensorFlow Hub â†’ Kaggle Hub fallback for all models

---

## Overview

All models now implement a unified fallback mechanism that tries TensorFlow Hub first, then automatically falls back to Kaggle Hub if needed. This provides maximum reliability across different network conditions and authentication states.

---

## Problem Statement

### Before (v2.1.2 and earlier)

Models were hardcoded to specific sources:

```python
# Rigid source assignment
self.model_sources = {
    "spaq": "tfhub",          # Only TF Hub
    "ava": "tfhub",           # Only TF Hub
    "koniq": "kaggle",        # Only Kaggle Hub
    "paq2piq": "tfhub",       # Only TF Hub
    "vila": "vila_kaggle"     # Only Kaggle Hub
}
```

**Issues**:
- âŒ If TF Hub was down, SPAQ/AVA/PAQ2PIQ would fail completely
- âŒ KONIQ required Kaggle auth even though TF Hub might be available
- âŒ VILA required Kaggle auth even though it's on TF Hub too
- âŒ No redundancy or fallback options
- âŒ Different loading logic for each source type

---

## Solution (v2.2.0)

### Unified Fallback Architecture

All models now have both sources defined with automatic fallback:

```python
self.model_sources = {
    "spaq": {
        "tfhub": "https://tfhub.dev/google/musiq/spaq/1",
        "kaggle": "google/musiq/tensorFlow2/spaq"
    },
    "ava": {
        "tfhub": "https://tfhub.dev/google/musiq/ava/1",
        "kaggle": "google/musiq/tensorFlow2/ava"
    },
    "koniq": {
        "tfhub": None,  # Not available on TF Hub
        "kaggle": "google/musiq/tensorFlow2/koniq-10k"
    },
    "paq2piq": {
        "tfhub": "https://tfhub.dev/google/musiq/paq2piq/1",
        "kaggle": "google/musiq/tensorFlow2/paq2piq"
    },
    "vila": {
        "tfhub": "https://tfhub.dev/google/vila/image/1",
        "kaggle": "google/vila/tensorFlow2/image"
    }
}
```

---

## Loading Logic Flow

```
â”Œâ”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”
â”‚   Model Loading Request             â”‚
â””â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”¬â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”˜
               â”‚
               â–¼
â”Œâ”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”
â”‚   Check TensorFlow Hub Available?   â”‚
â””â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”¬â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”˜
               â”‚
         â”Œâ”€â”€â”€â”€â”€â”´â”€â”€â”€â”€â”€â”
         â”‚           â”‚
      YESâ”‚           â”‚NO
         â”‚           â”‚
         â–¼           â–¼
â”Œâ”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”  â”Œâ”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”
â”‚ Try TF Hub     â”‚  â”‚ Skip TF Hub    â”‚
â””â”€â”€â”€â”€â”€â”€â”€â”€â”¬â”€â”€â”€â”€â”€â”€â”€â”˜  â””â”€â”€â”€â”€â”€â”€â”€â”€â”¬â”€â”€â”€â”€â”€â”€â”€â”˜
         â”‚                    â”‚
    â”Œâ”€â”€â”€â”€â”´â”€â”€â”€â”€â”              â”‚
    â”‚         â”‚              â”‚
SUCCESSâ”‚   FAILâ”‚              â”‚
    â”‚         â”‚              â”‚
    â–¼         â–¼              â–¼
â”Œâ”€â”€â”€â”€â”€â”€â”€â”€â”  â”Œâ”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”
â”‚ DONE âœ“ â”‚  â”‚ Check Kaggle Hub     â”‚
â””â”€â”€â”€â”€â”€â”€â”€â”€â”˜  â”‚ Available?           â”‚
            â””â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”¬â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”˜
                       â”‚
                 â”Œâ”€â”€â”€â”€â”€â”´â”€â”€â”€â”€â”€â”
                 â”‚           â”‚
              YESâ”‚           â”‚NO
                 â”‚           â”‚
                 â–¼           â–¼
        â”Œâ”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”  â”Œâ”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”
        â”‚ Try Kaggle Hub â”‚  â”‚ FAIL âœ—         â”‚
        â””â”€â”€â”€â”€â”€â”€â”€â”€â”¬â”€â”€â”€â”€â”€â”€â”€â”˜  â”‚ No sources     â”‚
                 â”‚          â”‚ available      â”‚
            â”Œâ”€â”€â”€â”€â”´â”€â”€â”€â”€â”     â””â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”˜
            â”‚         â”‚
        SUCCESSâ”‚   FAILâ”‚
            â”‚         â”‚
            â–¼         â–¼
        â”Œâ”€â”€â”€â”€â”€â”€â”€â”€â”  â”Œâ”€â”€â”€â”€â”€â”€â”€â”€â”
        â”‚ DONE âœ“ â”‚  â”‚ FAIL âœ— â”‚
        â””â”€â”€â”€â”€â”€â”€â”€â”€â”˜  â””â”€â”€â”€â”€â”€â”€â”€â”€â”˜
```

---

## Implementation Details

### Load Model Method

```python
def load_model(self, model_name: str) -> bool:
    """
    Load a model with fallback mechanism.
    
    Priority:
    1. TensorFlow Hub (fast, no auth)
    2. Kaggle Hub (fallback, requires auth)
    """
    if model_name not in self.model_sources:
        return False
    
    sources = self.model_sources[model_name]
    tfhub_url = sources.get("tfhub")
    kaggle_path = sources.get("kaggle")
    
    # Try TensorFlow Hub first
    if tfhub_url:
        try:
            print(f"Loading {model_name.upper()} from TensorFlow Hub")
            model = hub.load(tfhub_url)
            self.models[model_name] = model
            print(f"âœ“ {model_name.upper()} loaded successfully from TF Hub")
            return True
        except Exception as e:
            print(f"âš  TF Hub failed: {e}")
            print(f"  Falling back to Kaggle Hub...")
    
    # Fall back to Kaggle Hub
    if kaggle_path:
        try:
            print(f"Loading {model_name.upper()} from Kaggle Hub")
            model_path = kagglehub.model_download(kaggle_path)
            model = tf.saved_model.load(model_path)
            self.models[model_name] = model
            print(f"âœ“ {model_name.upper()} loaded successfully from Kaggle Hub")
            return True
        except Exception as e:
            print(f"âœ— Failed to load from Kaggle Hub: {e}")
            return False
    
    # Both sources failed or unavailable
    print(f"âœ— No available sources succeeded")
    return False
```

---

## Model Availability Matrix

| Model | TensorFlow Hub | Kaggle Hub | Fallback Benefit |
|-------|----------------|------------|------------------|
| **SPAQ** | âœ… Primary | âœ… Fallback | High - Works without auth |
| **AVA** | âœ… Primary | âœ… Fallback | High - Works without auth |
| **KONIQ** | âŒ Not available | âœ… Primary | Medium - Only on Kaggle |
| **PAQ2PIQ** | âœ… Primary | âœ… Fallback | High - Works without auth |
| **VILA** | âœ… Primary | âœ… Fallback | High - Works without auth |

---

## Benefits

### 1. Improved Reliability âœ…
- **Before**: Single point of failure per model
- **After**: Automatic fallback if primary source fails

### 2. Faster Loading âœ…
- **TF Hub** typically loads faster (CDN-backed)
- **Kaggle Hub** used only when necessary

### 3. No Authentication When Possible âœ…
- **TF Hub**: No authentication required
- **Kaggle Hub**: Authentication only used as fallback

### 4. Better User Experience âœ…
- Clear status messages with emoji indicators
- Users see which source was used
- Transparent fallback process

### 5. Future-Proof Architecture âœ…
- Easy to add more sources (local cache, mirrors, custom servers)
- Consistent pattern for all models
- Extensible design

---

## Example Output

### Successful TF Hub Load
```
Loading SPAQ model from TensorFlow Hub: https://tfhub.dev/google/musiq/spaq/1
âœ“ SPAQ model loaded successfully from TensorFlow Hub
```

### Fallback to Kaggle Hub
```
Loading AVA model from TensorFlow Hub: https://tfhub.dev/google/musiq/ava/1
âš  TensorFlow Hub failed for AVA: Network error
  Falling back to Kaggle Hub...
Loading AVA model from Kaggle Hub: google/musiq/tensorFlow2/ava
Model downloaded to: /home/user/.cache/kagglehub/models/google/musiq/...
âœ“ AVA model loaded successfully from Kaggle Hub
```

### KONIQ (Kaggle Hub only)
```
Loading KONIQ model from Kaggle Hub: google/musiq/tensorFlow2/koniq-10k
Model downloaded to: /home/user/.cache/kagglehub/models/google/musiq/...
âœ“ KONIQ model loaded successfully from Kaggle Hub
```

### Complete Failure
```
Loading CUSTOM model from TensorFlow Hub: https://tfhub.dev/google/custom/1
âš  TensorFlow Hub failed for CUSTOM: Model not found
  Falling back to Kaggle Hub...
Loading CUSTOM model from Kaggle Hub: google/custom/tensorFlow2/model
âœ— Failed to load CUSTOM model from Kaggle Hub: 404 Not Found

Note: Kaggle Hub models require authentication.
See [README_VILA.md](vila/README_VILA.md) for Kaggle setup instructions.

âœ— Failed to load CUSTOM model: No available sources succeeded
```

---

## Testing

### Test Fallback Behavior

```python
# Test 1: TF Hub success (no fallback needed)
scorer = MultiModelMUSIQ()
success = scorer.load_model("spaq")
# Expected: Loads from TF Hub
# Kaggle Hub is not attempted

# Test 2: TF Hub unavailable (fallback to Kaggle Hub)
# Simulate by blocking TF Hub access
scorer = MultiModelMUSIQ()
success = scorer.load_model("spaq")
# Expected: Tries TF Hub, fails, falls back to Kaggle Hub

# Test 3: Kaggle Hub only model
scorer = MultiModelMUSIQ()
success = scorer.load_model("koniq")
# Expected: Skips TF Hub (None), loads directly from Kaggle Hub

# Test 4: Both sources fail
scorer = MultiModelMUSIQ()
success = scorer.load_model("invalid_model")
# Expected: Returns False, clear error message
```

### Test All Models

```bash
# Run comprehensive test
wsl bash -c "source ~/.venvs/tf/bin/activate && cd /path/to/image-scoring && python run_all_musiq_models.py --image test_image.jpg"

# Expected output:
# - Models load from TF Hub when possible
# - Fallback to Kaggle Hub if needed
# - All 5 models load successfully
```

---

## Performance Comparison

### TensorFlow Hub (Primary)
- **Speed**: â­â­â­â­â­ Fast (CDN-backed)
- **Reliability**: â­â­â­â­ High (Google infrastructure)
- **Auth**: âœ… None required
- **Cache**: âœ… Local cache in `~/.keras/`

### Kaggle Hub (Fallback)
- **Speed**: â­â­â­ Moderate (depends on region)
- **Reliability**: â­â­â­â­ High (Kaggle infrastructure)
- **Auth**: âš ï¸ Required (`kaggle.json`)
- **Cache**: âœ… Local cache in `~/.cache/kagglehub/`

---

## Migration Guide

### For Users

**No action required!** The fallback mechanism works automatically.

- If you have Kaggle auth configured: Models load from best available source
- If you don't have Kaggle auth: Models load from TF Hub when possible
- Existing JSON results remain compatible

### For Developers

**Model source definitions changed**:

```python
# OLD (v2.1.2)
self.model_sources = {
    "spaq": "tfhub",
    "ava": "tfhub"
}

# NEW (v2.2.0)
self.model_sources = {
    "spaq": {
        "tfhub": "url",
        "kaggle": "path"
    },
    "ava": {
        "tfhub": "url",
        "kaggle": "path"
    }
}
```

**Update custom code** to use new format if you've extended the system.

---

## Future Enhancements

### Potential Additions

1. **Local Cache Priority**
   ```python
   "spaq": {
       "local": "/path/to/cached/model",  # Try first
       "tfhub": "url",                    # Try second
       "kaggle": "path"                   # Try third
   }
   ```

2. **Custom Mirrors**
   ```python
   "spaq": {
       "mirror": "https://custom-mirror.com/spaq",
       "tfhub": "url",
       "kaggle": "path"
   }
   ```

3. **Parallel Loading**
   - Try multiple sources simultaneously
   - Use whichever responds first

4. **Health Check**
   - Pre-check source availability
   - Skip known-failing sources

5. **Metrics Collection**
   - Track which sources are used
   - Identify performance patterns
   - Optimize source priority

---

## Related Documents

- [Docs index](../README.md)
- [CHANGELOG.md](../../CHANGELOG.md) - Version 2.2.0 release notes
- [README_VILA.md](vila/README_VILA.md) - Kaggle authentication setup
- [WSL_WRAPPER_VERIFICATION.md](../guides/setup/WSL_WRAPPER_VERIFICATION.md) - Environment verification
- [VILA_ALL_FIXES_SUMMARY.md](../vila/VILA_ALL_FIXES_SUMMARY.md) - Complete VILA integration history

---

## Version History

- **v2.2.0** (2025-10-09): Unified fallback mechanism implemented
- **v2.1.2** (2025-10-09): VILA score range correction
- **v2.1.1** (2025-10-09): VILA path and parameter fixes
- **v2.1.0** (2025-10-08): Initial VILA integration
- **v2.0.0** (2025-06-12): Multi-model MUSIQ support

---

## Summary

âœ… **Implemented**: Unified TFHub â†’ Kaggle Hub fallback for all 5 models  
âœ… **Benefit**: Improved reliability without requiring authentication  
âœ… **Impact**: No breaking changes, fully backward compatible  
âœ… **Version**: 2.2.0 (minor version bump)  

**Status**: Production Ready ðŸŽ‰


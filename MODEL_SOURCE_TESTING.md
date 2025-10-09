# Model Source Testing Guide

**Purpose**: Verify all TensorFlow Hub and Kaggle Hub model URLs are accessible and valid.

---

## Overview

The `test_model_sources.py` script tests all model sources defined in `run_all_musiq_models.py` to ensure:
- TensorFlow Hub URLs are accessible
- Kaggle Hub paths are valid
- Fallback mechanism will work correctly
- Authentication is properly configured

---

## Quick Start

### Test TensorFlow Hub Only (Recommended First Test)

```bash
# Windows Batch
test_model_sources.bat

# PowerShell
.\Test-ModelSources.ps1

# Direct Python (WSL)
wsl bash -c "source ~/.venvs/tf/bin/activate && cd /mnt/d/Projects/image-scoring && python test_model_sources.py"

# Direct Python (Windows)
python test_model_sources.py
```

**Why Start Here:**
- ✅ Fast (no downloads)
- ✅ No authentication required
- ✅ Tests most common source (TF Hub)

### Test Both Sources (Full Validation)

```bash
# Validate Kaggle paths without downloading
test_model_sources.bat --test-kaggle --skip-download

# Full test with Kaggle downloads (requires auth)
test_model_sources.bat --test-kaggle

# PowerShell versions
.\Test-ModelSources.ps1 -TestKaggle -SkipDownload
.\Test-ModelSources.ps1 -TestKaggle
```

---

## Usage

### Command-Line Options

| Option | Description |
|--------|-------------|
| `--test-kaggle` | Test Kaggle Hub sources (requires kagglehub package) |
| `--skip-download` | Validate Kaggle paths without downloading models |
| `--verbose` | Show detailed error messages |

### Examples

```bash
# 1. Quick TF Hub test (no auth needed)
python test_model_sources.py

# 2. Validate all paths without downloads
python test_model_sources.py --test-kaggle --skip-download

# 3. Full test with downloads (requires Kaggle auth)
python test_model_sources.py --test-kaggle

# 4. Verbose output for debugging
python test_model_sources.py --test-kaggle --verbose
```

---

## Expected Output

### Successful Test

```
Testing imports...
✓ TensorFlow: 2.15.0
✓ TensorFlow Hub available
✓ Kaggle Hub available

======================================================================
MODEL SOURCE AVAILABILITY TEST
======================================================================
✓ Kaggle authentication found

======================================================================
Testing Model Sources
======================================================================

📦 Testing SPAQ model:
  Testing TF Hub: https://tfhub.dev/google/musiq/spaq/1
    TF Hub:     ✓ Accessible (signatures: ['serving_default'])
  Testing Kaggle Hub: google/musiq/tensorFlow2/spaq
    Kaggle Hub: ✓ Accessible (cached at: /home/user/.cache/kagglehub...)

📦 Testing AVA model:
  Testing TF Hub: https://tfhub.dev/google/musiq/ava/1
    TF Hub:     ✓ Accessible (signatures: ['serving_default'])
  Testing Kaggle Hub: google/musiq/tensorFlow2/ava
    Kaggle Hub: ✓ Accessible (cached at: /home/user/.cache/kagglehub...)

📦 Testing KONIQ model:
    TF Hub:     N/A - Not available on TF Hub
  Testing Kaggle Hub: google/musiq/tensorFlow2/koniq-10k
    Kaggle Hub: ✓ Accessible (cached at: /home/user/.cache/kagglehub...)

📦 Testing PAQ2PIQ model:
  Testing TF Hub: https://tfhub.dev/google/musiq/paq2piq/1
    TF Hub:     ✓ Accessible (signatures: ['serving_default'])
  Testing Kaggle Hub: google/musiq/tensorFlow2/paq2piq
    Kaggle Hub: ✓ Accessible (cached at: /home/user/.cache/kagglehub...)

📦 Testing VILA model:
  Testing TF Hub: https://tfhub.dev/google/vila/image/1
    TF Hub:     ✓ Accessible (signatures: ['serving_default'])
  Testing Kaggle Hub: google/vila/tensorFlow2/image
    Kaggle Hub: ✓ Accessible (cached at: /home/user/.cache/kagglehub...)

======================================================================
SUMMARY
======================================================================

Model           TensorFlow Hub                 Kaggle Hub                    
----------------------------------------------------------------------
✓ spaq          ✓                              ✓                             
✓ ava           ✓                              ✓                             
✓ koniq         N/A                            ✓                             
✓ paq2piq       ✓                              ✓                             
✓ vila          ✓                              ✓                             

======================================================================
RECOMMENDATIONS
======================================================================
✓ All models have at least one accessible source
✓ Model loading should work with fallback mechanism

======================================================================
FALLBACK MECHANISM STATUS
======================================================================
✓ SPAQ       - Full fallback (TF Hub primary, Kaggle backup)
✓ AVA        - Full fallback (TF Hub primary, Kaggle backup)
⚠ KONIQ      - Kaggle only (no TF Hub available)
✓ PAQ2PIQ    - Full fallback (TF Hub primary, Kaggle backup)
✓ VILA       - Full fallback (TF Hub primary, Kaggle backup)

======================================================================
Test completed successfully!
======================================================================
```

### Failed Test (Example)

```
📦 Testing SPAQ model:
  Testing TF Hub: https://tfhub.dev/google/musiq/spaq/1
    TF Hub:     ✗ Network Error
  Testing Kaggle Hub: google/musiq/tensorFlow2/spaq
    Kaggle Hub: ✗ Authentication Required

======================================================================
RECOMMENDATIONS
======================================================================
⚠ SPAQ: No accessible sources!

⚠ Some models require Kaggle authentication
  Run: mkdir -p ~/.kaggle && cp /path/to/kaggle.json ~/.kaggle/
  See: README_VILA.md for setup instructions
```

---

## What Gets Tested

### TensorFlow Hub Tests

For each TF Hub URL:
1. ✅ URL accessibility
2. ✅ Model can be loaded
3. ✅ Model has expected signatures
4. ❌ Network errors
5. ❌ 404 Not Found errors

### Kaggle Hub Tests

For each Kaggle Hub path:
1. ✅ Path format validation
2. ✅ Model can be downloaded (with `--test-kaggle`)
3. ✅ Downloaded path exists
4. ✅ Authentication works
5. ❌ Authentication errors
6. ❌ 404 Not Found errors
7. ❌ Network errors

---

## Models Tested

| Model | TF Hub URL | Kaggle Hub Path |
|-------|-----------|-----------------|
| **SPAQ** | https://tfhub.dev/google/musiq/spaq/1 | google/musiq/tensorFlow2/spaq |
| **AVA** | https://tfhub.dev/google/musiq/ava/1 | google/musiq/tensorFlow2/ava |
| **KONIQ** | *(Not on TF Hub)* | google/musiq/tensorFlow2/koniq-10k |
| **PAQ2PIQ** | https://tfhub.dev/google/musiq/paq2piq/1 | google/musiq/tensorFlow2/paq2piq |
| **VILA** | https://tfhub.dev/google/vila/image/1 | google/vila/tensorFlow2/image |

---

## Troubleshooting

### "TensorFlow not available"

**Solution**: Use WSL with TensorFlow environment
```bash
wsl bash -c "source ~/.venvs/tf/bin/activate && cd /mnt/d/Projects/image-scoring && python test_model_sources.py"
```

### "Kaggle Hub not available"

**Solution**: Install kagglehub
```bash
pip install kagglehub==0.3.4
```

### "Authentication Required" for Kaggle

**Solution**: Set up Kaggle credentials
```bash
# In WSL
mkdir -p ~/.kaggle
cp /mnt/c/Users/YourName/Downloads/kaggle.json ~/.kaggle/
chmod 600 ~/.kaggle/kaggle.json
```

See [README_VILA.md](README_VILA.md) for detailed setup.

### "Network Error"

**Possible Causes**:
- No internet connection
- Firewall blocking access
- TF Hub or Kaggle Hub temporarily down

**Solution**: 
- Check internet connection
- Try again later
- Test individual sources to isolate issue

### "404 Not Found"

**Meaning**: Model URL/path is incorrect

**Action**: 
- Check `run_all_musiq_models.py` for typos
- Verify model exists on TF Hub or Kaggle Hub
- Update model paths if models have been moved

---

## Integration with Development Workflow

### When to Run This Test

1. **Before Deployment**: Verify all model sources
2. **After Updating Model Paths**: Ensure new paths work
3. **Troubleshooting**: Diagnose model loading issues
4. **Environment Setup**: Verify new installations
5. **Network Issues**: Check which sources are accessible

### Continuous Integration

```yaml
# Example CI workflow
steps:
  - name: Test Model Sources
    run: |
      python test_model_sources.py
      # Exit with error if test fails
```

### Pre-Commit Hook

```bash
#!/bin/bash
# .git/hooks/pre-commit
python test_model_sources.py --test-kaggle --skip-download
if [ $? -ne 0 ]; then
    echo "Model source test failed!"
    exit 1
fi
```

---

## Performance Notes

### Test Duration

| Test Type | Duration | Download Size |
|-----------|----------|---------------|
| TF Hub only | ~30 seconds | 0 MB (no downloads) |
| Kaggle validation | ~45 seconds | 0 MB (validation only) |
| Full Kaggle test | ~5-10 minutes | ~500 MB (all models) |

**Tip**: Use `--skip-download` for quick validation during development.

### Caching

- **TF Hub**: Models cached in `~/.keras/`
- **Kaggle Hub**: Models cached in `~/.cache/kagglehub/`
- **Subsequent Tests**: Much faster due to caching

---

## Files

| File | Purpose |
|------|---------|
| `test_model_sources.py` | Main test script (Python) |
| `test_model_sources.bat` | Windows batch wrapper |
| `Test-ModelSources.ps1` | PowerShell wrapper |
| `MODEL_SOURCE_TESTING.md` | This documentation |

---

## Related Documents

- [MODEL_FALLBACK_MECHANISM.md](MODEL_FALLBACK_MECHANISM.md) - Fallback system details
- [README_VILA.md](README_VILA.md) - Kaggle authentication setup
- [WSL_WRAPPER_VERIFICATION.md](WSL_WRAPPER_VERIFICATION.md) - Environment verification
- [CHANGELOG.md](CHANGELOG.md) - Version history

---

## Example Use Cases

### 1. First-Time Setup Verification

```bash
# After setting up environment
python test_model_sources.py
# Expected: All TF Hub models accessible

# After configuring Kaggle auth
python test_model_sources.py --test-kaggle --skip-download
# Expected: All Kaggle paths valid
```

### 2. Troubleshooting Model Loading

```bash
# If models fail to load
python test_model_sources.py --test-kaggle --verbose
# Identifies which source is failing and why
```

### 3. Verifying New Model Paths

```bash
# After updating model paths in code
python test_model_sources.py --test-kaggle --skip-download
# Quick validation without large downloads
```

### 4. Network Diagnostics

```bash
# Check if TF Hub is accessible
python test_model_sources.py
# If fails, try Kaggle Hub as backup
python test_model_sources.py --test-kaggle
```

---

## Status Indicators

The test script uses emoji indicators:

| Indicator | Meaning |
|-----------|---------|
| ✓ | Success - source is accessible |
| ✗ | Error - source failed to load |
| ⚠ | Warning - partial functionality |
| N/A | Not applicable - source not available |

---

## Summary

✅ **Purpose**: Verify all model URLs are accessible  
✅ **Usage**: Simple command-line interface  
✅ **Testing**: TF Hub + Kaggle Hub validation  
✅ **Integration**: Works with existing infrastructure  
✅ **Documentation**: Complete guide included  

**Recommendation**: Run `test_model_sources.py` before any major deployment or after environment changes to ensure all model sources are accessible.

---

**Created**: 2025-10-09  
**Version**: 1.0  
**Compatibility**: Works with v2.2.0+ model fallback mechanism


# VILA Parameter Name Fix

## Problem

After fixing the VILA model path, the model still failed to load with a signature error:

```
for signature: (*, image_bytes: TensorSpec(shape=(), dtype=tf.string, name='image_bytes')) 
-> Dict[['predictions', TensorSpec(shape=(1, 1), dtype=tf.float32, name='predictions')]].

Fallback to flat signature also failed due to: signature_wrapper(image_bytes) 
missing required arguments: image_bytes.
```

## Root Cause

Different models expect different parameter names:

| Model Type | Parameter Name | Format |
|------------|----------------|--------|
| **VILA** | `image_bytes` | Keyword argument |
| **MUSIQ** | `image_bytes_tensor` | Keyword argument |

The code was using `image_bytes_tensor` for all models, which works for MUSIQ but fails for VILA.

## Solution

### Fix in `run_vila.py` (Standalone)

**Before:**
```python
result = serving_fn(image_bytes_tensor=image_bytes_tensor)
```

**After:**
```python
result = serving_fn(image_bytes=image_bytes_tensor)
```

### Fix in `run_all_musiq_models.py` (Multi-Model)

**Before:**
```python
predictions = model.signatures['serving_default'](image_bytes_tensor=image_bytes_tensor)
```

**After:**
```python
# Determine correct parameter name for model
# VILA models use 'image_bytes', MUSIQ models use 'image_bytes_tensor'
if model_type == "vila":
    predictions = model.signatures['serving_default'](image_bytes=image_bytes_tensor)
else:
    predictions = model.signatures['serving_default'](image_bytes_tensor=image_bytes_tensor)
```

## Testing

Run the integration test:

```bash
# WSL (recommended)
wsl bash -c "source ~/.venvs/tf/bin/activate && cd /mnt/d/Projects/image-scoring && python test_vila.py"

# Windows
python test_vila.py
```

Expected output:
```
✓ VILA integration is set up correctly
✓ All core components are functional
```

## Technical Details

### Model Signature Inspection

To inspect a model's signature in TensorFlow:

```python
import tensorflow as tf

model = tf.saved_model.load(model_path)
print(model.signatures['serving_default'].structured_input_signature)
```

For VILA:
```python
(*, image_bytes: TensorSpec(shape=(), dtype=tf.string, name='image_bytes'))
```

For MUSIQ:
```python
(*, image_bytes_tensor: TensorSpec(shape=(), dtype=tf.string, name='image_bytes_tensor'))
```

### Why This Matters

TensorFlow's `saved_model` signatures require exact parameter name matching when calling with keyword arguments. Passing the wrong parameter name results in:
- "missing required arguments" error
- Model fails to process input
- No fallback behavior

## Impact

✅ **Fixed:**
- VILA model now loads and processes images correctly
- Multi-model scoring includes VILA predictions
- Gallery generation can use VILA scores

✅ **Preserved:**
- MUSIQ models continue to work with existing parameter name
- No impact on MUSIQ-only workflows
- Backward compatible with MUSIQ results

## Related Files

- `run_vila.py` - Standalone VILA scorer
- `run_all_musiq_models.py` - Multi-model integration
- `VILA_MODEL_PATH_FIX.md` - Complete fix documentation
- `test_vila.py` - Integration tests

## Lessons Learned

1. Always inspect model signatures before integration
2. Different models may expect different parameter names
3. Test with actual model loading, not just imports
4. Add model-specific logic when handling multiple model types
5. Document parameter naming conventions

## Status

✅ **FIXED** - VILA model now functional with correct parameter name  
📅 **Version**: 2.1.1  
🧪 **Tested**: Integration tests pass in WSL environment


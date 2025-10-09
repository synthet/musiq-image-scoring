# VILA Score Range Correction

## Issue Identified

The VILA model score range was incorrectly documented as `0-10` in the codebase and documentation. According to the official TensorFlow Hub/Kaggle Hub documentation, the correct range is `0-1`.

## Official Documentation

From the VILA model page on TensorFlow Hub:

> **Output**: A dictionary of predictions containing
> - `predictions`: (1, 1) quality score range in **[0, 1]**

**Source**: 
- TensorFlow Hub: `https://tfhub.dev/google/vila/image/1`
- Kaggle Hub: `google/vila/tensorFlow2/image`
- Paper: CVPR 2023 - "VILA: Learning Image Aesthetics from User Comments with Vision-Language Pretraining"

## What Was Corrected

### Code Changes

#### 1. `run_all_musiq_models.py`

**Before:**
```python
self.model_ranges = {
    "spaq": (0.0, 100.0),
    "ava": (1.0, 10.0),
    "koniq": (0.0, 100.0),
    "paq2piq": (0.0, 100.0),
    "vila": (0.0, 10.0)  # ❌ INCORRECT
}
```

**After:**
```python
self.model_ranges = {
    "spaq": (0.0, 100.0),
    "ava": (1.0, 10.0),
    "koniq": (0.0, 100.0),
    "paq2piq": (0.0, 100.0),
    "vila": (0.0, 1.0)   # ✅ CORRECT
}
```

### Documentation Changes

#### Updated Files:
1. **`README.md`**
   - Changed: `range: 0-10` → `range: 0-1, normalized`

2. **`README_VILA.md`**
   - Changed model description: `0-10` → `0-1 (normalized aesthetic quality score)`
   - Updated example JSON output:
     ```json
     "vila": {
       "score": 0.785,        // was: 7.85
       "score_range": "0.0-1.0",  // was: "0.0-10.0"
       "normalized_score": 0.785
     }
     ```

3. **`VILA_MODEL_PATH_FIX.md`**
   - Added Range column to model registry table
   - Shows VILA range as `0-1`

4. **`VILA_FIXES_SUMMARY.md`**
   - Added Range column to model configuration table
   - Shows VILA range as `0-1`

5. **CLI Help Text** in `run_all_musiq_models.py`
   - Changed: `(range: 0-10)` → `(range: 0-1)`

## Impact

### ✅ No Breaking Changes
The correction does **NOT** affect functionality because:

1. **Normalization happens automatically**: The model range is used to normalize scores to [0, 1] for weighted scoring:
   ```python
   normalized_score = (score - min_score) / (max_score - min_score)
   ```

2. **VILA scores are already [0, 1]**: Since the output is already in [0, 1], normalization becomes:
   ```python
   normalized_score = (score - 0.0) / (1.0 - 0.0) = score
   ```
   The normalized score equals the raw score!

3. **Previous incorrect range**: Would have done:
   ```python
   normalized_score = (score - 0.0) / (10.0 - 0.0) = score / 10.0
   ```
   This would have **under-weighted** VILA scores by 10x!

### Impact on Existing Results

If you have existing JSON files with VILA scores:

**With Incorrect Range (0-10)**:
- Raw score: 0.785
- Normalized (incorrect): 0.785 / 10 = **0.0785**
- Contribution to final score: 0.0785 × 15% = **0.012**

**With Correct Range (0-1)**:
- Raw score: 0.785
- Normalized (correct): 0.785 / 1 = **0.785**
- Contribution to final score: 0.785 × 15% = **0.118**

**Impact**: VILA scores will have ~10x more influence on final weighted scores now!

## Version Update

- **Version**: 2.1.1 → **2.1.2** (pending)
- **Reason**: Score range correction affects weighted scoring calculations
- **Backward Compatibility**: Results with v2.1.1 should be reprocessed

## Corrected Model Registry

| Model | Dataset | Score Range | Normalized Range | Weight | Parameter Name |
|-------|---------|-------------|------------------|--------|----------------|
| KONIQ | KONIQ-10K | 0-100 | 0-1 | 30% | `image_bytes_tensor` |
| SPAQ | SPAQ | 0-100 | 0-1 | 25% | `image_bytes_tensor` |
| PAQ2PIQ | PAQ2PIQ | 0-100 | 0-1 | 20% | `image_bytes_tensor` |
| **VILA** | **AVA** | **0-1** | **0-1** | **15%** | **`image_bytes`** |
| AVA | AVA | 1-10 | 0-1 | 10% | `image_bytes_tensor` |

## Example Score Calculation

### Before Correction (Incorrect)

```python
# Model scores
koniq_raw = 68.45    → normalized = 0.685
spaq_raw = 72.30     → normalized = 0.723
paq2piq_raw = 75.60  → normalized = 0.756
vila_raw = 0.785     → normalized = 0.0785  # ❌ WRONG! Divided by 10
ava_raw = 6.20       → normalized = 0.578

# Weighted score (incorrect)
weighted = (0.685 × 0.30) + (0.723 × 0.25) + (0.756 × 0.20) + (0.0785 × 0.15) + (0.578 × 0.10)
         = 0.2055 + 0.1808 + 0.1512 + 0.0118 + 0.0578
         = 0.607  # VILA barely contributed!
```

### After Correction (Correct)

```python
# Model scores
koniq_raw = 68.45    → normalized = 0.685
spaq_raw = 72.30     → normalized = 0.723
paq2piq_raw = 75.60  → normalized = 0.756
vila_raw = 0.785     → normalized = 0.785  # ✅ CORRECT! Already normalized
ava_raw = 6.20       → normalized = 0.578

# Weighted score (correct)
weighted = (0.685 × 0.30) + (0.723 × 0.25) + (0.756 × 0.20) + (0.785 × 0.15) + (0.578 × 0.10)
         = 0.2055 + 0.1808 + 0.1512 + 0.1178 + 0.0578
         = 0.713  # VILA now properly contributes!
```

**Difference**: Final score increased by **0.106** (10.6% higher)!

## Recommendations

### For New Processing
✅ Use the corrected version - scores are now accurate

### For Existing Results
⚠️ **Reprocess recommended** if you need accurate weighted scores:

```batch
# Reprocess a folder
create_gallery.bat "D:\Photos\YourFolder"
```

This will:
1. Detect version mismatch (v2.1.1 vs v2.1.2)
2. Reprocess images with correct VILA range
3. Generate accurate weighted scores

### For Analysis Scripts
If you're reading old JSON files directly, be aware:
- Old files (v2.1.1): VILA normalized_score = raw_score / 10
- New files (v2.1.2): VILA normalized_score = raw_score

## Testing

Verify the correction works:

```bash
# Run test
wsl bash -c "source ~/.venvs/tf/bin/activate && cd /mnt/d/Projects/image-scoring && python test_vila.py"
```

Expected output:
```
✓ VILA score range: (0.0, 1.0)
```

## References

1. **TensorFlow Hub VILA Model**:
   - https://tfhub.dev/google/vila/image/1
   - Output: predictions in [0, 1]

2. **Kaggle Hub VILA Model**:
   - Model ID: `google/vila/tensorFlow2/image`
   - Same output spec: [0, 1]

3. **VILA Paper (CVPR 2023)**:
   - "VILA: Learning Image Aesthetics from User Comments with Vision-Language Pretraining"
   - Authors: Ke, Junjie et al.
   - Aesthetic scores normalized to [0, 1]

## Summary

✅ **Corrected**: VILA score range from [0, 10] to [0, 1]  
✅ **Impact**: VILA scores now properly contribute to weighted scoring  
✅ **Version**: Will bump to 2.1.2 with this correction  
⚠️ **Action**: Reprocess existing images for accurate scores  

**Root Cause**: Initial assumption about score range was incorrect. The official documentation clearly states [0, 1], which is standard for normalized aesthetic scores in vision-language models.

Thank you for catching this important correction! 🎯

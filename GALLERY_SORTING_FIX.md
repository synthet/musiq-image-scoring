# Gallery Sorting Fix - Filename and Date Issues

## Issues Fixed

### Issue 1: Filename Sorting Not Displaying Files ❌
**Problem**: When sorting by filename, the gallery would not display any files.

**Root Cause**: The sorting comparison logic wasn't handling string values correctly. It was trying to perform numeric operations on filenames.

**Solution**: Added explicit string comparison logic for filename sorting:

```javascript
if (currentSort === 'filename') {
    // String comparison for filename
    const nameA = scoreA || '';
    const nameB = scoreB || '';
    return currentOrder === 'asc' ? 
        nameA.localeCompare(nameB) : 
        nameB.localeCompare(nameA);
}
```

### Issue 2: Date Sorting Showing NaN ❌
**Problem**: When sorting by date, all dates would display as "NaN" (Not a Number).

**Root Cause**: The code was attempting to parse `image_path` as a date:
```javascript
case 'date':
    return new Date(image.image_path || 0).getTime();  // ❌ WRONG
```

This is incorrect because `image_path` is a file path string (e.g., `"D:/Photos/image.jpg"`), not a date string.

**Solution**: Removed date sorting option entirely since:
1. JSON data doesn't contain file modification timestamps
2. Image paths don't contain parseable date information
3. Alternative: Sort by filename (which often contains dates in format like `20250612_037.jpg`)

## Changes Made

### File: `gallery_generator.py`

1. **Removed Date Sorting Option**:
   ```html
   <!-- REMOVED -->
   <option value="date">Date (Newest First)</option>
   ```

2. **Fixed getScore() Function**:
   ```javascript
   case 'date':
       // Use file modification date from stats if available, otherwise return 0
       return 0;  // Disabled - no date info in JSON
   ```

3. **Improved sortImages() Function**:
   ```javascript
   function sortImages() {
       imageData.sort((a, b) => {
           const scoreA = getScore(a, currentSort);
           const scoreB = getScore(b, currentSort);
           
           if (currentSort === 'filename') {
               // String comparison for filename
               const nameA = scoreA || '';
               const nameB = scoreB || '';
               return currentOrder === 'asc' ? 
                   nameA.localeCompare(nameB) : 
                   nameB.localeCompare(nameA);
           }
           
           // Numeric comparison for all other sorts
           const numA = parseFloat(scoreA) || 0;
           const numB = parseFloat(scoreB) || 0;
           
           if (currentOrder === 'asc') {
               return numA - numB;
           } else {
               return numB - numA;
           }
       });
   }
   ```

4. **Updated getScoreLabel()** - Removed date label:
   ```javascript
   const labels = {
       'final_robust_score': 'Robust',
       'weighted_score': 'Weighted',
       'median_score': 'Median',
       'average_normalized_score': 'Average',
       'spaq_score': 'SPAQ',
       'ava_score': 'AVA',
       'koniq_score': 'KONIQ',
       'paq2piq_score': 'PAQ2PIQ',
       'vila_score': 'VILA',
       'filename': 'Name'
       // 'date': 'Date'  // REMOVED
   };
   ```

## Available Sort Options (After Fix)

| Sort Option | Type | Description | Status |
|-------------|------|-------------|--------|
| **Final Robust Score** | Numeric | Combined weighted score | ✅ Working |
| **Weighted Score** | Numeric | Weighted average of all models | ✅ Working |
| **Median Score** | Numeric | Median of normalized scores | ✅ Working |
| **Average Normalized** | Numeric | Simple average of normalized scores | ✅ Working |
| **SPAQ Score** | Numeric | SPAQ model score (0-100) | ✅ Working |
| **AVA Score** | Numeric | AVA model score (1-10) | ✅ Working |
| **KONIQ Score** | Numeric | KONIQ model score (0-100) | ✅ Working |
| **PAQ2PIQ Score** | Numeric | PAQ2PIQ model score (0-100) | ✅ Working |
| **VILA Score** | Numeric | VILA model score (0-1) | ✅ Working |
| **Filename (A-Z)** | String | Alphabetical sort by filename | ✅ **FIXED** |
| ~~Date (Newest First)~~ | ~~Date~~ | ~~Sort by file date~~ | ❌ **REMOVED** |

## Testing

### Test Filename Sorting
1. Open gallery in browser
2. Select "Filename (A-Z)" from sort dropdown
3. Choose "Highest First" or "Lowest First" for order
4. **Expected**: Images sort alphabetically by filename
5. **Result**: ✅ Works correctly

### Verify Other Sorts Still Work
1. Test each numeric sort option (scores)
2. **Expected**: All numeric sorts work as before
3. **Result**: ✅ All working

## Alternative Date Sorting Solutions (Future)

If date sorting is needed in the future, here are options:

### Option 1: Add Timestamp to JSON
Modify `batch_process_images.py` to include file modification time:

```python
import os
from datetime import datetime

# In the image processing function
file_stats = os.stat(image_path)
timestamp = datetime.fromtimestamp(file_stats.st_mtime).isoformat()

# Add to JSON output
results["timestamp"] = timestamp
```

Then in gallery:
```javascript
case 'date':
    return new Date(image.timestamp || 0).getTime();
```

### Option 2: Parse Date from Filename
For filenames with dates (e.g., `20250612_037.jpg`):

```javascript
case 'date':
    const filename = image.image_name || '';
    const dateMatch = filename.match(/^(\d{8})/);  // YYYYMMDD
    if (dateMatch) {
        const dateStr = dateMatch[1];
        const year = dateStr.substr(0, 4);
        const month = dateStr.substr(4, 2);
        const day = dateStr.substr(6, 2);
        return new Date(`${year}-${month}-${day}`).getTime();
    }
    return 0;
```

### Option 3: Use File System API (Browser only)
Would require significant changes and browser permissions.

## Impact

### Before Fix
- ❌ Filename sorting: Broken (no images displayed)
- ❌ Date sorting: Broken (NaN displayed)
- ✅ All numeric sorts: Working

### After Fix
- ✅ Filename sorting: **Working perfectly**
- ➖ Date sorting: **Removed** (wasn't functional)
- ✅ All numeric sorts: Working
- ✅ VILA score: Now properly displayed and sortable

## Documentation Updated

Updated the following documentation:

1. **[README.md](README.md)**:
   - Added WSL setup instructions
   - Added environment comparison table
   - Added gallery features list
   - Mentioned filename sorting works

2. **[GALLERY_SORTING_FIX.md](GALLERY_SORTING_FIX.md)**: This document

## User Impact

### Positive Changes
- ✅ Filename sorting now works correctly
- ✅ No more confusing "NaN" dates
- ✅ Cleaner, more focused sort options
- ✅ All numeric sorts continue to work perfectly
- ✅ VILA scores properly displayed

### What Users Should Know
- **Date sorting removed**: If you need chronological sorting and your filenames contain dates, use filename sort (A-Z)
- **Filename sort fixed**: You can now properly sort images alphabetically
- **10 working sort options**: All remaining sort options work correctly

## Version Update

This fix is included in:
- **Gallery Generator**: Updated
- **Documentation**: Updated
- **Version**: Included with v2.1.2 updates

## Testing Checklist

- [x] Filename sorting works (A-Z)
- [x] Filename sorting works (Z-A)
- [x] All numeric sorts work
- [x] VILA sort works
- [x] No JavaScript errors in console
- [x] Images display correctly
- [x] Modal viewing works
- [x] Statistics update correctly
- [x] Responsive design maintained

## Related Documents

- [GALLERY_GENERATOR_README.md](GALLERY_GENERATOR_README.md) - Gallery documentation
- [GALLERY_VILA_UPDATE.md](GALLERY_VILA_UPDATE.md) - VILA integration in gallery
- [README.md](README.md) - Main project documentation

---

**Fixed**: 2025-10-09  
**Status**: ✅ Resolved  
**Impact**: Improved user experience, removed broken features  

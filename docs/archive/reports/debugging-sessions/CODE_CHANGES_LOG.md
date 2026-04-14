# Code Changes Log - Fullscreen Image Feature

**Feature**: Display full-resolution source images in fullscreen mode  
**Date**: January 2026  
**Status**: Frontend complete, Backend blocked by routing issue

## Summary of Changes

### 1. Gallery Tab - Hidden Path Textbox
**File**: `modules/ui/tabs/gallery.py`  
**Status**: ✅ Complete and Working

**Change**:
```python
# OLD (line ~511):
gallery_selected_path = gr.Textbox(visible=False)

# NEW:
gallery_selected_path = gr.Textbox(
    value="", 
    visible=True,  # CRITICAL: Must be True to render in DOM
    elem_id="gallery-selected-path",
    elem_classes=["hidden-path-storage"],
    container=False,
    interactive=False,
    show_label=False
)
```

**Reason**: Gradio removes `visible=False` components from DOM entirely. JavaScript cannot access them. Setting `visible=True` with CSS hiding keeps it in DOM while invisible to users.

**Output Mapping**: Confirmed in `display_details()` return statement at index 12:
```python
return [
    # ... (indices 0-11)
    file_path,  # Index 12 → gallery_selected_path
    # ... (indices 13-18)
]
```

### 2. CSS - Hide Path Textbox
**File**: `modules/ui/assets.py`  
**Status**: ✅ Complete and Working

**Added** (after line ~65):
```css
/* Hide path storage textbox (visible=True but CSS hidden for DOM access) */
.hidden-path-storage {
    display: none !important;
    visibility: hidden !important;
    position: absolute !important;
    left: -9999px !important;
    width: 0 !important;
    height: 0 !important;
    opacity: 0 !important;
    pointer-events: none !important;
}
```

**Effect**: Textbox renders in DOM (accessible to JavaScript) but completely invisible and non-interactive for users.

### 3. JavaScript - Fullscreen Interception
**File**: `modules/ui/assets.py`  
**Status**: ✅ Complete and Working

**Added Functions**:

#### 3a. Path Validation
```javascript
function isValidPath(path) {
    if (!path || !path.trim()) return false;
    const trimmed = path.trim();
    
    // Reject temp paths
    if (trimmed.includes('/tmp/gradio/')) return false;
    
    // Must look like a file path
    const hasPathSeparator = trimmed.includes('/') || trimmed.includes('\\');
    const hasDriveLetter = /^[a-zA-Z]:/.test(trimmed);
    const hasMntPath = trimmed.startswith('/mnt/');
    const hasFileExtension = /\.[a-zA-Z0-9]{2,4}$/i.test(trimmed);
    
    return (hasPathSeparator || hasDriveLetter || hasMntPath) && 
           hasFileExtension && 
           trimmed.length > 5;
}
```

**Purpose**: Distinguish real file paths from image descriptions that might be in other textboxes.

#### 3b. Path Retrieval
```javascript
function getSelectedImagePath() {
    // Priority 1: Global variable
    if (window.currentSelectedImagePath && isValidPath(window.currentSelectedImagePath)) {
        return window.currentSelectedImagePath;
    }
    
    // Priority 2: Hidden textbox by ID
    const pathTextBox = document.getElementById('gallery-selected-path');
    if (pathTextBox) {
        const input = pathTextBox.querySelector('textarea, input[type="text"]') || pathTextBox;
        const value = input.value || input.textContent || '';
        if (isValidPath(value)) {
            return value.trim();
        }
    }
    
    // Priority 3: Partial ID match
    const partialMatch = document.querySelector('[id*="gallery-selected-path"]');
    // ... (similar logic)
    
    // Priority 4: JSON elements in details panel
    // ... (searches for JSON-formatted data)
    
    return null;
}
```

**Priority Order**:
1. Global variable `window.currentSelectedImagePath`
2. Element with exact ID `gallery-selected-path`
3. Element with partial ID match
4. JSON elements in details panel

#### 3c. Fullscreen Detection
```javascript
function interceptFullscreenButton() {
    document.addEventListener('click', function(e) {
        // Detect fullscreen button click
        const fullscreenBtn = e.target.closest('button[aria-label="Fullscreen"]') ||
                             e.target.closest('button[title="Fullscreen"]') ||
                             e.target.closest('button.icon-button');
        
        if (!fullscreenBtn) return;
        
        // Get image path
        const imgPath = getSelectedImagePath();
        if (!imgPath) {
            console.log('Fullscreen: No image path found');
            return;
        }
        
        console.log('Fullscreen button clicked, path:', imgPath);
        
        // Wait for modal and replace image
        currentPreviewId++;
        const myPreviewId = currentPreviewId;
        
        function waitForFullscreenModal(attemptNum = 0) {
            // Try multiple selectors
            const fullscreenImg = document.querySelector('img[data-testid="detailed-image"]') ||
                                 document.querySelector('.gallery .preview img') ||
                                 document.querySelector('img.preview-image');
            
            if (fullscreenImg && myPreviewId === currentPreviewId) {
                console.log('Fullscreen modal detected, replacing image');
                loadFullResolution(imgPath, myPreviewId, fullscreenImg);
                return true;
            }
            return false;
        }
        
        // Try immediately, then retry with delays
        if (!waitForFullscreenModal(0)) {
            setTimeout(() => waitForFullscreenModal(1), 50);
            setTimeout(() => waitForFullscreenModal(2), 150);
            setTimeout(() => waitForFullscreenModal(3), 300);
            setTimeout(() => waitForFullscreenModal(4), 500);
        }
    }, true);  // Use capture phase
}
```

**Key Selectors**:
- `img[data-testid="detailed-image"]` - Primary selector for fullscreen image
- `.gallery .preview img` - Fallback
- Multiple retry attempts with delays (50ms, 150ms, 300ms, 500ms)

#### 3d. Image Loading
```javascript
function loadFullResolution(imgPath, previewId, imgElement) {
    // Validate preview ID (prevent stale loads)
    if (previewId !== currentPreviewId) return;
    
    // Cancel previous load
    if (abortController) {
        abortController.abort();
    }
    abortController = new AbortController();
    
    // Construct URL
    const url = `/source-image?path=${encodeURIComponent(imgPath)}`;
    
    showLoadingIndicator(imgElement);
    
    // Fetch image
    fetch(url, { signal: abortController.signal })
        .then(response => {
            if (!response.ok) throw new Error('Network response was not ok');
            return response.blob();
        })
        .then(blob => {
            if (previewId !== currentPreviewId) return; // Check again
            
            // Create ObjectURL and replace image
            const objectURL = URL.createObjectURL(blob);
            previousObjectURL = objectURL;
            
            imgElement.onload = () => hideLoadingIndicator(imgElement);
            imgElement.src = objectURL;
            
            abortController = null;
        })
        .catch(err => {
            if (err.name !== 'AbortError') {
                console.error('Full res load error:', err);
            }
            hideLoadingIndicator(imgElement);
        });
}
```

**Features**:
- Abort previous requests when new image selected
- Preview ID validation to prevent stale loads
- ObjectURL creation for blob data
- Loading indicators
- Proper cleanup and error handling

#### 3e. Initialization
```javascript
// Initialize on page load
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => {
        interceptFullscreenButton();
    });
} else {
    interceptFullscreenButton();
}
```

### 4. Backend - FastAPI Endpoint
**File**: `modules/ui/app.py`  
**Status**: ❌ Blocked - Returns 404 (See GRADIO_ROUTING_ISSUE.md)

**Added Function**:
```python
def setup_server_endpoints(demo):
    """Configures FastAPI endpoints for the Gradio app."""
    fastapi_app = demo.app
    
    @fastapi_app.get("/source-image")
    async def source_image_endpoint(path: str):
        import urllib.parse
        from fastapi.responses import Response, FileResponse
        from fastapi import HTTPException
        import io
        
        # 1. URL decode
        file_path = urllib.parse.unquote(path)
        
        # 2. Path conversion (WSL → Windows)
        original_path = file_path
        resolved = utils.resolve_file_path(file_path)
        if resolved:
            file_path = resolved
        else:
            file_path = utils.convert_path_to_local(file_path)
        
        # 3. Validate file exists
        if not os.path.exists(file_path):
            raise HTTPException(status_code=404, detail="File not found")
        
        # 4. Determine file type
        ext = Path(file_path).suffix.lower()
        is_raw = ext in ['.nef', '.cr2', '.dng', '.arw', '.orf', 
                        '.nrw', '.cr3', '.rw2']
        
        if is_raw:
            # Extract embedded JPEG (fast)
            img = thumbnails.extract_embedded_jpeg(file_path, min_size=1000)
            
            if img and img.width > 1000:
                jpeg_bytes = io.BytesIO()
                img.save(jpeg_bytes, format='JPEG', quality=95)
                jpeg_bytes.seek(0)
                return Response(
                    content=jpeg_bytes.read(),
                    media_type="image/jpeg",
                    headers={"Cache-Control": "public, max-age=3600"}
                )
            
            # Fallback: Full RAW decode (slower)
            preview_path = thumbnails.generate_preview(file_path)
            if preview_path and os.path.exists(preview_path):
                return FileResponse(
                    preview_path,
                    media_type="image/jpeg",
                    headers={"Cache-Control": "public, max-age=3600"}
                )
            
            # Last resort: smaller embedded JPEG
            if img:
                jpeg_bytes = io.BytesIO()
                img.save(jpeg_bytes, format='JPEG', quality=95)
                jpeg_bytes.seek(0)
                return Response(content=jpeg_bytes.read(), media_type="image/jpeg")
            
            raise HTTPException(status_code=500, detail="Failed to generate RAW preview")
        else:
            # Regular image: serve directly
            media_types = {
                '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg',
                '.png': 'image/png', '.gif': 'image/gif',
                '.webp': 'image/webp', '.bmp': 'image/bmp',
                '.tiff': 'image/tiff', '.tif': 'image/tiff'
            }
            media_type = media_types.get(ext, 'image/jpeg')
            
            return FileResponse(
                file_path,
                media_type=media_type,
                headers={"Cache-Control": "public, max-age=3600"}
            )
```

**Path Conversion Logic**:
1. `utils.resolve_file_path()`: Checks database resolved_paths table
2. `utils.convert_path_to_local()`: Converts `/mnt/d/` to `D:\`

**RAW Processing Strategy**:
1. Try embedded JPEG extraction (fast, ~2MB for D90 NEFs)
2. If too small, do full RAW decode (slow, ~20MB full resolution)
3. If all fails, return smaller embedded JPEG
4. Cache with 1-hour max-age header

### 5. Webui - Endpoint Registration
**File**: `webui.py`  
**Status**: ❌ Blocked - Routes registered but return 404

**Changed**:
```python
# OLD:
demo, runner, tagging_runner = app.create_ui()
app.setup_server_endpoints(demo)  # Before queue()
demo.queue().launch(...)

# NEW:
demo, runner, tagging_runner = app.create_ui()
demo.queue()  # Initialize FastAPI app first
app.setup_server_endpoints(demo)  # Then register endpoints
demo.launch(...)
```

**Reason**: Ensure FastAPI app is fully initialized before registering custom routes.

**Result**: Routes appear in list but still return 404 (Gradio routing issue).

## Testing Evidence

### Frontend Logs (Working ✅)
```json
{"location":"assets.py:getSelectedImagePath","message":"Found path in gallery-selected-path textbox","data":{"filePath":"/mnt/d/Photos/D90/2014/20140614_0410.NEF"}}
{"location":"assets.py:waitForFullscreenModal","message":"Modal search result","data":{"foundImage":true,"matchedSelector":"img[data-testid=\"detailed-image\"]"}}
{"location":"assets.py:loadFullResolution","message":"Starting fetch","data":{"url":"/source-image?path=%2Fmnt%2Fd%2FPhotos%2FD90%2F2014%2F20140614_0410.NEF"}}
```

### Backend Logs (Not Working ❌)
```
[DEBUG] FastAPI app routes after: 79
[DEBUG] All registered routes:
  {'GET'} /source-image  ← Route registered
```

But when accessed:
```
GET /source-image?path=...
Response: 404 {"detail":"Not Found"}
(No terminal output - function never called)
```

## Debug Artifacts Cleanup ✅

**Date**: January 17, 2026  
**Status**: Complete

All debug instrumentation has been removed from the codebase:

### Cleaned Files:
1. **`modules/ui/app.py`**:
   - Removed all `# #region agent log` blocks
   - Removed test endpoint (`/test-endpoint`)
   - Removed debug print statements
   - Removed commented-out DEBUG code

2. **`modules/ui/assets.py`**:
   - Removed 24 JavaScript agent log regions (fetch calls to logging endpoint)
   - Cleaned up all HTTP logging instrumentation
   - Kept functional code intact

3. **`webui.py`**:
   - No artifacts (debug prints were legitimate startup messages)

4. **`.cursor/debug.log`**:
   - Deleted (16 KB of NDJSON logs)

### Verification:
```bash
grep -i "agent log" modules/ui/*.py    # 0 results
grep -i "7242/ingest" modules/ui/*.py  # 0 results
grep -i "test-endpoint" modules/ui/*.py # 0 results
```

**Production-ready**: All code now clean with no debug overhead.

## Rollback Instructions

If changes need to be reverted:

1. **Revert `gallery.py`**:
   ```python
   gallery_selected_path = gr.Textbox(visible=False)
   ```

2. **Remove CSS** from `assets.py`:
   - Delete `.hidden-path-storage` CSS block

3. **Remove JavaScript** from `assets.py`:
   - Delete all functions added to `tree_js` variable
   - Remove initialization code

4. **Remove endpoint** from `app.py`:
   - Delete `setup_server_endpoints()` or comment out endpoint

5. **Revert `webui.py`**:
   - Move `setup_server_endpoints()` call back or remove

## Next Steps for Completion

1. **Solve Gradio routing issue** (See GRADIO_ROUTING_ISSUE.md)
2. **Verify backend path conversion** with real requests
3. **Test RAW image extraction** performance
4. **Remove debug instrumentation** from all files
5. **Add user documentation** for the feature
6. **Performance optimization** if needed

## Files Modified

1. `modules/ui/tabs/gallery.py` - Textbox visibility
2. `modules/ui/assets.py` - CSS + JavaScript (~500 lines)
3. `modules/ui/app.py` - FastAPI endpoint (~150 lines)
4. `webui.py` - Endpoint setup timing (3 lines)

**Total Lines Added**: ~650 lines  
**Total Lines Modified**: ~5 lines  
**New Dependencies**: None (uses existing utilities)

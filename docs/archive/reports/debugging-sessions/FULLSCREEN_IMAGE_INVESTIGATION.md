# Fullscreen Image Display Investigation

**Date**: January 2026  
**Status**: RESOLVED âœ…  
**Resolution**: See GRADIO_ROUTING_RESOLUTION.md

## Problem Statement

When clicking the fullscreen button in the Gallery tab, the system displays a tiny internal Gradio thumbnail instead of the actual source image. The goal is to:

1. Display the full-resolution source image (RAW or regular)
2. Handle WSLâ†”Windows path conversion correctly
3. Process RAW files on-the-fly (extract embedded JPEG or decode)
4. Serve regular images directly from their source location

## Architecture

### Components

```
â”Œâ”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”
â”‚                    Frontend (JavaScript)                     â”‚
â”‚  - Intercept fullscreen button click                        â”‚
â”‚  - Read DB path from hidden textbox                         â”‚
â”‚  - Fetch full-res image from backend endpoint               â”‚
â”‚  - Replace modal image src with ObjectURL                   â”‚
â””â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”˜
                              â”‚
                              â”‚ HTTP GET /source-image?path=...
                              â–¼
â”Œâ”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”
â”‚                   Backend (FastAPI Endpoint)                 â”‚
â”‚  - Receive WSL path (/mnt/d/Photos/...)                    â”‚
â”‚  - Convert to Windows path (D:\Photos\...)                  â”‚
â”‚  - Check if RAW or regular image                            â”‚
â”‚  - Extract JPEG from RAW or serve file directly             â”‚
â”‚  - Return as HTTP response                                   â”‚
â””â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”˜
```

### File Structure

- **`modules/ui/tabs/gallery.py`**: Gallery UI with hidden path textbox
- **`modules/ui/assets.py`**: JavaScript for fullscreen interception
- **`modules/ui/app.py`**: FastAPI endpoint registration
- **`webui.py`**: Application launcher and endpoint setup

## Investigation Timeline

### Phase 1: Path Retrieval (SOLVED âœ…)

**Issue**: JavaScript couldn't find the database file path

**Root Cause**: Gradio removes `visible=False` components from DOM entirely

**Solution**:
```python
gallery_selected_path = gr.Textbox(
    value="", 
    visible=True,  # Must be True to render in DOM
    elem_id="gallery-selected-path",
    elem_classes=["hidden-path-storage"],
    container=False,
    interactive=False,
    show_label=False
)
```

With CSS:
```css
.hidden-path-storage {
    display: none !important;
    visibility: hidden !important;
    position: absolute !important;
    left: -9999px !important;
    opacity: 0 !important;
    pointer-events: none !important;
}
```

**Evidence**:
```json
{"location":"assets.py:getSelectedImagePath","message":"Found path in gallery-selected-path textbox","data":{"filePath":"/mnt/d/Photos/D90/2014/20140614_0410.NEF"}}
```

### Phase 2: Frontend Implementation (COMPLETED âœ…)

**Implementation**:
1. Global variable `window.currentSelectedImagePath` to store path
2. `handlePreviewChange()` updates path when preview opens
3. `getSelectedImagePath()` reads path with robust validation
4. `interceptFullscreenButton()` detects button clicks
5. `waitForFullscreenModal()` finds modal image element
6. `loadFullResolution()` fetches and replaces image

**Key Functions**:
- **`isValidPath(path)`**: Validates file paths vs descriptions
  - Checks for path separators (`/`, `\`)
  - Checks for drive letters (`C:`, etc.)
  - Checks for `/mnt/` prefix
  - Checks for file extensions
  - Rejects `/tmp/gradio/` paths

- **Modal Detection**: `img[data-testid="detailed-image"]`

- **API Call**: 
  ```javascript
  fetch(`/source-image?path=${encodeURIComponent(imgPath)}`)
  ```

**Evidence - Complete Frontend Flow**:
```json
{"location":"assets.py:handleFullscreenClick","message":"Fullscreen button clicked"}
{"location":"assets.py:getSelectedImagePath","message":"Found path","data":{"filePath":"/mnt/d/Photos/D90/2014/20140614_0410.NEF"}}
{"location":"assets.py:waitForFullscreenModal","message":"Modal search result","data":{"foundImage":true,"matchedSelector":"img[data-testid=\"detailed-image\"]"}}
{"location":"assets.py:loadFullResolution","message":"Starting fetch","data":{"url":"/source-image?path=%2Fmnt%2Fd%2FPhotos%2FD90%2F2014%2F20140614_0410.NEF"}}
{"location":"assets.py:loadFullResolution","message":"Fetch response received","data":{"ok":false,"status":404}}
```

### Phase 3: Backend Endpoint Registration (BLOCKED âŒ)

**Problem**: Endpoint returns 404 despite being registered

**Attempts**:

1. **Initial Registration** (Failed):
   ```python
   @demo.app.get("/api/source-image")
   async def source_image_endpoint(path: str):
   ```
   - Hypothesis: Gradio reserves `/api/*` routes

2. **Changed Path** (Failed):
   ```python
   @demo.app.get("/source-image")
   ```
   - Hypothesis: Avoid Gradio route conflicts

3. **Moved Registration Timing** (Failed):
   ```python
   demo.queue()  # Call first
   setup_server_endpoints(demo)  # Then register
   demo.launch()
   ```
   - Hypothesis: FastAPI app needs to be initialized

4. **Test Endpoint** (Failed):
   ```python
   @fastapi_app.get("/test-endpoint")
   async def test_endpoint():
       return JSONResponse({"status": "ok"})
   ```
   - Result: Also returns 404
   - Confirms: General routing problem, not specific to our endpoint

**Evidence - Routes ARE Registered**:
```
[DEBUG] FastAPI app type: <class 'gradio.routes.App'>
[DEBUG] FastAPI app routes before: 76
[DEBUG] FastAPI app routes after: 79
[DEBUG] All registered routes:
  ...
  {'GET'} /test-endpoint
  {'GET'} /manifest.json
  {'GET'} /api/raw-preview
  {'GET'} /source-image
```

**Evidence - Routes Never Called**:
- HTTP requests return `{"detail":"Not Found"}`
- NO terminal output from print statements inside endpoint functions
- NO debug.log entries from endpoint logging
- Endpoints registered but functions never execute

**Hypothesis**: Gradio's routing layer intercepts ALL requests before they reach registered FastAPI routes

## Technical Implementation

### Backend Endpoint Design

```python
@fastapi_app.get("/source-image")
async def source_image_endpoint(path: str):
    # 1. URL decode
    file_path = urllib.parse.unquote(path)
    
    # 2. Path conversion (WSL â†’ Windows)
    resolved = utils.resolve_file_path(file_path)
    if not resolved:
        resolved = utils.convert_path_to_local(file_path)
    
    # 3. Validate file exists
    if not os.path.exists(resolved):
        raise HTTPException(status_code=404, detail="File not found")
    
    # 4. Process based on file type
    ext = Path(resolved).suffix.lower()
    is_raw = ext in ['.nef', '.cr2', '.dng', '.arw', '.orf', '.nrw', '.cr3', '.rw2']
    
    if is_raw:
        # Extract embedded JPEG (fast)
        img = thumbnails.extract_embedded_jpeg(resolved, min_size=1000)
        
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
        preview_path = thumbnails.generate_preview(resolved)
        if preview_path:
            return FileResponse(preview_path, media_type="image/jpeg")
    else:
        # Regular image: serve directly
        return FileResponse(resolved, media_type="image/jpeg")
```

### Path Conversion Logic

**WSL to Windows**:
- `/mnt/d/Photos/image.NEF` â†’ `D:\Photos\image.NEF`
- Uses `utils.resolve_file_path()` or `utils.convert_path_to_local()`

**Database Resolution**:
- Some paths may be stored as relative paths
- `resolve_file_path()` checks resolved_paths table first
- Falls back to conversion if resolution fails

## Current Status

### âœ… Working:
- Frontend path retrieval from database
- Frontend fullscreen button detection
- Frontend modal image element detection  
- Frontend HTTP request construction
- Backend endpoint registration (routes visible in list)
- Path conversion utilities
- RAW image processing utilities

### âœ… Resolved:
- **Backend endpoint routing**: Solved using `gr.mount_gradio_app()` pattern
- **Full implementation**: Frontend + backend working end-to-end
- **RAW processing**: Embedded JPEG extraction working
- **Path conversion**: WSLâ†”Windows conversion working

### ðŸŽ‰ Final Status:
**Feature fully functional** - Fullscreen button now displays full-resolution source images with proper RAW processing and path conversion.

## Environment

- **OS**: Windows 10 + WSL (Linux)
- **Python**: 3.12
- **Gradio**: Latest (2026 version)
- **Server**: `http://127.0.0.1:7860`
- **Codebase**: WSL path `/path/to/image-scoring`

## Next Steps

1. **Verify endpoint execution**: Check terminal for debug prints when accessing endpoints
2. **Research Gradio routing**: Investigate Gradio documentation for custom route registration
3. **Alternative approaches**:
   - Register routes before `Blocks` creation
   - Use Gradio's built-in file serving mechanisms
   - Mount FastAPI routes at app startup, not in `setup_server_endpoints()`
   - Use `demo.app.mount()` instead of decorators

## References

- [Gradio Blocks Documentation](https://www.gradio.app/docs/blocks)
- [FastAPI Routing](https://fastapi.tiangolo.com/tutorial/first-steps/)
- Related files:
  - `docs/technical/GRADIO_INTEGRATION.md` (if exists)
  - `docs/technical/PATH_RESOLUTION.md` (if exists)

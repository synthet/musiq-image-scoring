# Debugging Session Log - Fullscreen Image Feature

**Date**: January 17, 2026  
**Session Duration**: ~3 hours  
**AI Agent**: Claude (Cursor IDE Debug Mode)

## Session Timeline

### 00:00 - Initial Request
**User**: "When fullscreen button in Gallery is pressed, display not an internal tiny thumbnail but a real source picture (follow by the reference in DB and resolve WSL<->Windows path conversion.) Use either native windows thumbnail or some on-the-fly RAW to jpeg processing"

**Analysis**:
- Need to intercept fullscreen button click
- Retrieve database path from Gradio state
- Convert WSL paths to Windows paths
- Serve full-resolution RAW or regular images
- Display in fullscreen modal instead of thumbnail

### 00:15 - Phase 1: Path Retrieval Issue

**Problem**: "Fullscreen: No image path found"

**Hypothesis A**: Path stored in `gr.State` not accessible from JavaScript  
**Hypothesis B**: Path in different location than expected  
**Hypothesis C**: Timing issue - fullscreen clicked before details update  
**Hypothesis D**: Path in gallery image data attributes  

**Investigation**:
- Added instrumentation to `getSelectedImagePath()` function
- Logged all textboxes found in details panel
- Found: Only image descriptions, no file paths

**Root Cause Discovered**: `gallery_selected_path = gr.Textbox(visible=False)`
- Gradio removes `visible=False` components from DOM entirely
- JavaScript cannot access them via `getElementById` or any selector
- Component exists in Python but not in HTML

**Solution**: Changed to `visible=True` with CSS hiding
```python
gallery_selected_path = gr.Textbox(
    visible=True,  # Renders in DOM
    elem_classes=["hidden-path-storage"]  # CSS hides it
)
```

**Evidence**: Logs showed textbox found with correct path after fix
```json
{"data":{"foundById":true,"value":"/mnt/d/Photos/D90/2014/20140614_0410.NEF"}}
```

**Time to Resolution**: ~45 minutes

### 01:00 - Phase 2: Path Validation Issue

**Problem**: Getting image descriptions instead of file paths

**Investigation**:
- Logs showed: `{"path":"The front of a church with a clock on it"}`
- JavaScript was reading from description textbox instead of path textbox

**Root Cause**: Weak `isValidPath()` validation
- Only checked for length and absence of `/tmp/gradio/`
- Didn't validate actual path characteristics

**Solution**: Enhanced validation
```javascript
function isValidPath(path) {
    // Check for path separators
    const hasPathSeparator = path.includes('/') || path.includes('\\');
    // Check for drive letters
    const hasDriveLetter = /^[a-zA-Z]:/.test(path);
    // Check for /mnt/ prefix
    const hasMntPath = path.startsWith('/mnt/');
    // Check for file extension
    const hasFileExtension = /\.[a-zA-Z0-9]{2,4}$/i.test(path);
    
    return (hasPathSeparator || hasDriveLetter || hasMntPath) && hasFileExtension;
}
```

**Evidence**: After fix, logs showed valid paths only
```json
{"data":{"filePath":"/mnt/d/Photos/D90/2014/20140614_0410.NEF","isValid":true}}
```

**Time to Resolution**: ~20 minutes

### 01:20 - Phase 3: Modal Detection

**Problem**: Finding the fullscreen modal image element

**Attempts**:
1. `.gallery .preview img` - Not specific enough
2. `img.preview-image` - Class doesn't exist
3. `.modal img` - Too generic

**Solution**: `img[data-testid="detailed-image"]`
- Gradio uses `data-testid` attributes
- Most reliable selector for the fullscreen image

**Added**: Retry mechanism with delays (50ms, 150ms, 300ms, 500ms)
- Modal may not be in DOM immediately after button click
- Multiple attempts ensure we find it

**Time to Resolution**: ~15 minutes

### 01:35 - Phase 4: Frontend Complete, Backend Testing

**Status**: Frontend successfully:
- Retrieves correct path from database
- Detects fullscreen button click
- Finds modal image element
- Constructs HTTP request to `/api/source-image`

**New Problem**: Backend endpoint returns 404

**Console Error**:
```
GET http://127.0.0.1:7860/api/source-image?path=%2Fmnt%2Fd%2FPhotos... 404 (Not Found)
Full res load error: Error: Network response was not ok
```

**Note**: NO backend logs written to `debug.log` - endpoint never called

### 01:45 - Phase 5: Backend Endpoint Registration

**Hypothesis E**: Endpoint not registered correctly

**Investigation**:
1. Verified `setup_server_endpoints(demo)` is called
2. Verified `demo.app` exists and has `.get()` method
3. Added route counting and listing

**Results**:
```
[DEBUG] demo.app type: <class 'gradio.routes.App'>
[DEBUG] demo.app has .get: True
[DEBUG] FastAPI app routes before: 76
[DEBUG] FastAPI app routes after: 79  â† Routes added!
```

**Hypothesis E**: REJECTED - Endpoints ARE registered

### 02:00 - Phase 6: Route Path Conflicts

**Hypothesis F**: `/api/*` prefix conflicts with Gradio internal routes

**Test**: Changed endpoint from `/api/source-image` to `/source-image`

**Result**: Still 404

**Hypothesis F**: REJECTED - Path doesn't matter

### 02:15 - Phase 7: Registration Timing

**Hypothesis G**: Endpoints registered too early, before FastAPI app ready

**Test**: Moved registration to AFTER `.queue()` call
```python
demo.queue()  # Initialize FastAPI first
setup_server_endpoints(demo)  # Then register
demo.launch()
```

**Result**: Routes appear in list, still 404

**Hypothesis G**: REJECTED - Timing doesn't matter

### 02:30 - Phase 8: Test Endpoint

**Hypothesis H**: Something wrong with `/source-image` endpoint logic

**Test**: Created minimal test endpoint
```python
@fastapi_app.get("/test-endpoint")
async def test_endpoint():
    return JSONResponse({"status": "ok"})
```

**Result**: Also returns 404

**Hypothesis H**: REJECTED - Not specific to our endpoint

### 02:45 - Phase 9: Route Execution Verification

**Current Investigation**: Are endpoint functions ever called?

**Added**: Print statements at start of endpoint functions
```python
@fastapi_app.get("/test-endpoint")
async def test_endpoint():
    print("[DEBUG] TEST ENDPOINT FUNCTION CALLED!")
    ...

@fastapi_app.get("/source-image")
async def source_image_endpoint(path: str):
    print(f"[DEBUG] SOURCE IMAGE ENDPOINT CALLED! path={path}")
    ...
```

**Terminal Output During Request**:
```
(No debug prints appear)
```

**Conclusion**: **Functions are NEVER called despite routes being registered**

**Current Hypothesis â­**: Gradio routing middleware intercepts ALL requests before FastAPI processes them, even though routes are technically registered in FastAPI app.

**Status**: BLOCKED - Need to investigate Gradio routing internals

## Instrumentation Summary

### Frontend (JavaScript)
**Location**: `modules/ui/assets.py` - `tree_js` variable

**Added Logs**:
- `handleFullscreenClick`: Button click detection
- `getSelectedImagePath`: Path retrieval from textbox
- `waitForFullscreenModal`: Modal detection
- `loadFullResolution`: Fetch initiation and response

**Log Format**: NDJSON to `.cursor/debug.log` via `fetch()` to HTTP endpoint
```javascript
fetch('http://127.0.0.1:7242/ingest/...', {
    method: 'POST',
    body: JSON.stringify({
        location: 'assets.py:functionName',
        message: 'Description',
        data: {...},
        timestamp: Date.now(),
        sessionId: 'debug-session',
        hypothesisId: 'A'
    })
})
```

### Backend (Python)
**Location**: `modules/ui/app.py` - endpoint functions

**Added Logs**:
- File writes to `/path/to/image-scoring\.cursor\debug.log`
- Console prints with `[DEBUG]` prefix
- Exception logging with error details

**Current Status**: No logs generated - functions never execute

## Key Learnings

### 1. Gradio DOM Rendering
`visible=False` removes components from DOM entirely. For JavaScript access:
- Use `visible=True` with CSS hiding
- Or use `gr.State` for Python-only data (but not accessible from JS)

### 2. Path Validation
Client-side validation must be very strict to avoid false positives:
- Check for actual path characteristics (separators, extensions)
- Don't rely on simple length or substring checks

### 3. Gradio Routing Architecture
`gradio.routes.App` is a custom FastAPI subclass that may:
- Intercept requests before FastAPI routing
- Have middleware that returns 404 for unknown paths
- Require special API for custom route registration

### 4. Debugging Strategy
Use runtime evidence over code inspection:
- Add print statements at function entry
- Log to files AND console
- Verify assumptions with counts and lists
- Test with minimal examples to isolate issues

## Tools Used

- **Cursor IDE Debug Mode**: Systematic hypothesis-driven debugging
- **Browser DevTools**: Console logs, Network tab, DOM inspection
- **NDJSON Logging**: Structured logs for analysis
- **FastAPI Route Introspection**: List all registered routes
- **Terminal Output**: Real-time execution verification

## Current Blocker

**Issue**: Gradio custom route registration broken or changed

**Impact**: Cannot implement backend endpoint, feature blocked

**Workarounds Being Considered**:
1. Use Gradio's built-in file serving (limited functionality)
2. Mount separate FastAPI app
3. Run separate image server on different port
4. Investigate Gradio source code for proper API

## Next Session Planning

1. **Research Gradio documentation** for custom routes in version 6.0+
2. **Examine `gradio.routes.App` source code** on GitHub
3. **Search Gradio issues** for similar problems
4. **Test workaround options** (separate server, mount app)
5. **Consider opening Gradio issue** if bug confirmed

## Files for Review

- `.cursor/debug.log` - Frontend execution logs
- `docs/reports/debugging-sessions/FULLSCREEN_IMAGE_INVESTIGATION.md` - Investigation summary
- `docs/reports/debugging-sessions/GRADIO_ROUTING_ISSUE.md` - Routing problem details
- `docs/reports/debugging-sessions/CODE_CHANGES_LOG.md` - All code modifications

# Gradio Custom FastAPI Route Registration Issue

**Issue**: Custom FastAPI routes registered via `@demo.app.get()` appear in routes list but return 404  
**Date**: January 2026  
**Severity**: Critical - Blocking fullscreen image feature

## Problem Description

When registering custom FastAPI routes on a Gradio `Blocks` app, the routes appear in the FastAPI app's route list but return `{"detail":"Not Found"}` when accessed. Endpoint functions are never called.

## Reproduction Steps

1. Create Gradio Blocks app
2. Call `.queue()` on the app
3. Register custom route using `@demo.app.get()`
4. Call `.launch()`
5. Access the custom route
6. **Result**: 404 response, function never called

## Code Example

```python
import gradio as gr
from fastapi.responses import JSONResponse

# Create Gradio app
with gr.Blocks() as demo:
    gr.Markdown("# Test App")

# Queue (initializes FastAPI app)
demo.queue()

# Register custom route
@demo.app.get("/test-endpoint")
async def test_endpoint():
    print("ENDPOINT CALLED")  # Never prints
    return JSONResponse({"status": "ok"})

# Launch
demo.launch()
```

## Observed Behavior

**Terminal Output**:
```
[DEBUG] FastAPI app routes after: 79
[DEBUG] All registered routes:
  {'GET'} /test-endpoint  ← Route IS registered
  ...
```

**HTTP Request**:
```
GET http://127.0.0.1:7860/test-endpoint
Response: 404 {"detail":"Not Found"}
```

**Terminal During Request**:
```
(No output - function never called)
```

## Evidence

### 1. Route Registration Confirmed
```python
print(f"Routes: {len(demo.app.routes)}")  # Shows route count increased
for route in demo.app.routes:
    if hasattr(route, 'path'):
        print(f"  {route.methods} {route.path}")
# Output includes: {'GET'} /test-endpoint
```

### 2. Function Never Executes
```python
@demo.app.get("/test-endpoint")
async def test_endpoint():
    print("[DEBUG] FUNCTION CALLED")  # Never prints
    # Log file never written
    # Response never returned
```

### 3. Consistent Across All Custom Routes
- `/test-endpoint`: 404
- `/source-image`: 404
- `/custom-api/anything`: 404
- Even `/manifest.json` override: 404

### 4. Built-in Gradio Routes Work
- `/`: Works
- `/config`: Works
- `/gradio_api/*`: Works

## Hypotheses

### H1: Gradio Routing Middleware Intercepts All Requests ⭐ (Most Likely)
Gradio may have a catch-all middleware that processes requests before FastAPI routing, returning 404 for unrecognized paths.

**Evidence**:
- Routes registered but never called
- Gradio routes work, custom routes don't
- No errors during registration

### H2: Route Registration Timing Issue
Custom routes need to be registered at a different point in the lifecycle.

**Tested**:
- ❌ Before `.queue()`
- ❌ After `.queue()`, before `.launch()`
- ❌ After `.launch()` (can't register after)

### H3: Gradio Version-Specific API Change
Recent Gradio versions may have changed how custom routes should be registered.

**Evidence**:
- Old tutorials show `@demo.app.get()` working
- Current version (2026) may have different API

### H4: Route Priority / Ordering Issue
Gradio's catch-all routes take precedence over custom routes.

**Counter-evidence**:
- Custom routes added AFTER Gradio routes
- Should have higher priority in FastAPI

## Attempted Solutions

### ❌ Solution 1: Change Registration Timing
```python
demo.queue()
setup_server_endpoints(demo)  # Register here
demo.launch()
```
**Result**: Still 404

### ❌ Solution 2: Avoid Path Conflicts
Changed from `/api/source-image` to `/source-image` to avoid `/api/*` prefix.
**Result**: Still 404

### ❌ Solution 3: Use FastAPI App Directly
```python
fastapi_app = demo.app
@fastapi_app.get("/test-endpoint")
```
**Result**: Still 404 (same as `@demo.app.get()`)

### ❌ Solution 4: Test Endpoint
Created minimal endpoint with no dependencies to rule out endpoint logic issues.
**Result**: Still 404

## Gradio App Structure

```python
type(demo)              # <class 'gradio.blocks.Blocks'>
type(demo.app)          # <class 'gradio.routes.App'>
hasattr(demo.app, 'get')  # True
```

The `gradio.routes.App` class is a custom FastAPI subclass, which may override routing behavior.

## Workaround Ideas

### Option 1: Use Gradio's File Serving
Instead of custom endpoint, use Gradio's built-in file serving via `allowed_paths`:
```python
demo.launch(allowed_paths=["D:/Photos/"])
# Access via: /gradio_api/file=D:/Photos/image.jpg
```

**Pros**: Uses Gradio's working routes  
**Cons**: Doesn't solve RAW processing, path conversion needed client-side

### Option 2: Mount Separate FastAPI App
```python
from fastapi import FastAPI

custom_app = FastAPI()

@custom_app.get("/source-image")
async def source_image_endpoint(path: str):
    ...

demo.app.mount("/custom", custom_app)
demo.launch()
# Access via: /custom/source-image
```

**Status**: Untested

### Option 3: Override Gradio Middleware
Patch or wrap Gradio's routing middleware to allow custom routes.

**Status**: Requires deep dive into Gradio internals

### Option 4: Separate Server
Run separate FastAPI server on different port for image serving.

**Pros**: Guaranteed to work  
**Cons**: Added complexity, CORS issues, separate process

## Investigation Needed

1. **Examine `gradio.routes.App` source code**
   - Look for middleware that intercepts requests
   - Check if there's a whitelist of allowed paths
   - Find proper API for custom routes

2. **Check Gradio GitHub Issues**
   - Search for "custom routes", "FastAPI endpoints"
   - Look for similar problems reported

3. **Test with Minimal Example**
   - Create minimal repro case
   - Test with different Gradio versions
   - Isolate the exact breaking change

4. **Read Gradio 6.0+ Documentation**
   - API may have changed for custom routes
   - Look for migration guides

## Related Files

- `modules/ui/app.py`: `setup_server_endpoints()` function
- `webui.py`: Endpoint setup and launch sequence
- `docs/reports/debugging-sessions/FULLSCREEN_IMAGE_INVESTIGATION.md`: Parent investigation

## References

- Gradio Blocks: https://www.gradio.app/docs/blocks
- FastAPI Routing: https://fastapi.tiangolo.com/
- Gradio GitHub: https://github.com/gradio-app/gradio

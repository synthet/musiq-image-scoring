# Gradio Routing Issue Resolution

**Date**: January 17, 2026
**Status**: Resolved
**Related Issues**: Fullscreen Image Loading Failed (404)

## Problem Summary
The application failed to load full-resolution images in fullscreen mode. The browser console reported `404 Not Found` errors for the `/source-image` endpoint.
Investigation revealed that custom FastAPI routes defined on the Gradio `demo.app` were not being correctly registered or were unreachable when using the standard `demo.launch()` method in recent Gradio versions.

## Root Cause
- **Issue**: `demo.app` (the underlying FastAPI app of a Gradio Blocks instance) does not consistently support manual route addition after creation when using `demo.launch()`. The internal routing table was updated in memory, but requests were not routing to these handlers in the running server.
- **Impact**: Custom endpoints required for serving images bypassing Gradio's processing (critical for performance and RAW file handling) were inaccessible.

## Solution Implemented
The application entry point was refactored to use `gr.mount_gradio_app`, which is the official pattern for combining FastAPI and Gradio.

### Key Changes
1.  **Refactored `webui.py`**:
    - Removed `demo.launch()`.
    - Explicitly initializes a root `FastAPI()` application.
    - Calls `app_module.setup_server_endpoints(app)` to register custom routes *directly* on this root app.
    - Mounts the Gradio interface using `gr.mount_gradio_app(app, demo, path="/")`.
    - Starts the server using `uvicorn.run()`.

2.  **Updated `modules/ui/app.py`**:
    - Modified `setup_server_endpoints` to accept the `fastapi_app` explicitly, removing the previous logic that tried to extract it from `demo`.

3.  **Cleaned Up Debugging**:
    - Removed temporary debug prints and test endpoints used during the investigation.

## Verification
- **Manual Test**: Run `python launch.py`.
- **Endpoint Check**: `/test-endpoint` (if enabled) or `/source-image` (via UI) responds correctly.
- **Functional Check**: Fullscreen mode in the Gallery now loads high-resolution images/previews successfully without 404 errors.

## Conclusion
The mounting strategy provides a robust foundation for hybrid Gradio/FastAPI applications. This structure also facilitates future API expansions (e.g., external healthy checks, metrics) without conflicting with Gradio's internal routing.

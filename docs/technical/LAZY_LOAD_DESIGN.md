# Design & Code Review: Lazy Load Full Resolution Images

## Overview
This document details the implementation of the "Lazy Load Full Resolution" feature for the Vexlum Scoring Scoring WebUI. The goal was to improve performance and user experience by displaying thumbnails during rapid navigation and only loading full-resolution images when the user settles on an image.

## Feature Specification
1.  **Lazy Loading**: Open full-resolution image only after a delay (debounce).
2.  **Performance**: Keep using lightweight thumbnails for the gallery grid and initial preview.
3.  **Cancellation**: Abort pending network requests if the user navigates away before the image loads.
4.  **Feedback**: Show a subtle "Loading..." indicator during the fetch.

## Implementation Details

### Core Logic (JavaScript)
The feature is implemented entirely in client-side JavaScript, injected via `webui.py`.

*   **File**: `webui.py`
*   **Location**: JavaScript block ~line 2122 (injected before closing `</script>`)
*   **Function**: `initLazyFullResolution()`

### Key Design Decisions

#### 1. Debouncing (600ms Delay)
**Why?** Browsing through a gallery often involves pressing arrow keys rapidly. Loading a 20MB+ RAW file or even a 5MB JPEG for every intermediate image would saturate the network and lag the UI.
**Solution**: A `setTimeout` of 600ms is used. If the user switches images within this window, the timeout is cleared, and no request is made.

#### 2. Cancellation with AbortController
**Why?** Even with debouncing, a user might linger for 700ms (triggering load) and then switch. We don't want the previous large image to arrive and overwrite the current one, or waste bandwidth.
**Solution**: A global `AbortController` is maintained.
```javascript
if (abortController) {
    abortController.abort(); // Cancel previous in-flight request
}
abortController = new AbortController();
fetch(url, { signal: abortController.signal }) ...
```

#### 4. Image Path Detection
**Why?** Gradio's DOM structure is complex. The `<img>` src often changes (e.g., base64 -> URL).
**Solution**:
*   We use `getSelectedImagePath()` which reads from the JSON metadata panel (`.json-holder`) that updates instantly when an image is selected.
*   Falls back to textarea/input fields if JSON metadata is not available.
*   This ensures we are loading the *correct* file, especially important for RAW files where the preview might be a cached JPEG but we want to load the real thing or a fresh high-res extraction.
*   *Note: `extractImagePath()` function was removed in favor of this metadata-based approach.*

#### 4. RAW vs. Standard Handling
*   **Standard Images**: Loaded via `/file={path}`.
*   **RAW Images** (.NEF, .CR2, etc.): Loaded via `/api/raw-preview?path={encoded_path}`. This endpoint (added previously) extracts the embedded JPEG from the RAW file server-side, which is faster than sending the full RAW file.

### Code Walkthrough

```javascript
function loadFullResolution(imgPath, previewId, imgElement) {
    // 1. Cancel previous load
    if (abortController) {
        abortController.abort();
        abortController = null;
    }
    
    // 2. Cleanup previous ObjectURL to prevent memory leak
    if (previousObjectURL) {
        URL.revokeObjectURL(previousObjectURL);
        previousObjectURL = null;
    }
    
    // 3. Check for stale ID (user already navigated away)
    if (previewId !== currentPreviewId) return;
    
    // 4. Setup new controller
    abortController = new AbortController();
    
    // 5. Construct URL (RAW vs Standard)
    let url = isRaw ? `/api/raw-preview...` : `/file=...`;
    
    // 6. Fetch & Swap
    fetch(url, { signal: abortController.signal })
        .then(response => {
            if (!response.ok) throw new Error('Network response was not ok');
            return response.blob();
        })
        .then(blob => {
            if (previewId !== currentPreviewId) return; // Changed, discard
            
            // Create ObjectURL from blob
            const objectURL = URL.createObjectURL(blob);
            previousObjectURL = objectURL;  // Track for cleanup
            imgElement.onload = () => {
                hideLoadingIndicator(imgElement);
            };
            imgElement.src = objectURL;
        })
        .catch(err => {
            if (err.name !== 'AbortError') {
                console.error('Full res load error:', err);
            }
            hideLoadingIndicator(imgElement);
        });
}
```

**Memory Management**: The implementation now properly tracks and revokes ObjectURLs to prevent memory leaks:
- Previous ObjectURL is revoked before creating a new one
- ObjectURL is revoked when navigating away from preview
- ObjectURL is revoked when switching to a new image

## Verification & Testing

### Test Scenario A: Rapid Navigation
1.  Open Gallery.
2.  Click an image to open preview.
3.  Press `Right Arrow` key 5 times quickly (faster than 600ms).
4.  **Expected Result**:
    *   No "Loading Full Res..." indicator appears.
    *   Network tab does NOT show 5 requests to `/file=...`.
    *   Only the final image eventually loads if you stop.

### Test Scenario B: Successful Load
1.  Open an image and wait 1 second.
2.  **Expected Result**:
    *   "Loading Full Res..." badge appears over the image.
    *   Image visibly sharpens (if thumbnail was blurry).
    *   Loader disappears.

### Test Scenario C: Cancellation
1.  Open a large RAW file (wait 600ms for load to start).
2.  Immediately switch to next image while "Loading..." is visible.
3.  **Expected Result**:
    *   The request in Network tab shows status `(cancelled)`.
    *   The new image shows its thumbnail immediately.
    *   The old image does NOT flash onto the new one.

## Review Notes
*   **Risk**: If Gradio significantly changes its DOM structure (class names like `.gallery` or `.preview`), the selectors might fail. This is a common risk with DOM injection.
*   **Performance**: The feature is purely additive and client-side. It does not affect server performance unless users actually stop to view images.
*   **Memory Management**: ObjectURLs are properly cleaned up to prevent memory leaks. Previous ObjectURLs are revoked when:
    - A new image starts loading
    - User navigates away from preview
    - User switches to a different image

# Fullscreen Navigation Issue (Persistent)

**Status**: Unresolved
**Date**: January 17, 2026
**Symptoms**:
- When viewing an image in fullscreen/lightbox mode.
- Navigating to the *next* or *previous* image (via arrow keys or buttons).
- The new image loads but remains as a low-resolution thumbnail (or standard preview), instead of the high-resolution source image.
- Exiting fullscreen and re-entering it loads the full resolution correctly.

## Investigation & Attempts

### 1. Initial Diagnosis
The issue was identified as a race condition. When Gradio's gallery navigation occurs:
1.  The `<img>` src is updated by Gradio to the new thumbnail/preview.
2.  The `api/raw-preview` or `source-image` logic needs to trigger.
3.  However, the "Selected Image Path" (stored in a hidden textbox) might not have been updated by Gradio's backend yet.
4.  If our logic reads the *old* path, it might think it's already loaded or load the wrong image.

### 2. Attempted Fix (Race Condition Handling)
We modified `modules/ui/assets.py` (`handlePreviewChange`) to:
- Detect when the `src` changes back to a non-source image (indicating navigation).
- Poll (`checkPathAndLoad`) for the selected path to update.
- Heuristic: If the path matches the *previous* loaded path but the image is a thumbnail, assume it's stale and retry.

### 3. Current Outcome
The user reports the issue **still persists**. This suggests:
- The polling logic might timeout before the path updates.
- Or Gradio doesn't update the path textbox at all during simple gallery navigation (only on explicit selection/click).
- Or the `MutationObserver` isn't triggering reliably on the src change during navigation.

## Next Steps for Debugging
- **Verify Path Updates**: Check if the hidden textbox `gallery-selected-path` actually updates during arrow key navigation. If not, we have no way to know *what* the new file is.
- **Index-Based Logic**: Instead of relying on the path text, we might need to rely on the *index* of the image in the gallery array (if accessible from DOM) and cross-reference with a stored list of all paths.
- **Event Listeners**: Verify if keyup/keydown events are successfully triggering the "Next" buttons and if those buttons trigger the Gradio event chain.

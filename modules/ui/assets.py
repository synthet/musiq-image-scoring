"""
UI assets module for CSS and JavaScript.

This module provides:
- get_css(): Returns the complete CSS stylesheet for the dark theme UI
- get_tree_js(): Returns JavaScript for folder tree interactions and gallery enhancements

The CSS includes styling for:
- Dark theme with GitHub-inspired color palette
- Gallery grid and lightbox preview
- Folder tree navigation
- Stack badges and preview popups
- Image comparison modal
- Lazy loading for full-resolution images

The JavaScript includes:
- Folder tree selection handling
- Gallery lightbox close button
- Stack badge overlays
- Keyboard shortcuts for stack operations
- Image comparison mode
- Lazy full-resolution image loading
"""
from pathlib import Path

_UI_DIR = Path(__file__).resolve().parent
_GRADIO_DESIGN_TOKENS = _UI_DIR / "gradio_design_tokens.css"

# Custom CSS for modern dark UI
custom_css = """
/* ========== ROOT THEME VARIABLES ========== */
:root {
    --bg-primary: #1b1b1f;
    --bg-secondary: #25262c;
    --bg-tertiary: #2a2b31;
    --bg-elevated: #343640;
    --bg-input: #3b3d47;
    --bg-console: #17181e;
    
    --border-color: #474a56;
    --border-subtle: #5a5e6a;
    
    --text-primary: rgba(255, 255, 255, 0.92);
    --text-secondary: #c7c9d2;
    --text-muted: #8b8f99;
    
    --accent-primary: #1d70ff;
    --accent-hover: #4894ff;
    --accent-success: #4caf50;
    --accent-warning: #d29922;
    --accent-danger: #f14f45;
    --accent-purple: #a371f7;
    --accent-queued: #80838a;
    
    --shadow-sm: 0 1px 2px rgba(0,0,0,0.3);
    --shadow-md: 0 4px 12px rgba(0,0,0,0.4);
    --shadow-lg: 0 8px 20px rgba(0, 0, 0, 0.18);
    
    --radius-sm: 4px;
    --radius-md: 6px;
    --radius-lg: 8px;
    
    --transition-fast: 160ms ease;
    --transition-normal: 250ms ease;
}

/* ========== GLOBAL STYLES ========== */
html,
body,
.gradio-container {
    margin: 0 !important;
    padding: 0 !important;
    min-height: 100vh !important;
    background:
        radial-gradient(circle at 18% -10%, rgba(0, 122, 204, 0.1), transparent 42%),
        var(--bg-primary) !important;
    color: var(--text-primary);
    font-family: "Segoe UI", Tahoma, Geneva, Verdana, sans-serif !important;
}

.dark {
    --block-background-fill: var(--bg-secondary) !important;
    --block-border-color: var(--border-color) !important;
    --body-background-fill: var(--bg-primary) !important;
    --button-primary-background-fill: var(--accent-primary) !important;
    --button-primary-background-fill-hover: var(--accent-hover) !important;
    --input-background-fill: var(--bg-input) !important;
}

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

/* ========== COMPACT LAYOUT ========== */
/* Reduce vertical gaps between rows and blocks */
.contain > .column > .row,
.contain > .column > .block,
.contain > .column > .form {
    margin-bottom: 8px !important;
}

.contain > .column > .accordion {
    margin-bottom: 8px !important;
}

/* Reduce padding on blocks */
.block {
    padding-top: 8px !important;
    padding-bottom: 8px !important;
}

/* Compact rows */
.row {
    gap: 8px !important;
}

/* ========== HEADER ========== */
h1 {
    font-size: 1.75rem !important;
    font-weight: 600 !important;
    letter-spacing: -0.5px !important;
    color: var(--text-primary) !important;
    margin-bottom: 0.5rem !important;
}

/* ========== TABS ========== */
.tabs {
  display: flex;
  border-bottom: 1px solid var(--border-color) !important;
  margin-bottom: 10px !important;
}

.tabs .tab-nav {
  gap: 4px;
  background: transparent !important;
  border: none !important;
  border-radius: 0 !important;
}

.tabs .tab-nav button {
  background: transparent !important;
  border: none !important;
  border-radius: var(--radius-md) !important;
  color: var(--text-secondary) !important;
  padding: 10px 14px !important;
  font-size: 0.9rem !important;
  font-weight: 500 !important;
  box-shadow: none !important;
  transition: color var(--transition-fast), box-shadow var(--transition-fast) !important;
}

.tabs .tab-nav button.selected {
  background: transparent !important;
  color: var(--accent-hover) !important;
  box-shadow: inset 0 -2px 0 var(--accent-primary) !important;
  font-weight: 600 !important;
}

.tabs .tab-nav button:hover:not(.selected) {
  background: var(--bg-input) !important;
}

/* ========== TREE VIEW ========== */
.tree-container,
.folder-tree-container {
  font-family: "Segoe UI", Tahoma, sans-serif;
  font-size: 0.85rem;
  color: var(--text-muted);
  line-height: 1.75;
  margin-top: 8px;
  max-height: 480px;
  overflow-y: auto;
}

/* .tree-content is used by ui_tree.py HTML output and JS selectFolder() */
.tree-content,
.tree-item {
  cursor: pointer;
  padding: 5px 8px;
  border-radius: var(--radius-md);
  display: inline-block;
  user-select: none;
  color: var(--text-secondary);
  transition: background-color var(--transition-fast), color var(--transition-fast);
}

.tree-content:hover,
.tree-item:hover {
  background-color: var(--bg-elevated);
  color: var(--text-primary);
}

.tree-content.selected,
.tree-item.selected {
  background-color: var(--accent-primary);
  color: #fff;
}

.tree-item.selected .tree-icon {
  color: rgba(255, 255, 255, 0.88) !important;
}

.tree-icon {
  font-family: monospace;
  font-size: 0.8rem;
  font-weight: bold;
  width: 14px;
  text-align: center;
}

.tree-icon.done {
  color: var(--accent-success);
}

.tree-icon.partial {
  color: #5bc0de;
}

.tree-icon.failed {
  color: var(--accent-danger);
}

.tree-icon.empty {
  color: var(--text-muted);
}

.tree-indent-1 { margin-left: 20px; }
.tree-indent-2 { margin-left: 36px; }
.tree-indent-3 { margin-left: 52px; }

summary { outline: none; cursor: pointer; }
#folder_tree_selection { display: none; } 

/* ========== GALLERY HEADER ========== */
.gallery-header {
    display: flex !important;
    align-items: center !important;
    gap: 12px !important;
    padding: 16px 20px !important;
    background: var(--bg-secondary) !important;
    border: 1px solid var(--border-color) !important;
    border-radius: var(--radius-lg) !important;
    margin-bottom: 16px !important;
}

.folder-badge {
    display: inline-flex !important;
    align-items: center !important;
    gap: 8px !important;
    padding: 8px 16px !important;
    background: linear-gradient(135deg, var(--accent-primary) 0%, var(--accent-purple) 100%) !important;
    border-radius: 20px !important;
    color: white !important;
    font-weight: 600 !important;
    font-size: 0.9rem !important;
    box-shadow: var(--shadow-sm) !important;
}

.folder-badge::before {
    content: "📁";
    font-size: 1rem;
}

/* ========== BUTTONS ========== */
button,
.gr-button {
  border-radius: var(--radius-md) !important;
  font-size: 0.9rem !important;
  min-height: 38px !important;
  transition:
    transform var(--transition-fast),
    background-color var(--transition-fast),
    border-color var(--transition-fast) !important;
}

.btn,
.secondary-btn,
.secondary-btn button {
  background-color: var(--bg-input) !important;
  color: var(--text-primary) !important;
  border: 1px solid var(--border-subtle) !important;
}

.btn:hover,
.secondary-btn:hover,
.secondary-btn button:hover {
  background-color: #4a4a4a !important;
}

.primary-btn,
.primary-btn button {
  background-color: var(--accent-primary) !important;
  border-color: var(--accent-primary) !important;
  color: white !important;
  font-weight: 600 !important;
}

.primary-btn:hover,
.primary-btn button:hover {
  background-color: var(--accent-hover) !important;
  border-color: var(--accent-hover) !important;
}

.danger-btn,
.danger-btn button {
  background-color: transparent !important;
  border: 1px solid var(--accent-danger) !important;
  color: var(--accent-danger) !important;
  font-weight: 600 !important;
}

.danger-btn:hover,
.danger-btn button:hover {
  background-color: rgba(241, 79, 69, 0.1) !important;
}

.success-btn,
.success-btn button {
  background-color: var(--accent-success) !important;
  border-color: var(--accent-success) !important;
  color: white !important;
  border-left: 4px solid rgba(255, 255, 255, 0.9) !important;
}

.primary-btn:hover,
.danger-btn:hover,
.secondary-btn:hover,
.success-btn:hover {
  transform: translateY(-1px);
}

/* ========== GALLERY GRID ========== */
.gallery-container {
    background: var(--bg-secondary) !important;
    border: 1px solid var(--border-color) !important;
    border-radius: var(--radius-lg) !important;
    padding: 16px !important;
}

/* Reset Gradio gallery wrapper positioning in preview mode */
.gallery-container .wrap,
.gallery-container > div {
    padding: 0 !important;
    margin: 0 !important;
}

/* Ensure the gallery block fills properly */
.block.gallery-container {
    padding: 0 !important;
}

.gallery .gallery-item {
    border-radius: var(--radius-md) !important;
    overflow: hidden !important;
    transition: all var(--transition-normal) !important;
    border: 2px solid transparent !important;
}

.gallery .gallery-item:hover {
    transform: scale(1.02) !important;
    border-color: var(--accent-primary) !important;
    box-shadow: var(--shadow-md) !important;
}

.gallery .gallery-item.selected {
    border-color: var(--accent-success) !important;
    box-shadow: 0 0 0 3px rgba(63, 185, 80, 0.3) !important;
}

/* ========== DETAILS PANEL ========== */
.details-panel {
    background: var(--bg-secondary) !important;
    border: 1px solid var(--border-color) !important;
    border-radius: var(--radius-lg) !important;
    padding: 20px !important;
}

.score-card {
    background: linear-gradient(135deg, var(--bg-tertiary) 0%, var(--bg-secondary) 100%) !important;
    border: 1px solid var(--border-color) !important;
    border-radius: var(--radius-md) !important;
    padding: 16px !important;
    text-align: center !important;
}

.score-value {
    font-size: 2rem !important;
    font-weight: 700 !important;
    color: var(--accent-primary) !important;
}

.score-label {
    font-size: 0.85rem !important;
    color: var(--text-secondary) !important;
    text-transform: uppercase !important;
    letter-spacing: 0.5px !important;
}

/* ========== INPUTS ========== */
.input-container input,
.input-container textarea {
    background: var(--bg-tertiary) !important;
    border: 1px solid var(--border-color) !important;
    border-radius: var(--radius-md) !important;
    color: var(--text-primary) !important;
    padding: 12px 16px !important;
    transition: all var(--transition-fast) !important;
}

.input-container input:focus,
.input-container textarea:focus {
    border-color: var(--accent-primary) !important;
    box-shadow: 0 0 0 3px rgba(88, 166, 255, 0.2) !important;
    outline: none !important;
}

/* ========== DROPDOWNS ========== */
.dropdown-container {
    position: relative !important;
}

select, .svelte-dropdown {
    background: var(--bg-tertiary) !important;
    border: 1px solid var(--border-color) !important;
    border-radius: var(--radius-md) !important;
    color: var(--text-primary) !important;
    padding: 10px 14px !important;
}

/* ========== ACCORDION ========== */
.accordion {
    background: var(--bg-secondary) !important;
    border: 1px solid var(--border-color) !important;
    border-radius: var(--radius-lg) !important;
    overflow: hidden !important;
    margin-bottom: 4px !important;
}

.accordion > .label-wrap {
    background: var(--bg-tertiary) !important;
    padding: 10px 16px !important;
    font-weight: 600 !important;
    color: var(--text-primary) !important;
    border-bottom: 1px solid var(--border-color) !important;
    display: flex !important;
    align-items: center !important;
}

/* Fix dropdown triangle alignment in all accordions (Gradio label-wrap + icon) */
.accordion .label-wrap .icon,
button.label-wrap .icon {
    display: inline-flex !important;
    align-items: center !important;
    vertical-align: middle !important;
}

/* ========== PAGINATION ========== */
.pagination-container {
    display: flex !important;
    align-items: center !important;
    justify-content: center !important;
    gap: 4px !important;
    padding: 6px 12px !important;
    margin: 0 !important;
}

.page-btn {
    min-width: 40px !important;
    padding: 8px 12px !important;
    font-size: 1rem !important;
}

.page-btn:hover {
    background: var(--accent-primary) !important;
    color: white !important;
    font-weight: bold !important;
}

.page-indicator {
    background: var(--bg-tertiary) !important;
    padding: 8px 20px !important;
    border-radius: var(--radius-md) !important;
    color: var(--text-primary) !important;
    font-weight: 500 !important;
    border: 1px solid var(--border-color) !important;
    min-width: 120px !important;
    text-align: center !important;
}

/* ========== MODAL & LIGHTBOX ========== */
/* Only target the main preview image, not thumbnails */
.preview .media-button img, 
.lightbox img, 
.modal img {
    object-fit: contain !important;
    width: auto !important;
    height: auto !important;
    max-width: 100% !important;
    max-height: calc(100% - 80px) !important;
    margin: auto;
}

/* Ensure thumbnail images display properly */
.gallery .thumbnails img,
.gallery .thumbnail-item img,
.thumbnails img,
.thumbnail-item img {
    width: 100% !important;
    height: 100% !important;
    object-fit: cover !important;
    display: block !important;
    opacity: 1 !important;
    visibility: visible !important;
}

/* Gradio Gallery Lightbox/Preview Mode Styling */
.gallery .preview,
.gallery button.preview {
    position: relative !important;
    width: 100% !important;
    display: block !important;
    padding: 0 !important;
    margin: 0 !important;
    left: 0 !important;
    right: 0 !important;
    box-sizing: border-box !important;
}

/* Gallery container should clip images but not buttons (buttons are fixed positioned) */
.gallery-container {
    overflow: hidden !important;
    padding: 0 !important;
}

/* The media-button contains the preview image - make it fill the container */
.gallery button.preview .media-button,
.gallery .preview .media-button {
    overflow: hidden !important;
    display: flex !important;
    align-items: center !important;
    justify-content: center !important;
    width: 100% !important;
    max-width: 100% !important;
    margin: 0 !important;
    padding: 0 !important;
    left: 0 !important;
    right: 0 !important;
    position: relative !important;
    box-sizing: border-box !important;
}

.gallery button.preview .media-button img,
.gallery .preview .media-button img {
    object-fit: contain !important;
    max-width: 100% !important;
    max-height: 100% !important;
    width: auto !important;
    height: auto !important;
    display: block !important;
    margin: 0 auto !important;
}

/* Override hide-top-corner to show controls - be more specific */
/* Since icon-button-wrapper is position:fixed, parent overflow doesn't affect it */
.gallery .hide-top-corner,
.gallery .top-panel,
.gallery .top-panel.hide-top-corner,
.gallery .icon-button-wrapper.hide-top-corner,
.gallery .icon-button-wrapper.top-panel.hide-top-corner {
    opacity: 1 !important;
    visibility: visible !important;
    display: flex !important;
    clip: auto !important;
    clip-path: none !important;
}

/* Style the built-in gallery controls (download, fullscreen, close) */
/* position:fixed removes element from document flow - parent overflow doesn't affect it */
.gallery .icon-buttons,
.gallery .icon-button-wrapper,
.gallery .icon-button-wrapper.top-panel {
    position: fixed !important;
    top: 15px !important;
    right: 180px !important;
    z-index: 99998 !important;
    display: flex !important;
    flex-direction: row !important;
    gap: 8px !important;
    opacity: 1 !important;
    visibility: visible !important;
    width: auto !important;
    max-width: none !important;
    transform: none !important;
}

.gallery .icon-buttons button,
.gallery .icon-button-wrapper button {
    background: var(--bg-elevated) !important;
    border: 1px solid var(--border-color) !important;
    border-radius: var(--radius-md) !important;
    padding: 10px 14px !important;
    color: var(--text-primary) !important;
    cursor: pointer !important;
    transition: all 0.2s ease !important;
    opacity: 1 !important;
    visibility: visible !important;
    display: inline-flex !important;
    min-width: auto !important;
    flex-shrink: 0 !important;
}

.gallery .icon-buttons button:hover,
.gallery .icon-button-wrapper button:hover {
    background: var(--accent-primary) !important;
    border-color: var(--accent-primary) !important;
}

/* Navigation hint text at bottom of preview */
.gallery button.preview::after {
    content: "Press ESC or click '✕ Back to Grid' to return" !important;
    position: fixed !important;
    bottom: 80px !important;
    left: 50% !important;
    transform: translateX(-50%) !important;
    z-index: 99990 !important;
    background: rgba(0, 0, 0, 0.85) !important;
    color: #a0a0a0 !important;
    padding: 12px 24px !important;
    border-radius: 25px !important;
    font-size: 13px !important;
    pointer-events: none !important;
    border: 1px solid rgba(255,255,255,0.1) !important;
}

/* Thumbnail strip styling */
.gallery .thumbnails {
    background: rgba(0, 0, 0, 0.9) !important;
    padding: 12px !important;
    border-radius: var(--radius-lg) !important;
    margin: 16px auto 0 auto !important;
    width: 100% !important;
    max-width: 100% !important;
    display: flex !important;
    justify-content: center !important;
    flex-wrap: wrap !important;
    gap: 8px !important;
}

.gallery .thumbnails button,
.gallery .thumbnail-item {
    border-radius: var(--radius-sm) !important;
    border: 2px solid transparent !important;
    transition: all 0.2s ease !important;
    overflow: visible !important;
    background-size: cover !important;
    background-position: center !important;
    background-repeat: no-repeat !important;
}

.gallery .thumbnails button:hover,
.gallery .thumbnail-item:hover {
    border-color: var(--accent-primary) !important;
}

.gallery .thumbnails button.selected,
.gallery .thumbnail-item.selected {
    border-color: var(--accent-warning) !important;
    box-shadow: 0 0 0 2px rgba(210, 153, 34, 0.3) !important;
}

/* Ensure thumbnail images are visible */
.gallery .thumbnails button img,
.gallery .thumbnail-item img {
    width: 100% !important;
    height: 100% !important;
    object-fit: cover !important;
    display: block !important;
    visibility: visible !important;
    opacity: 1 !important;
}

/* Ensure the preview backdrop is clickable to close */
.gallery .preview > div:first-child {
    cursor: pointer !important;
}

/* Preview content divs should contain images properly and be centered */
/* Exclude icon-button-wrapper and thumbnails from these styles */
.gallery button.preview > div:not(.icon-button-wrapper):not(.thumbnails),
.gallery .preview > div:not(.icon-button-wrapper):not(.thumbnails) {
    overflow: hidden !important;
    width: 100% !important;
    display: flex !important;
    align-items: center !important;
    justify-content: center !important;
    margin: 0 !important;
    padding: 0 !important;
    left: 0 !important;
    right: 0 !important;
    box-sizing: border-box !important;
}

/* Svelte gallery specific overrides */
.svelte-ao1xvt.preview,
button.preview.svelte-ao1xvt {
    padding: 0 !important;
    margin: 0 !important;
    width: 100% !important;
    left: 0 !important;
}

.svelte-ao1xvt.media-button,
button.media-button.svelte-ao1xvt {
    margin: 0 !important;
    padding: 0 !important;
    width: 100% !important;
    left: 0 !important;
}

/* Specifically target the close button in gallery preview */
.gallery button.preview .icon-button-wrapper button,
.gallery .preview .icon-button-wrapper button,
.gallery [class*="close"],
.gallery button[aria-label*="close"],
.gallery button[aria-label*="Close"] {
    opacity: 1 !important;
    visibility: visible !important;
    display: inline-flex !important;
    pointer-events: auto !important;
}

.full-res-modal {
    position: fixed !important;
    top: 0 !important;
    left: 0 !important;
    width: 100% !important;
    height: 100% !important;
    background-color: rgba(0, 0, 0, 0.95) !important;
    z-index: 9999 !important;
    display: flex !important;
    flex-direction: column !important;
    align-items: center !important;
    justify-content: center !important;
    backdrop-filter: blur(10px) !important;
}

.modal-close-btn {
    position: absolute !important;
    top: 20px !important;
    right: 30px !important;
    z-index: 10000 !important;
    background: var(--bg-elevated) !important;
    border: 1px solid var(--border-color) !important;
    border-radius: var(--radius-md) !important;
    padding: 10px 20px !important;
}

.modal-image-container {
    display: flex !important;
    justify-content: center !important;
    align-items: center !important;
    width: 95% !important;
    height: 90% !important;
    border: none !important;
    background-color: transparent !important;
}

.modal-image-container img {
    max-height: 90vh !important;
    max-width: 95vw !important;
    object-fit: contain !important;
    border-radius: var(--radius-lg) !important;
}

/* ========== STATUS INDICATORS ========== */
.status-badge {
    display: inline-flex !important;
    align-items: center !important;
    gap: 6px !important;
    padding: 6px 12px !important;
    border-radius: 20px !important;
    font-size: 0.85rem !important;
    font-weight: 500 !important;
}

.status-badge.success {
    background: rgba(63, 185, 80, 0.15) !important;
    color: var(--accent-success) !important;
    border: 1px solid rgba(63, 185, 80, 0.3) !important;
}

.status-badge.warning {
    background: rgba(210, 153, 34, 0.15) !important;
    color: var(--accent-warning) !important;
    border: 1px solid rgba(210, 153, 34, 0.3) !important;
}

.status-badge.error {
    background: rgba(241, 79, 69, 0.15) !important;
    color: var(--accent-danger) !important;
    border: 1px solid rgba(241, 79, 69, 0.3) !important;
}

.status-badge.info {
    background: rgba(0, 122, 204, 0.15) !important;
    color: var(--accent-primary) !important;
    border: 1px solid rgba(0, 122, 204, 0.3) !important;
}

/* ========== PROGRESS BAR ========== */
.progress-container {
    background: var(--bg-tertiary) !important;
    border-radius: var(--radius-md) !important;
    height: 8px !important;
    overflow: hidden !important;
}

.progress-bar {
    height: 100% !important;
    background: linear-gradient(90deg, var(--accent-primary) 0%, var(--accent-purple) 100%) !important;
    border-radius: var(--radius-md) !important;
    transition: width var(--transition-normal) !important;
}

/* ========== LABELS ========== */
.label {
    color: var(--text-secondary) !important;
    font-size: 0.85rem !important;
    font-weight: 500 !important;
    text-transform: uppercase !important;
    letter-spacing: 0.5px !important;
    margin-bottom: 6px !important;
}

/* ========== CARDS ========== */
.card {
    background: var(--bg-secondary) !important;
    border: 1px solid var(--border-color) !important;
    border-radius: var(--radius-lg) !important;
    padding: 20px !important;
    transition: all var(--transition-fast) !important;
}

.card:hover {
    border-color: var(--accent-primary) !important;
    box-shadow: var(--shadow-md) !important;
}

/* ========== EMPTY STATE ========== */
.empty-state {
    display: flex !important;
    flex-direction: column !important;
    align-items: center !important;
    justify-content: center !important;
    padding: 60px 20px !important;
    color: var(--text-muted) !important;
}

.empty-state-icon {
    font-size: 3rem !important;
    margin-bottom: 16px !important;
    opacity: 0.5 !important;
}

/* ========== SCROLLBAR ========== */
::-webkit-scrollbar {
    width: 8px;
    height: 8px;
}

::-webkit-scrollbar-track {
    background: var(--bg-primary);
}

::-webkit-scrollbar-thumb {
    background: var(--bg-elevated);
    border-radius: 4px;
}

::-webkit-scrollbar-thumb:hover {
    background: var(--text-muted);
}

/* ========== ANIMATION ========== */
@keyframes fadeIn {
    from { opacity: 0; transform: translateY(10px); }
    to { opacity: 1; transform: translateY(0); }
}

.animate-in {
    animation: fadeIn var(--transition-normal) ease-out !important;
}

/* ========== FILTER CHIPS ========== */
.filter-chip {
    display: inline-flex !important;
    align-items: center !important;
    gap: 6px !important;
    padding: 6px 14px !important;
    background: var(--bg-tertiary) !important;
    border: 1px solid var(--border-color) !important;
    border-radius: 20px !important;
    font-size: 0.85rem !important;
    color: var(--text-secondary) !important;
    transition: all var(--transition-fast) !important;
}

.filter-chip:hover {
    border-color: var(--accent-primary) !important;
    color: var(--text-primary) !important;
}

.filter-chip.active {
    background: var(--accent-primary) !important;
    border-color: var(--accent-primary) !important;
    color: white !important;
}

/* ========== PIPELINE PANELS ========== */
.sidebar {
  background-color: var(--bg-secondary) !important;
  border-right: 1px solid var(--border-color) !important;
  border-radius: var(--radius-md) !important;
  padding: 10px 12px !important;
  overflow-y: auto !important;
}

.sidebar h3 {
  margin-top: 0 !important;
}

.panel {
  background-color: var(--bg-secondary) !important;
  border: 1px solid var(--border-color) !important;
  border-radius: var(--radius-lg) !important;
  overflow: hidden !important;
  margin-bottom: 14px !important;
  padding: 0 !important;
  box-shadow: var(--shadow-lg) !important;
}

.panel .wrap, .panel .form {
  padding: 0 !important;
  border: none !important;
}

.panel-header {
  padding: 12px 16px !important;
  border-bottom: 1px solid var(--border-color) !important;
  background-color: #2f3038 !important;
  display: flex !important;
  justify-content: space-between !important;
  align-items: center !important;
  gap: 12px !important;
}

.panel-title {
  margin: 0 !important;
  font-size: 1rem !important;
  font-weight: 600 !important;
}

.panel-body {
  padding: 14px !important;
}

.header-note {
  font-size: 0.85rem !important;
  color: var(--text-secondary) !important;
}

.folder-summary h3,
.legend-title {
  margin-top: 0 !important;
  margin-bottom: 10px !important;
}

.folder-summary p {
  font-size: 0.85rem !important;
  color: var(--text-muted) !important;
  line-height: 1.5 !important;
  margin: 0 !important;
}

.folder-summary strong {
  color: var(--text-primary) !important;
}

.legend {
  display: grid !important;
  grid-template-columns: 1fr 1fr !important;
  gap: 8px !important;
  font-size: 0.85rem !important;
  color: var(--text-muted) !important;
  margin-top: 10px !important;
}

.legend-item {
  display: inline-flex !important;
  align-items: center !important;
  gap: 6px !important;
}

/* STEPPER */
.stepper {
  display: flex !important;
  align-items: center !important;
  justify-content: space-between !important;
  gap: 8px !important;
  margin-top: 6px !important;
  margin-bottom: 10px !important;
  overflow-x: auto !important;
  padding-bottom: 4px !important;
}

.step {
  display: flex !important;
  flex-direction: column !important;
  align-items: center !important;
  gap: 8px !important;
  flex: 1 !important;
  min-width: 100px !important;
}

.step-dot {
  width: 28px !important;
  height: 28px !important;
  border-radius: 50% !important;
  background-color: var(--bg-elevated) !important;
  border: 2px solid var(--border-subtle) !important;
  display: flex !important;
  align-items: center !important;
  justify-content: center !important;
  font-size: 0.8rem !important;
  font-weight: bold !important;
  color: var(--text-muted) !important;
  position: relative !important;
  z-index: 2 !important;
}

.step-label {
  font-size: 0.8rem !important;
  font-weight: 600 !important;
  color: var(--text-secondary) !important;
  text-transform: uppercase !important;
}

.step-count {
  font-size: 0.75rem !important;
  color: var(--text-muted) !important;
}

.connector {
  height: 2px !important;
  background-color: var(--border-subtle) !important;
  flex: 1 !important;
  margin-top: -38px !important;
  min-width: 50px !important;
  position: relative !important;
  z-index: 1 !important;
}

.step.done .step-dot {
  border-color: var(--accent-success) !important;
  color: var(--accent-success) !important;
  background-color: rgba(76, 175, 80, 0.1) !important;
}

.step.running .step-dot {
  border-color: var(--accent-primary) !important;
  color: var(--accent-primary) !important;
  background-color: rgba(0, 122, 204, 0.1) !important;
  box-shadow: 0 0 0 4px rgba(0, 122, 204, 0.18) !important;
  animation: running-pulse 1.6s ease-in-out infinite !important;
}

.connector.done {
  background-color: var(--accent-success) !important;
}

.connector.running {
  background: linear-gradient(90deg, var(--accent-success), var(--accent-primary)) !important;
}

@keyframes running-pulse {
    0%   { box-shadow: 0 0 0 0   rgba(0, 122, 204, 0.35); }
    50%  { box-shadow: 0 0 0 6px rgba(0, 122, 204, 0.10); }
    100% { box-shadow: 0 0 0 0   rgba(0, 122, 204, 0.00); }
}

/* PHASE CARDS */
.phase-grid {
  gap: 10px !important;
  display: flex !important;
}

.phase-card {
  background-color: var(--bg-elevated) !important;
  border: 1px solid var(--border-color) !important;
  border-radius: var(--radius-md) !important;
  border-left: 4px solid var(--accent-queued) !important;
  padding: 15px !important;
  flex: 1 !important;
  min-width: 25% !important;
}

.phase-card.queued {
  border-left-color: var(--accent-queued) !important;
}

.phase-card.running {
  border-color: var(--accent-primary) !important;
  border-left-color: var(--accent-primary) !important;
  box-shadow: 0 0 0 1px rgba(0, 122, 204, 0.2) !important;
}

.phase-head {
  display: flex !important;
  justify-content: space-between !important;
  align-items: center !important;
  margin-bottom: 12px !important;
}

.phase-title {
  font-weight: 600 !important;
  font-size: 0.95rem !important;
  display: flex !important;
  align-items: center !important;
  gap: 8px !important;
  color: var(--text-primary) !important;
}

.phase-icon {
  width: 24px !important;
  height: 24px !important;
  background: var(--bg-input) !important;
  border-radius: var(--radius-sm) !important;
  display: flex !important;
  align-items: center !important;
  justify-content: center !important;
  font-size: 0.8rem !important;
  color: var(--text-secondary) !important;
  font-weight: bold !important;
}

.phase-card.running .phase-icon {
  background: var(--accent-primary) !important;
  color: white !important;
}

.phase-status {
  font-size: 0.75rem !important;
  padding: 2px 6px !important;
  border-radius: 4px !important;
  background-color: var(--bg-input) !important;
  color: var(--text-secondary) !important;
  text-transform: uppercase !important;
}

.phase-card.running .phase-status {
  background-color: rgba(0, 122, 204, 0.2) !important;
  color: #61baff !important;
}

.phase-stats {
  font-size: 0.85rem !important;
  color: var(--text-secondary) !important;
  margin-bottom: 12px !important;
}


.queue-board {
  margin-top: 10px !important;
}

.queue-table-wrap {
  overflow-x: auto !important;
}

.queue-table {
  width: 100% !important;
  border-collapse: collapse !important;
  font-size: 0.8rem !important;
}

.queue-table th,
.queue-table td {
  border: 1px solid var(--border-color) !important;
  padding: 6px 8px !important;
  text-align: left !important;
  vertical-align: top !important;
}

.queue-table th[data-sort-col] {
  cursor: pointer !important;
}

.queue-chip {
  display: inline-block !important;
  padding: 2px 6px !important;
  border-radius: 999px !important;
  font-size: 0.72rem !important;
  text-transform: uppercase !important;
  letter-spacing: 0.02em !important;
  border: 1px solid var(--border-color) !important;
}

.queue-chip-queued { background: rgba(0, 122, 204, 0.22) !important; color: #9ad6ff !important; }
.queue-chip-paused { background: rgba(255, 166, 0, 0.18) !important; color: #ffd38a !important; }
.queue-chip-failed { background: rgba(255, 59, 48, 0.18) !important; color: #ffb0aa !important; }

.queue-action-btn {
  font-size: 0.72rem !important;
  margin: 2px !important;
  padding: 3px 6px !important;
  border-radius: 6px !important;
  border: 1px solid var(--border-color) !important;
  background: var(--bg-input) !important;
  color: var(--text-primary) !important;
}

.queue-action-btn:disabled {
  opacity: 0.5 !important;
  cursor: not-allowed !important;
}


.queue-actions {
  min-width: 235px !important;
}

.queue-actions .queue-action-btn {
  white-space: nowrap !important;
}

.progress {
  height: 6px !important;
  background-color: var(--bg-primary) !important;
  border-radius: 3px !important;
  overflow: hidden !important;
  border: 1px solid var(--border-color) !important;
  margin-bottom: 15px !important;
}

.progress-fill {
  height: 100% !important;
  background-color: var(--text-muted) !important;
  /* width comes from inline style (e.g. width: 84.5%) to match displayed numbers */
  min-width: 0;
  transition: width 0.2s ease;
}

.phase-card.running .progress-fill {
  background-color: var(--accent-primary) !important;
}

/* OPTIONS ACCORDION */
.options-accordion {
  background: transparent !important;
  border: 1px solid var(--border-color) !important;
  border-radius: var(--radius-md) !important;
  overflow: hidden !important;
  margin-top: 10px !important;
}

.options-accordion > button {
  background-color: rgba(10, 11, 14, 0.2) !important;
  padding: 8px 12px !important;
  font-size: 0.85rem !important;
  font-weight: normal !important;
  color: var(--text-primary) !important;
  border-radius: var(--radius-md) !important;
  border: none !important;
}

.options-accordion.open > button {
  border-bottom: 1px solid var(--border-color) !important;
  border-bottom-left-radius: 0 !important;
  border-bottom-right-radius: 0 !important;
}

.options-accordion .wrap, .options-accordion .accordion-content {
  padding: 0 !important;
  border: none !important;
}

.options-accordion .label-wrap {
  width: 100% !important;
  min-height: 38px !important;
  background: transparent !important;
  border: none !important;
  border-bottom: 1px solid var(--border-color) !important;
  color: var(--text-secondary) !important;
  border-radius: 0 !important;
  padding: 8px 12px !important;
  margin: 0 !important;
  box-shadow: none !important;
  display: flex !important;
  align-items: center !important;
}

.options-accordion .label-wrap .icon {
  display: inline-flex !important;
  align-items: center !important;
  vertical-align: middle !important;
}
.options-accordion .form > :last-child .label-wrap {
  border-bottom: none !important;
}

.options-accordion .form {
  border: none !important;
  background: transparent !important;
  padding: 0 !important;
  gap: 0 !important;
}

.pipeline-actions {
  gap: 8px !important;
}

/* CONSOLE */
.console-container {
  background-color: var(--bg-console) !important;
  border: 1px solid var(--border-color) !important;
  border-radius: var(--radius-md) !important;
  padding: 10px !important;
  font-family: "Consolas", "Courier New", monospace !important;
  font-size: 0.85rem !important;
  color: #d4d4d4 !important;
}

.console-container .wrap {
  border: none !important;
  background: transparent !important;
}

.console-container textarea {
  font-family: "Consolas", "Courier New", monospace !important;
  font-size: 0.85rem !important;
  background: transparent !important;
  border: none !important;
  color: #d4d4d4 !important;
  box-shadow: none !important;
}

.telemetry-list {
  display: flex !important;
  flex-direction: column !important;
  gap: 8px !important;
  max-height: 320px !important;
  overflow-y: auto !important;
}

.telemetry-item {
  border: 1px solid var(--border-color) !important;
  border-radius: var(--radius-sm) !important;
  padding: 8px !important;
  background: rgba(255,255,255,0.02) !important;
}

.telemetry-item.telemetry-warning {
  border-color: var(--accent-warning) !important;
}

.telemetry-item.telemetry-error {
  border-color: var(--accent-danger) !important;
}

.section-divider {
  border-top: 1px solid var(--border-color) !important;
  margin: 15px 0 !important;
}
    display: flex !important;
    align-items: center !important;
    justify-content: space-between !important;
}

.folder-path-display {
    display: flex !important;
    align-items: center !important;
    gap: 12px !important;
    color: var(--text-primary) !important;
    font-weight: 500 !important;
}

.folder-icon {
    font-size: 1.5rem !important;
}

/* ========== FOLDER TREE CONTAINER ========== */
.folder-tree-container {
    max-height: 550px !important;
    overflow-y: auto !important;
    overflow-x: hidden !important;
    background: var(--bg-secondary) !important;
    border: 1px solid var(--border-color) !important;
    border-radius: var(--radius-md) !important;
    padding: 12px !important;
}

/* Folder Tree Status Label - smaller font */
.tree-status-label .output-class {
    font-size: 0.9rem !important;
    font-weight: 400 !important;
    color: var(--text-secondary) !important;
    padding: 8px 12px !important;
}

.folder-tree-container::-webkit-scrollbar {
    width: 8px;
}

.folder-tree-container::-webkit-scrollbar-track {
    background: var(--bg-tertiary);
    border-radius: 4px;
}

.folder-tree-container::-webkit-scrollbar-thumb {
    background: var(--bg-elevated);
    border-radius: 4px;
}

.folder-tree-container::-webkit-scrollbar-thumb:hover {
    background: var(--accent-primary);
}

/* ========== HIGHLIGHTED TEXT (KEYWORDS) ========== */
/* Hide category labels (C0, C1, etc.) */
[data-testid="highlighted-text"] .label {
    display: none !important;
}

/* Hide close/cross button */
[data-testid="highlighted-text"] .label-clear-button {
    display: none !important;
}

/* White text for keyword tags */
[data-testid="highlighted-text"] .textspan {
    color: white !important;
    font-weight: 500 !important;
    padding: 4px 12px !important;
    border-radius: 6px !important;
    margin: 2px !important;
}

[data-testid="highlighted-text"] .text {
    color: white !important;
}

/* ========== STACK BADGE OVERLAY ========== */
.stack-badge {
    position: absolute;
    top: 6px;
    right: 6px;
    background: linear-gradient(135deg, #58a6ff 0%, #a371f7 100%);
    color: white;
    font-size: 11px;
    font-weight: 700;
    padding: 3px 8px;
    border-radius: 10px;
    min-width: 20px;
    text-align: center;
    box-shadow: 0 2px 8px rgba(0,0,0,0.5);
    z-index: 10;
    pointer-events: none;
    font-family: system-ui, -apple-system, sans-serif;
}

.stack-badge.large {
    background: linear-gradient(135deg, #3fb950 0%, #238636 100%);
}

/* ========== STACK INLINE PREVIEW (Hover Expand) ========== */
.stack-preview-popup {
    position: fixed;
    background: var(--bg-secondary, #161b22);
    border: 1px solid var(--border-color, #30363d);
    border-radius: 12px;
    padding: 12px;
    box-shadow: 0 8px 32px rgba(0,0,0,0.5);
    z-index: 9999;
    max-width: 400px;
    display: none;
}

.stack-preview-popup.visible {
    display: block;
    animation: fadeInScale 0.15s ease-out;
}

@keyframes fadeInScale {
    from {
        opacity: 0;
        transform: scale(0.95);
    }
    to {
        opacity: 1;
        transform: scale(1);
    }
}

.stack-preview-header {
    font-size: 13px;
    font-weight: 600;
    color: var(--text-primary, #e6edf3);
    margin-bottom: 8px;
    padding-bottom: 6px;
    border-bottom: 1px solid var(--border-subtle, #21262d);
}

.stack-preview-grid {
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: 6px;
}

.stack-preview-thumb {
    width: 80px;
    height: 80px;
    object-fit: cover;
    border-radius: 6px;
    border: 2px solid transparent;
    transition: border-color 0.15s ease;
}

.stack-preview-thumb:hover {
    border-color: var(--accent-primary, #58a6ff);
}

.stack-preview-thumb.best {
    border-color: var(--accent-success, #3fb950);
}

.stack-preview-more {
    width: 80px;
    height: 80px;
    display: flex;
    align-items: center;
    justify-content: center;
    background: var(--bg-tertiary, #21262d);
    border-radius: 6px;
    color: var(--text-secondary, #8b949e);
    font-size: 12px;
    font-weight: 500;
}

/* ========== IMAGE COMPARISON VIEW ========== */
.compare-modal {
    position: fixed !important;
    top: 0 !important;
    left: 0 !important;
    width: 100% !important;
    height: 100% !important;
    background: rgba(0, 0, 0, 0.95) !important;
    z-index: 10000 !important;
    display: flex !important;
    flex-direction: column !important;
    padding: 20px !important;
    box-sizing: border-box !important;
}

.compare-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 10px 20px;
    background: var(--bg-secondary, #161b22);
    border-radius: 10px;
    margin-bottom: 15px;
}

.compare-title {
    font-size: 1.2rem;
    font-weight: 600;
    color: var(--text-primary, #e6edf3);
}

.compare-grid {
    display: grid;
    gap: 15px;
    flex: 1;
    overflow: hidden;
}

.compare-grid.cols-2 {
    grid-template-columns: repeat(2, 1fr);
}

.compare-grid.cols-3 {
    grid-template-columns: repeat(3, 1fr);
}

.compare-grid.cols-4 {
    grid-template-columns: repeat(2, 1fr);
    grid-template-rows: repeat(2, 1fr);
}

.compare-item {
    background: var(--bg-secondary, #161b22);
    border: 1px solid var(--border-color, #30363d);
    border-radius: 10px;
    overflow: hidden;
    display: flex;
    flex-direction: column;
}

.compare-item img {
    width: 100%;
    height: calc(100% - 60px);
    object-fit: contain;
    background: var(--bg-primary, #0d1117);
}

.compare-item-info {
    padding: 10px 15px;
    background: var(--bg-tertiary, #21262d);
    color: var(--text-primary, #e6edf3);
    font-size: 0.9rem;
}

.compare-item-score {
    display: flex;
    gap: 15px;
    margin-top: 5px;
}

.compare-item-score span {
    color: var(--accent-primary, #58a6ff);
    font-weight: 600;
}

/* ========== QUICK START PANEL ========== */
.quick-start-panel {
    background: linear-gradient(135deg, rgba(0, 122, 204, 0.08) 0%, rgba(163, 113, 247, 0.06) 100%) !important;
    border: 1px solid rgba(0, 122, 204, 0.25) !important;
    border-radius: var(--radius-lg) !important;
    padding: 14px 18px !important;
    margin-bottom: 14px !important;
}

.quick-start-steps {
    display: flex !important;
    align-items: flex-start !important;
    gap: 8px !important;
    margin-top: 10px !important;
    flex-wrap: wrap !important;
}

.qs-step {
    display: flex !important;
    align-items: center !important;
    gap: 8px !important;
    padding: 8px 12px !important;
    border-radius: var(--radius-md) !important;
    font-size: 0.85rem !important;
    color: var(--text-secondary) !important;
    border: 1px solid var(--border-color) !important;
    background: var(--bg-tertiary) !important;
    transition: all var(--transition-fast) !important;
    flex: 1 !important;
    min-width: 160px !important;
}

.qs-step.current {
    border-color: var(--accent-primary) !important;
    color: var(--text-primary) !important;
    background: rgba(0, 122, 204, 0.12) !important;
    font-weight: 600 !important;
}

.qs-step.done {
    border-color: var(--accent-success) !important;
    color: var(--accent-success) !important;
    opacity: 0.7 !important;
}

.qs-step-num {
    width: 22px !important;
    height: 22px !important;
    border-radius: 50% !important;
    background: var(--bg-input) !important;
    display: flex !important;
    align-items: center !important;
    justify-content: center !important;
    font-size: 0.78rem !important;
    font-weight: bold !important;
    flex-shrink: 0 !important;
}

.qs-step.current .qs-step-num {
    background: var(--accent-primary) !important;
    color: white !important;
}

.qs-step.done .qs-step-num {
    background: var(--accent-success) !important;
    color: white !important;
}

.qs-arrow {
    color: var(--text-muted) !important;
    font-size: 0.9rem !important;
    padding-top: 8px !important;
    flex-shrink: 0 !important;
}

/* ========== CONFIRMATION ROW ========== */
.confirm-row {
    background: rgba(241, 79, 69, 0.08) !important;
    border: 1px solid rgba(241, 79, 69, 0.3) !important;
    border-radius: var(--radius-md) !important;
    padding: 10px 14px !important;
    margin-top: 6px !important;
}

.confirm-row > div {
    display: flex !important;
    align-items: center !important;
    gap: 10px !important;
    flex-wrap: wrap !important;
}

.confirm-text {
    font-size: 0.85rem !important;
    color: var(--text-secondary) !important;
    flex: 1 !important;
}

/* ========== MICROCOPY / HELPER TEXT ========== */
.action-help {
    font-size: 0.78rem !important;
    color: var(--text-muted) !important;
    margin-top: 4px !important;
    line-height: 1.4 !important;
    font-style: italic !important;
}

.section-microcopy {
    font-size: 0.82rem !important;
    color: var(--text-muted) !important;
    padding: 6px 0 2px 0 !important;
    line-height: 1.5 !important;
}

/* ========== FILTER PRESETS ========== */
.filter-preset-row {
    display: flex !important;
    gap: 6px !important;
    flex-wrap: wrap !important;
    margin-bottom: 10px !important;
    padding-bottom: 10px !important;
    border-bottom: 1px solid var(--border-color) !important;
}

.filter-preset-row > div {
    display: flex !important;
    gap: 6px !important;
    flex-wrap: wrap !important;
    align-items: center !important;
}

/* Active chips strip */
.active-chips-strip {
    display: flex !important;
    gap: 6px !important;
    flex-wrap: wrap !important;
    align-items: center !important;
    min-height: 28px !important;
    padding: 4px 0 !important;
}

.active-chip {
    display: inline-flex !important;
    align-items: center !important;
    gap: 4px !important;
    padding: 3px 10px !important;
    background: rgba(0, 122, 204, 0.18) !important;
    border: 1px solid rgba(0, 122, 204, 0.4) !important;
    border-radius: 14px !important;
    font-size: 0.78rem !important;
    color: var(--accent-hover) !important;
    font-weight: 500 !important;
}

/* ========== ACCESSIBILITY ========== */
:focus-visible {
    outline: 2px solid var(--accent-primary) !important;
    outline-offset: 2px !important;
}

.sr-only {
    position: absolute !important;
    width: 1px !important;
    height: 1px !important;
    padding: 0 !important;
    margin: -1px !important;
    overflow: hidden !important;
    clip: rect(0, 0, 0, 0) !important;
    white-space: nowrap !important;
    border: 0 !important;
}

.phase-card[role="region"]:focus-within {
    box-shadow: 0 0 0 2px var(--accent-primary) !important;
}
"""

def get_css():
    css = custom_css
    if _GRADIO_DESIGN_TOKENS.is_file():
        css += "\n" + _GRADIO_DESIGN_TOKENS.read_text(encoding="utf-8")
    return css

tree_js = r"""
<script>
/**
 * LibRaw Viewer - In-browser NEF/RAW file preview
 * 
 * Provides two modes:
 * 1. Fast embedded JPEG extraction (instant preview)
 * 2. Full RAW decode via LibRaw-WASM (on-demand)
 */

class NefViewer {
    constructor() {
        this.wasmLoaded = false;
        this.libraw = null;
    }

    /**
     * Extract embedded JPEG preview from NEF file.
     * NEF files contain a full-size JPEG preview that can be extracted quickly.
     * 
     * @param {ArrayBuffer} buffer - Raw NEF file bytes
     * @returns {Promise<Blob|null>} - JPEG blob or null if not found
     */
    async extractEmbeddedJpeg(buffer) {
        const bytes = new Uint8Array(buffer);

        // JPEG markers
        const JPEG_SOI = 0xFFD8;  // Start of Image
        const JPEG_EOI = 0xFFD9;  // End of Image

        // Search for embedded JPEG (usually after EXIF data)
        // NEF files typically have the full-size JPEG starting around offset 0x8000+
        let jpegStart = -1;
        let jpegEnd = -1;

        // Skip first 1KB (TIFF header area) and search for JPEG SOI
        for (let i = 1024; i < bytes.length - 1; i++) {
            if (bytes[i] === 0xFF && bytes[i + 1] === 0xD8) {
                // Found potential JPEG start
                // Verify it's a substantial JPEG (not just thumbnail)
                // by checking if there's enough data after it
                if (bytes.length - i > 100000) {  // At least 100KB remaining
                    jpegStart = i;
                    break;
                }
            }
        }

        if (jpegStart === -1) {
            console.log('NefViewer: No embedded JPEG found');
            return null;
        }

        // Find JPEG end marker
        for (let i = jpegStart + 2; i < bytes.length - 1; i++) {
            if (bytes[i] === 0xFF && bytes[i + 1] === 0xD9) {
                jpegEnd = i + 2;
                // Continue searching for a later EOI (could be thumbnail EOI)
            }
        }

        if (jpegEnd === -1) {
            console.log('NefViewer: JPEG end marker not found');
            return null;
        }

        // Extract JPEG bytes
        const jpegBytes = bytes.slice(jpegStart, jpegEnd);
        console.log(`NefViewer: Extracted JPEG preview (${(jpegBytes.length / 1024).toFixed(1)} KB)`);

        return new Blob([jpegBytes], { type: 'image/jpeg' });
    }

    /**
     * Load LibRaw WASM module for full RAW decoding.
     * Only loads when needed (lazy loading).
     */
    async loadWasm() {
        if (this.wasmLoaded) return true;

        try {
            // Dynamic import of libraw-wasm
            // Note: User needs to provide the WASM file
            const wasmPath = '/file=static/wasm/libraw.wasm';

            // Check if libraw-wasm is available
            if (typeof LibRaw !== 'undefined') {
                this.libraw = new LibRaw();
                await this.libraw.init(wasmPath);
                this.wasmLoaded = true;
                console.log('NefViewer: LibRaw WASM loaded');
                return true;
            } else {
                console.warn('NefViewer: LibRaw-WASM not available, using embedded JPEG only');
                return false;
            }
        } catch (e) {
            console.error('NefViewer: Failed to load WASM', e);
            return false;
        }
    }

    /**
     * Decode full RAW data using LibRaw-WASM.
     * This is computationally expensive (2-5 seconds for 45MP).
     * 
     * @param {ArrayBuffer} buffer - Raw NEF file bytes
     * @returns {Promise<ImageData|null>} - Decoded image data
     */
    async decodeRaw(buffer) {
        if (!await this.loadWasm()) {
            console.error('NefViewer: WASM not available for RAW decode');
            return null;
        }

        try {
            const result = await this.libraw.decode(new Uint8Array(buffer));
            return new ImageData(
                new Uint8ClampedArray(result.data),
                result.width,
                result.height
            );
        } catch (e) {
            console.error('NefViewer: RAW decode failed', e);
            return null;
        }
    }

    /**
     * Create an image element from a blob.
     * 
     * @param {Blob} blob - Image blob (JPEG)
     * @returns {Promise<HTMLImageElement>}
     */
    async blobToImage(blob) {
        return new Promise((resolve, reject) => {
            const img = new Image();
            img.onload = () => {
                URL.revokeObjectURL(img.src);
                resolve(img);
            };
            img.onerror = reject;
            img.src = URL.createObjectURL(blob);
        });
    }

    /**
     * Render ImageData to a canvas element.
     * 
     * @param {ImageData} imageData - Decoded RAW image data
     * @param {HTMLCanvasElement} canvas - Target canvas
     */
    renderToCanvas(imageData, canvas) {
        canvas.width = imageData.width;
        canvas.height = imageData.height;
        const ctx = canvas.getContext('2d');
        ctx.putImageData(imageData, 0, 0);
    }
}

// Global instance
window.NefViewer = new NefViewer();

/**
 * Preview a NEF file by extracting embedded JPEG.
 * Called from Gradio button click handlers.
 * 
 * @param {string} filePath - Path to NEF file
 * @param {string} targetElementId - ID of img/canvas element to render to
 */
async function previewNefFile(filePath, targetElementId) {
    const statusEl = document.getElementById('raw-preview-status');
    if (statusEl) statusEl.textContent = 'Loading...';

    try {
        // Fetch NEF file
        const response = await fetch(filePath);
        if (!response.ok) throw new Error(`Failed to fetch: ${response.status}`);

        const buffer = await response.arrayBuffer();
        console.log(`NefViewer: Loaded ${(buffer.byteLength / 1024 / 1024).toFixed(1)} MB`);

        // Try embedded JPEG extraction first (fast path)
        const jpegBlob = await window.NefViewer.extractEmbeddedJpeg(buffer);

        if (jpegBlob) {
            const img = await window.NefViewer.blobToImage(jpegBlob);
            const target = document.getElementById(targetElementId);

            if (target && target.tagName === 'IMG') {
                target.src = URL.createObjectURL(jpegBlob);
            } else if (target && target.tagName === 'CANVAS') {
                const ctx = target.getContext('2d');
                target.width = img.width;
                target.height = img.height;
                ctx.drawImage(img, 0, 0);
            }

            if (statusEl) statusEl.textContent = `Preview: ${img.width}x${img.height}`;
        } else {
            if (statusEl) statusEl.textContent = 'No embedded preview found';
        }
    } catch (e) {
        console.error('NefViewer: Preview failed', e);
        if (statusEl) statusEl.textContent = `Error: ${e.message}`;
    }
}

// Export for global access
window.previewNefFile = previewNefFile;

/**
 * Generic RAW preview handler with progress indicator.
 * Uses server-side extraction endpoint for optimized performance (faster than client-side).
 * Falls back to client-side extraction if server endpoint fails.
 * 
 * @param {string} filePath - Path to the NEF file
 * @param {HTMLElement} statusEl - Status display element
 * @param {HTMLElement} canvas - Canvas to render preview
 */
async function handleRawPreview(filePath, statusEl, canvas) {
    if (!filePath) {
        if (statusEl) statusEl.innerHTML = '<span style="color: #f85149;">❌ No file path provided. Select an image first.</span>';
        return;
    }

    // Check if NEF file (extended to support more RAW formats)
    const lowerPath = filePath.toLowerCase();
    const supportedFormats = ['.nef', '.nrw', '.cr2', '.cr3', '.arw', '.orf', '.rw2', '.dng'];
    const isRaw = supportedFormats.some(ext => lowerPath.endsWith(ext));
    
    if (!isRaw) {
        if (statusEl) statusEl.innerHTML = '<span style="color: #d29922;">⚠️ Selected file is not a supported RAW format.</span>';
        return;
    }

    const fileName = filePath.split(/[/\\]/).pop();

    // Show loading status
    if (statusEl) {
        statusEl.innerHTML = `
            <div style="color: #58a6ff; margin-bottom: 8px;">📥 Extracting preview from ${fileName}...</div>
            <div style="background: #21262d; border-radius: 4px; height: 8px; overflow: hidden;">
                <div id="nef-progress-bar" style="width: 0%; height: 100%; background: linear-gradient(90deg, #58a6ff 0%, #a371f7 100%); transition: width 0.3s ease;"></div>
            </div>
        `;
    }

    try {
        // Method 1: Try server-side extraction endpoint (fast - ~2-5MB JPEG vs 20-60MB NEF)
        const encodedPath = encodeURIComponent(filePath);
        const previewUrl = `/api/raw-preview?path=${encodedPath}`;
        
        const response = await fetch(previewUrl);
        
        if (response.ok) {
            // Server-side extraction successful
            const jpegBlob = await response.blob();
            
            if (jpegBlob && jpegBlob.size > 1000) {
                const img = await window.NefViewer.blobToImage(jpegBlob);

                if (canvas) {
                    canvas.style.display = 'block';
                    canvas.width = Math.min(img.width, 800);
                    canvas.height = (img.height / img.width) * canvas.width;
                    const ctx = canvas.getContext('2d');
                    ctx.drawImage(img, 0, 0, canvas.width, canvas.height);
                }

                if (statusEl) {
                    statusEl.innerHTML = `<span style="color: #3fb950;">✅ Preview: ${img.width}x${img.height} (${(jpegBlob.size / 1024).toFixed(0)} KB) - Server-extracted</span>`;
                }
                return; // Success, exit early
            }
        }
        
        // Method 2: Fallback to client-side extraction (if server endpoint fails)
        console.log('NefViewer: Server-side extraction failed or unavailable, falling back to client-side extraction');
        if (statusEl) {
            statusEl.innerHTML = `<span style="color: #d29922;">⚠️ Server extraction failed, trying client-side...</span>`;
        }

        // Convert WSL path to Windows path for fetch
        let fetchPath = filePath;
        if (filePath.startsWith('/mnt/')) {
            const parts = filePath.split('/');
            const driveLetter = parts[2].toUpperCase();
            const rest = parts.slice(3).join('/');
            fetchPath = `${driveLetter}:/${rest}`;
        }

        // Use Gradio's file serving endpoint
        const fileUrl = `/file=${fetchPath}`;
        
        // Fetch full file with progress tracking
        const fileResponse = await fetch(fileUrl);
        if (!fileResponse.ok) throw new Error(`HTTP ${fileResponse.status}`);

        const contentLength = fileResponse.headers.get('content-length');
        const total = parseInt(contentLength, 10) || 0;
        
        const reader = fileResponse.body.getReader();
        let receivedLength = 0;
        const chunks = [];
        const progressBar = document.getElementById('nef-progress-bar');

        while (true) {
            const { done, value } = await reader.read();
            if (done) break;
            
            chunks.push(value);
            receivedLength += value.length;
            
            if (progressBar && total > 0) {
                const percent = Math.round((receivedLength / total) * 100);
                progressBar.style.width = `${percent}%`;
            }
        }

        // Combine chunks into a single buffer
        const buffer = new Uint8Array(receivedLength);
        let position = 0;
        for (const chunk of chunks) {
            buffer.set(chunk, position);
            position += chunk.length;
        }

        const sizeMB = (buffer.byteLength / 1024 / 1024).toFixed(1);
        if (statusEl) statusEl.innerHTML = `<span style="color: #58a6ff;">🔍 Extracting preview from ${sizeMB} MB file...</span>`;

        const jpegBlob = await window.NefViewer.extractEmbeddedJpeg(buffer.buffer);

        if (jpegBlob) {
            const img = await window.NefViewer.blobToImage(jpegBlob);

            if (canvas) {
                canvas.style.display = 'block';
                canvas.width = Math.min(img.width, 800);
                canvas.height = (img.height / img.width) * canvas.width;
                const ctx = canvas.getContext('2d');
                ctx.drawImage(img, 0, 0, canvas.width, canvas.height);
            }

            if (statusEl) {
                statusEl.innerHTML = `<span style="color: #3fb950;">✅ Extracted preview: ${img.width}x${img.height} (${(jpegBlob.size / 1024).toFixed(0)} KB) - Client-extracted</span>`;
            }
        } else {
            // Fallback message with suggestions
            if (statusEl) {
                statusEl.innerHTML = `
                    <div style="color: #d29922;">⚠️ No embedded JPEG found in this RAW file.</div>
                    <div style="color: #8b949e; font-size: 0.85em; margin-top: 8px;">
                        Some RAW files may not contain embedded previews, or the format may not be supported yet.
                        The server-generated thumbnail (if available) can be used instead.
                    </div>
                `;
            }
        }
    } catch (ex) {
        console.error('NefViewer:', ex);
        if (statusEl) {
            statusEl.innerHTML = `
                <div style="color: #f85149;">❌ Error: ${ex.message}</div>
                <div style="color: #8b949e; font-size: 0.85em; margin-top: 8px;">
                    Check browser console for details. The file may be too large or inaccessible.
                </div>
            `;
        }
    }
}

/**
 * Initialize RAW preview buttons across all tabs.
 * Supports Gallery, Stacks, and Culling tabs.
 */
function initRawPreviewButtons() {
    // Configuration for each preview context
    const previewConfigs = [
        {
            buttonId: 'raw-preview-btn',
            statusId: 'raw-preview-status',
            canvasId: 'raw-preview-canvas',
            pathSource: 'textbox',  // Use hidden textbox with elem_id
            pathElementId: 'gallery-selected-path',  // Gradio element ID
            name: 'Gallery'
        },
        {
            buttonId: 'stacks-raw-preview-btn',
            statusId: 'stacks-raw-preview-status',
            canvasId: 'stacks-raw-preview-canvas',
            pathSource: 'textbox',  // Find path from nearby textbox
            name: 'Stacks'
        },
        {
            buttonId: 'cull-raw-preview-btn',
            statusId: 'cull-raw-preview-status',
            canvasId: 'cull-raw-preview-canvas',
            pathSource: 'textbox',  // Find path from nearby textbox
            name: 'Culling'
        }
    ];

    const checkInterval = setInterval(() => {
        let allInitialized = true;

        previewConfigs.forEach(config => {
            const btn = document.getElementById(config.buttonId);
            
            if (btn && !btn.hasAttribute('data-nef-initialized')) {
                btn.setAttribute('data-nef-initialized', 'true');
                
                btn.addEventListener('click', async (e) => {
                    e.preventDefault();
                    e.stopPropagation();

                    const statusEl = document.getElementById(config.statusId);
                    const canvas = document.getElementById(config.canvasId);
                    
                    let filePath = null;

                    // Find the file path based on context
                    if (config.pathSource === 'textbox') {
                        // Gallery/Stacks/Culling tab: find from textbox (Gradio state)
                        if (config.pathElementId) {
                            // Use specific element ID (Gallery tab uses hidden textbox)
                            // Gradio textboxes: try direct ID first, then look for textarea/input inside
                            let pathEl = document.getElementById(config.pathElementId);
                            if (!pathEl) {
                                // Sometimes Gradio adds prefixes, try with common prefixes
                                pathEl = document.querySelector(`[id*="${config.pathElementId}"]`);
                            }
                            if (pathEl) {
                                // For Gradio textboxes, the value is in the textarea or input element
                                const input = pathEl.querySelector('textarea, input[type="text"]') || pathEl;
                                if (input && input.value) {
                                    filePath = input.value;
                                } else if (pathEl.value) {
                                    // Sometimes the element itself has the value
                                    filePath = pathEl.value;
                                }
                            }
                        }
                        
                        // Fallback: find from nearby textbox (Stacks/Culling tabs)
                        if (!filePath) {
                            // Stacks/Culling tab: find from Gradio textbox near the button
                            // Look for textarea with the selected path value
                            const accordion = btn.closest('.accordion');
                            if (accordion) {
                                const textareas = accordion.querySelectorAll('textarea');
                                textareas.forEach(ta => {
                                    if (ta.value && (ta.value.includes('\\') || ta.value.includes('/'))) {
                                        filePath = ta.value;
                                    }
                                });
                            }
                            
                            // Fallback: try finding by looking at nearby input elements
                            if (!filePath) {
                                const row = btn.closest('.row');
                                if (row) {
                                    const textareas = row.querySelectorAll('textarea');
                                    textareas.forEach(ta => {
                                        if (ta.value && (ta.value.includes('\\') || ta.value.includes('/'))) {
                                            filePath = ta.value;
                                        }
                                    });
                                }
                            }
                        }
                    }

                    await handleRawPreview(filePath, statusEl, canvas);
                });

                console.log(`NefViewer: ${config.name} preview button initialized`);
            } else if (!btn) {
                allInitialized = false;
            }
        });

        // Stop checking once all buttons are initialized (or after timeout)
        if (allInitialized) {
            clearInterval(checkInterval);
        }
    }, 1000);

    // Stop checking after 30 seconds
    setTimeout(() => clearInterval(checkInterval), 30000);
}

// Initialize when DOM is ready
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initRawPreviewButtons);
} else {
    initRawPreviewButtons();
}

console.log('NefViewer: Module loaded');

window.selectFolder = function(e, path) {
    e.preventDefault();
    e.stopPropagation();
    
    // Clear selection style
    var all = document.querySelectorAll('.tree-content');
    for (var i=0; i<all.length; i++) {
        all[i].style.backgroundColor = '';
        all[i].style.color = '';
    }
    
    // Set new style
    e.target.style.backgroundColor = '#2196f3';
    e.target.style.color = 'white';
    
    // Update hidden input (Gradio may add suffixes to elem_id)
    var container = document.getElementById('folder_tree_selection') || document.querySelector('[id*="folder_tree_selection"]');
    var ta = container ? container.querySelector('textarea') : null;
    if (ta) {
        var descriptor = Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype, "value");
        descriptor.set.call(ta, path);
        ta.dispatchEvent(new Event('input', { bubbles: true }));
    }
}

// Gallery lightbox close button handler
function initGalleryCloseButton() {
    let closeBtn = null;
    
    function createCloseButton() {
        if (closeBtn && document.body.contains(closeBtn)) return closeBtn;
        
        closeBtn = document.createElement('button');
        closeBtn.id = 'gallery-close-btn';
        closeBtn.innerHTML = '✕ Back to Grid';
        closeBtn.style.cssText = `
            position: fixed;
            top: 15px;
            right: 15px;
            z-index: 99999;
            background: linear-gradient(135deg, #f85149 0%, #da3633 100%);
            color: white;
            padding: 14px 28px;
            border-radius: 10px;
            font-size: 15px;
            font-weight: 700;
            cursor: pointer;
            box-shadow: 0 4px 20px rgba(248, 81, 73, 0.5);
            border: 2px solid rgba(255,255,255,0.2);
            transition: all 0.2s ease;
            font-family: system-ui, -apple-system, sans-serif;
            letter-spacing: 0.5px;
        `;
        closeBtn.onmouseenter = function() {
            this.style.transform = 'scale(1.08)';
            this.style.boxShadow = '0 6px 25px rgba(248, 81, 73, 0.7)';
        };
        closeBtn.onmouseleave = function() {
            this.style.transform = 'scale(1)';
            this.style.boxShadow = '0 4px 20px rgba(248, 81, 73, 0.5)';
        };
        closeBtn.onclick = function(e) {
            e.preventDefault();
            e.stopPropagation();
            closePreview();
        };
        return closeBtn;
    }
    
    function closePreview() {
        // Method 1: Find and click the grid/thumbnail view
        const gridButtons = document.querySelectorAll('.gallery button, .gallery .thumbnail, .gallery [class*="grid"]');
        
        // Method 2: Simulate Escape key
        document.dispatchEvent(new KeyboardEvent('keydown', { 
            key: 'Escape', 
            code: 'Escape', 
            keyCode: 27, 
            which: 27, 
            bubbles: true,
            cancelable: true
        }));
        
        // Method 3: Find preview container and trigger close
        const previewBtn = document.querySelector('.gallery button.preview');
        if (previewBtn) {
            // Try to find a close mechanism
            const svgIcons = previewBtn.querySelectorAll('svg');
            svgIcons.forEach(svg => {
                if (svg.closest('button')) {
                    svg.closest('button').click();
                }
            });
        }
        
        // Method 4: Click on the preview backdrop area
        setTimeout(() => {
            const preview = document.querySelector('.gallery .preview, .gallery button.preview');
            if (preview) {
                // Dispatch escape again
                preview.dispatchEvent(new KeyboardEvent('keydown', { 
                    key: 'Escape', 
                    bubbles: true 
                }));
            }
            removeCloseButton();
        }, 100);
    }
    
    function removeCloseButton() {
        const btn = document.getElementById('gallery-close-btn');
        if (btn) btn.remove();
        closeBtn = null;
    }
    
    function checkForPreviewMode() {
        // Check if gallery is in preview/lightbox mode
        const previewActive = document.querySelector('.gallery button.preview');
        const hasLargeImage = document.querySelector('.gallery .preview img, .gallery button.preview img');
        const thumbnailStrip = document.querySelector('.gallery .thumbnails, .gallery [class*="thumbnail"]');
        
        // If preview mode detected (large image with thumbnail strip)
        if (previewActive || (hasLargeImage && thumbnailStrip)) {
            if (!document.getElementById('gallery-close-btn')) {
                const btn = createCloseButton();
                document.body.appendChild(btn);
            }
        } else {
            removeCloseButton();
        }
    }
    
    // Watch for DOM changes
    const observer = new MutationObserver(function(mutations) {
        checkForPreviewMode();
    });
    
    observer.observe(document.body, { 
        childList: true, 
        subtree: true, 
        attributes: true,
        attributeFilter: ['class', 'style']
    });
    
    // Also check periodically for edge cases
    setInterval(checkForPreviewMode, 500);
    
    // Initial check
    setTimeout(checkForPreviewMode, 1000);
}

// Handle Escape key globally
document.addEventListener('keydown', function(e) {
    if (e.key === 'Escape') {
        const btn = document.getElementById('gallery-close-btn');
        if (btn) btn.remove();
    }
});

// Initialize when DOM is ready
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initGalleryCloseButton);
} else {
    initGalleryCloseButton();
}

// ========== STACK BADGE OVERLAY ==========
function initStackBadges() {
    function addBadgesToStackGallery() {
        // Find the Stacks tab gallery (first gallery in the Stacks tab)
        const stacksTab = document.querySelector('[id*="stacks"]');
        if (!stacksTab) return;
        
        // Find all gallery items in the stacks section
        const galleries = document.querySelectorAll('.gallery');
        
        galleries.forEach(gallery => {
            // Look for stack gallery items (they have captions with "X imgs")
            const items = gallery.querySelectorAll('.thumbnail-item, .gallery-item, [class*="thumbnail"]');
            
            items.forEach(item => {
                // Skip if already has badge
                if (item.querySelector('.stack-badge')) return;
                
                // Get the caption/label
                const caption = item.querySelector('.caption, .label, [class*="caption"]');
                if (!caption) return;
                
                const text = caption.textContent || '';
                // Match pattern like "(5 imgs)" or "(12 imgs)"
                const match = text.match(/\((\d+)\s*imgs?\)/i);
                
                if (match) {
                    const count = parseInt(match[1], 10);
                    if (count >= 2) {
                        // Make item position relative if not already
                        const computed = window.getComputedStyle(item);
                        if (computed.position === 'static') {
                            item.style.position = 'relative';
                        }
                        
                        // Create and add badge
                        const badge = document.createElement('span');
                        badge.className = 'stack-badge' + (count >= 10 ? ' large' : '');
                        badge.textContent = count;
                        item.appendChild(badge);
                    }
                }
            });
        });
    }
    
    // Watch for DOM changes (galleries update dynamically)
    const badgeObserver = new MutationObserver(function(mutations) {
        // Debounce
        clearTimeout(window._stackBadgeTimeout);
        window._stackBadgeTimeout = setTimeout(addBadgesToStackGallery, 200);
    });
    
    badgeObserver.observe(document.body, { 
        childList: true, 
        subtree: true 
    });
    
    // Initial run
    setTimeout(addBadgesToStackGallery, 1000);
    
    // Also run on tab changes
    document.addEventListener('click', function(e) {
        if (e.target.closest('[role="tab"]')) {
            setTimeout(addBadgesToStackGallery, 300);
        }
    });
}

// Initialize stack badges
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initStackBadges);
} else {
    initStackBadges();
}

// ========== KEYBOARD SHORTCUTS FOR STACK OPERATIONS ==========
function initStackKeyboardShortcuts() {
    document.addEventListener('keydown', function(e) {
        // Only trigger if no input/textarea is focused
        const activeEl = document.activeElement;
        if (activeEl && (activeEl.tagName === 'INPUT' || activeEl.tagName === 'TEXTAREA')) {
            return;
        }
        
        // Ctrl+G -> Group Selected
        if (e.ctrlKey && !e.shiftKey && e.key.toLowerCase() === 'g') {
            e.preventDefault();
            const groupBtn = document.getElementById('stack-group-btn');
            if (groupBtn) {
                groupBtn.click();
                console.log('Keyboard: Ctrl+G -> Group Selected');
            }
        }
        
        // Ctrl+Shift+G -> Ungroup All
        if (e.ctrlKey && e.shiftKey && e.key.toLowerCase() === 'g') {
            e.preventDefault();
            const ungroupBtn = document.getElementById('stack-ungroup-btn');
            if (ungroupBtn) {
                ungroupBtn.click();
                console.log('Keyboard: Ctrl+Shift+G -> Ungroup All');
            }
        }
        
        // Ctrl+R -> Remove from Stack
        if (e.ctrlKey && !e.shiftKey && e.key.toLowerCase() === 'r') {
            // Check if we're on stacks tab to avoid conflicts
            const stacksTab = document.querySelector('[id*="stacks"].tabitem--selected, [id*="stacks"][aria-selected="true"]');
            if (stacksTab) {
                e.preventDefault();
                const removeBtn = document.getElementById('stack-remove-btn');
                if (removeBtn) {
                    removeBtn.click();
                    console.log('Keyboard: Ctrl+R -> Remove from Stack');
                }
            }
        }
    });
    
    console.log('Stack keyboard shortcuts initialized: Ctrl+G (Group), Ctrl+Shift+G (Ungroup), Ctrl+R (Remove)');
}

// Initialize keyboard shortcuts
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initStackKeyboardShortcuts);
} else {
    initStackKeyboardShortcuts();
}

// ========== STACK INLINE EXPAND/COLLAPSE ==========
function initStackExpandCollapse() {
    let currentExpandedStack = null;
    
    // Add visual feedback for expand/collapse state
    function updateExpandState() {
        const stacksTab = document.querySelector('[id*="stacks"]');
        if (!stacksTab) return;
        
        // Find the content gallery section
        const contentSection = stacksTab.querySelector('[id*="stack"][class*="gallery"]');
        const stackItems = stacksTab.querySelectorAll('.gallery .thumbnail-item, .gallery .gallery-item, .gallery [class*="thumbnail"]');
        
        // Add expand indicator to stack items
        stackItems.forEach((item, index) => {
            if (item.querySelector('.expand-indicator')) return;
            
            const indicator = document.createElement('span');
            indicator.className = 'expand-indicator';
            indicator.style.cssText = `
                position: absolute;
                bottom: 6px;
                left: 6px;
                font-size: 14px;
                opacity: 0.7;
                pointer-events: none;
                transition: transform 0.2s ease;
            `;
            indicator.textContent = '▼';
            
            const computed = window.getComputedStyle(item);
            if (computed.position === 'static') {
                item.style.position = 'relative';
            }
            item.appendChild(indicator);
        });
    }
    
    // Create collapse button for content gallery
    function addCollapseButton() {
        const stacksTab = document.querySelector('[id*="stacks"]');
        if (!stacksTab) return;
        
        // Find the content gallery header
        const contentHeaders = stacksTab.querySelectorAll('h3, .markdown');
        contentHeaders.forEach(header => {
            if (header.textContent.includes('Stack Contents') && !header.querySelector('.collapse-btn')) {
                const btn = document.createElement('button');
                btn.className = 'collapse-btn';
                btn.innerHTML = '▲ Collapse';
                btn.style.cssText = `
                    margin-left: 10px;
                    padding: 4px 12px;
                    font-size: 11px;
                    background: var(--bg-tertiary, #21262d);
                    border: 1px solid var(--border-color, #30363d);
                    border-radius: 6px;
                    color: var(--text-secondary, #8b949e);
                    cursor: pointer;
                    vertical-align: middle;
                `;
                btn.onclick = function(e) {
                    e.preventDefault();
                    const gallery = this.closest('[id*="stacks"]').querySelector('.gallery:not(:first-child)');
                    if (gallery) {
                        const isCollapsed = gallery.style.display === 'none';
                        gallery.style.display = isCollapsed ? '' : 'none';
                        this.innerHTML = isCollapsed ? '▲ Collapse' : '▼ Expand';
                    }
                };
                header.appendChild(btn);
            }
        });
    }
    
    // Observe DOM changes
    const expandObserver = new MutationObserver(function() {
        clearTimeout(window._expandTimeout);
        window._expandTimeout = setTimeout(() => {
            updateExpandState();
            addCollapseButton();
        }, 300);
    });
    
    expandObserver.observe(document.body, { childList: true, subtree: true });
    
    // Initial setup
    setTimeout(() => {
        updateExpandState();
        addCollapseButton();
    }, 1500);
}

// Initialize expand/collapse
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initStackExpandCollapse);
} else {
    initStackExpandCollapse();
}

// ========== IMAGE COMPARISON VIEW ==========
window.compareImages = [];
window.maxCompareImages = 4;

function initCompareMode() {
    // Add compare button to image details
    const addBtn = document.getElementById('compare-add-btn');
    if (addBtn && !addBtn.hasAttribute('data-compare-init')) {
        addBtn.setAttribute('data-compare-init', 'true');
        addBtn.addEventListener('click', function(e) {
            e.preventDefault();
            e.stopPropagation();
            
            // Get current image path from JSON details
            let imagePath = null;
            const jsonElements = document.querySelectorAll('.json-holder pre, [data-testid="json"] pre');
            jsonElements.forEach(el => {
                try {
                    const data = JSON.parse(el.textContent);
                    if (data && data.file_path) {
                        imagePath = data.file_path;
                    }
                } catch (ex) {}
            });
            
            if (!imagePath) {
                alert('Select an image first');
                return;
            }
            
            // Add to compare list (max 4)
            if (window.compareImages.length >= window.maxCompareImages) {
                window.compareImages.shift(); // Remove oldest
            }
            
            if (!window.compareImages.includes(imagePath)) {
                window.compareImages.push(imagePath);
            }
            
            // Show visual feedback
            const count = window.compareImages.length;
            this.textContent = `📊 Compare (${count}/${window.maxCompareImages})`;
            
            if (count >= 2) {
                showCompareView();
            }
        });
    }
}

function showCompareView() {
    if (window.compareImages.length < 2) {
        alert('Add at least 2 images to compare');
        return;
    }
    
    // Create modal
    const modal = document.createElement('div');
    modal.className = 'compare-modal';
    modal.innerHTML = `
        <div class="compare-header">
            <span class="compare-title">📊 Image Comparison (${window.compareImages.length} images)</span>
            <button onclick="closeCompareView()" style="background: #f85149; border: none; color: white; padding: 8px 16px; border-radius: 6px; cursor: pointer; font-weight: 600;">✕ Close</button>
        </div>
        <div class="compare-grid cols-${Math.min(window.compareImages.length, 4)}">
            ${window.compareImages.map((path, i) => `
                <div class="compare-item">
                    <img src="/file=${path.replace(/\\\\/g, '/')}" alt="Image ${i+1}">
                    <div class="compare-item-info">
                        <strong>${path.split(/[/\\\\]/).pop()}</strong>
                    </div>
                </div>
            `).join('')}
        </div>
    `;
    
    document.body.appendChild(modal);
}

function closeCompareView() {
    const modal = document.querySelector('.compare-modal');
    if (modal) {
        modal.remove();
    }
    window.compareImages = [];
    
    // Reset button text
    const addBtn = document.getElementById('compare-add-btn');
    if (addBtn) {
        addBtn.textContent = '📊 Add to Compare';
    }
}

// Initialize compare mode
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initCompareMode);
} else {
    initCompareMode();
}

// Re-init on DOM changes (Gradio rerenders)
const compareObserver = new MutationObserver(() => {
    clearTimeout(window._compareInitTimeout);
    window._compareInitTimeout = setTimeout(initCompareMode, 500);
});
compareObserver.observe(document.body, { childList: true, subtree: true });

// ========== LAZY LOAD FULL RESOLUTION ==========
// Global variable to store currently selected image path
window.currentSelectedImagePath = null;
// Global variable to store gallery paths array (raw_paths from server)
window.galleryPaths = [];

// Intercept gallery image clicks to store the selected path
function initGalleryPathTracking() {
    // Watch for gallery updates to store paths array
    // This is called when gallery.select fires - we can't intercept it directly,
    // but we can watch for when preview opens and try to extract from DOM
    
    // Also listen for clicks on gallery images
    document.addEventListener('click', function(e) {
        const galleryItem = e.target.closest('.gallery img, .gallery-item, [class*="gallery-item"]');
        if (galleryItem && !e.target.closest('button')) {
            // Find the image element
            const img = galleryItem.tagName === 'IMG' ? galleryItem : galleryItem.querySelector('img');
            if (img && img.src) {
                // Extract index from gallery structure
                const galleryContainer = galleryItem.closest('.gallery');
                if (galleryContainer) {
                    const allItems = galleryContainer.querySelectorAll('img, [class*="gallery-item"] img');
                    const index = Array.from(allItems).indexOf(img);
                    // Path will be populated by display_details, which we'll watch for
                }
            }
        }
    }, true);
}

function initLazyFullResolution() {
    console.log("Initializing Lazy Full Resolution Loader");
    let currentPreviewId = 0;
    let loadTimeout = null;
    let abortController = null;
    let previousObjectURL = null;  // Track ObjectURL for cleanup
    const LOAD_DELAY_MS = 100;  // Wait 100ms before loading full res (snappy but debounced)
    
    // Find the preview image element
    function getCurrentPreviewImg() {
        // Gradio 3/4 structure vary, check multiple selectors
        return document.querySelector('.gallery .preview img, .gallery button.preview img, img.preview-image');
    }
    
    // Show a subtle loading indicator
    function showLoadingIndicator(img) {
        if (!img || img.parentNode.querySelector('.full-res-loader')) return;
        
        const loader = document.createElement('div');
        loader.className = 'full-res-loader';
        loader.innerHTML = `
            <div style="
                position: absolute; 
                top: 50%; 
                left: 50%; 
                transform: translate(-50%, -50%);
                background: rgba(0,0,0,0.6);
                color: white;
                padding: 8px 16px;
                border-radius: 20px;
                font-size: 13px;
                pointer-events: none;
                z-index: 10;
                backdrop-filter: blur(4px);
                border: 1px solid rgba(255,255,255,0.1);
                display: flex;
                align-items: center;
                gap: 8px;
            ">
                <div class="spinner" style="
                    width: 14px; 
                    height: 14px; 
                    border: 2px solid rgba(255,255,255,0.3); 
                    border-top: 2px solid white; 
                    border-radius: 50%;
                    animation: spin 1s linear infinite;
                "></div>
                <span>Loading Full Res...</span>
            </div>
            <style>@keyframes spin { 0% { transform: rotate(0deg); } 100% { transform: rotate(360deg); } }</style>
        `;
        
        // Position relative to parent if needed
        if (getComputedStyle(img.parentNode).position === 'static') {
            img.parentNode.style.position = 'relative';
        }
        
        img.parentNode.appendChild(loader);
    }
    
    function hideLoadingIndicator(img) {
        if (!img) return;
        const loader = img.parentNode.querySelector('.full-res-loader');
        if (loader) loader.remove();
    }
    
    // BETTER APPROACH: Use the selected gallery item data
    // Helper function to extract file path from Gradio thumbnail/preview src URL
    function extractPathFromSrc(src) {
        if (!src) return null;
        
        // Gradio serves files via /file=<path> or /api/file=<path>
        // Example: http://localhost:7860/file=/mnt/d/Photos/.../image.NEF
        const fileMatch = src.match(/\/file=([^?&#]+)/);
        if (fileMatch) {
            const path = decodeURIComponent(fileMatch[1]);
            // Validate it looks like an image path
            if (path.match(/\.(nef|nrw|jpg|jpeg|png|tif|tiff|cr2|cr3|arw|orf|rw2|dng)$/i)) {
                return path;
            }
        }
        
        // Also try /api/... pattern
        const apiMatch = src.match(/\/api\/.*?([\/\\][^?&#]+\.(nef|nrw|jpg|jpeg|png|tif|tiff|cr2|cr3|arw|orf|rw2|dng))/i);
        if (apiMatch) {
            return decodeURIComponent(apiMatch[1]);
        }
        
        return null;
    }
    
    function getSelectedImagePath() {
        
        // Helper function to validate if string is actually a file path
        function isValidPath(path) {
            if (!path || !path.trim()) return false;
            const trimmed = path.trim();
            
            // Reject temp paths
            if (trimmed.includes('/tmp/gradio/')) return false;
            
            // Must look like a file path (contains slashes or drive letter, and has file extension)
            const hasPathSeparator = trimmed.includes('/') || trimmed.includes('\\');
            const hasDriveLetter = /^[a-zA-Z]:/.test(trimmed);
            const hasMntPath = trimmed.startsWith('/mnt/');
            const hasFileExtension = /\.[a-zA-Z0-9]{2,4}$/i.test(trimmed);
            
            // Must satisfy: (has path separator OR drive letter OR /mnt/) AND has file extension
            return (hasPathSeparator || hasDriveLetter || hasMntPath) && hasFileExtension && trimmed.length > 5;
        }
        
        // PRIORITY 0: Check global variable (populated when preview opens)
        if (window.currentSelectedImagePath && isValidPath(window.currentSelectedImagePath)) {
            return window.currentSelectedImagePath;
        }
        
        // PRIORITY 1: Check all textboxes in details panel area for path
        // Try multiple ways to find the textbox (Gradio may prefix/modify IDs)
        let pathTextBox = document.getElementById('gallery-selected-path');
        
        // Try querySelector with partial ID match (Gradio might add prefixes)
        if (!pathTextBox) {
            pathTextBox = document.querySelector('[id*="gallery-selected-path"]');
        }
        
        // Try finding ALL textboxes in details panel (not just hidden ones)
        if (!pathTextBox) {
            const detailsPanel = document.querySelector('.details-panel, [class*="details"]');
            if (detailsPanel) {
                const allTextboxes = detailsPanel.querySelectorAll('textarea, input[type="text"]');
                // Collect all values for logging
                for (const tb of allTextboxes) {
                    const val = tb.value || tb.textContent || '';
                    if (isValidPath(val)) {
                        pathTextBox = tb;
                        break;
                    }
                }
            }
        }
        
        // Also try finding all textboxes (hidden or visible) anywhere in the document
        if (!pathTextBox) {
            const allTextboxes = document.querySelectorAll('textarea, input[type="text"]');
            for (const tb of allTextboxes) {
                const val = tb.value || tb.textContent || '';
                if (isValidPath(val)) {
                    pathTextBox = tb;
                    break;
                }
            }
        }
        
        if (pathTextBox) {
            // For Gradio textboxes, value might be in textarea/input child or on element itself
            const input = pathTextBox.querySelector('textarea, input[type="text"]') || pathTextBox;
            const value = input.value || input.textContent || '';
            
            if (isValidPath(value)) {
                return value.trim();
            }
        }
        
        // PRIORITY 2: Try to find the file path from the details panel JSON (also contains original DB path)
        const jsonElements = document.querySelectorAll('.json-holder pre, [data-testid="json"] pre');
        for (const el of jsonElements) {
            try {
                const data = JSON.parse(el.textContent);
                if (data && data.file_path && isValidPath(data.file_path)) {
                    return data.file_path;
                }
            } catch (e) {}
        }
        
        
        // Fallback: Try to match preview image to gallery item to get index, then extract path
        // Find the currently previewed image
        const previewImg = document.querySelector('.gallery .preview img, img.preview-image');
        if (previewImg && previewImg.src) {
            // Try to find the gallery item that matches this preview image
            const galleryItems = document.querySelectorAll('.gallery img, .gallery-item img, [class*="gallery"] img');
            // Try to match by thumbnail strip item (Gradio shows selected item in strip)
            const thumbnailStrip = document.querySelector('.gallery .thumbnails, .gallery [class*="thumbnail"]');
            if (thumbnailStrip) {
                const selectedThumb = thumbnailStrip.querySelector('.selected, [class*="selected"], [class*="active"]') || 
                                    thumbnailStrip.querySelector('img[src*="' + previewImg.src.split('/').pop() + '"]')?.closest('div, li, span');
                if (selectedThumb) {
                    // Try to get index from data attribute or position
                    const thumbIndex = selectedThumb.dataset.index || Array.from(thumbnailStrip.children).indexOf(selectedThumb);
                }
            }
        }
        
        return null;
    }
    
    function loadFullResolution(imgPath, previewId, imgElement) {
        console.log(`[FullRes] Loading: ${imgPath} (ID: ${previewId})`);
        
        // If previewId changed, check if we are still viewing the same image
        if (previewId !== currentPreviewId) {
            const currentPath = getSelectedImagePath();
            if (imgPath === currentPath) {
                 console.log(`[FullRes] ID changed (${previewId} vs ${currentPreviewId}) but path matches, proceeding.`);
            } else {
                 console.log(`[FullRes] Stale ID and path mismatch (Target: ${imgPath}, Curr: ${currentPath}), aborting`);
                 return;
            }
        }
        
        // Cleanup previous ObjectURL if it exists (legacy cleanup)
        if (previousObjectURL) {
            URL.revokeObjectURL(previousObjectURL);
            previousObjectURL = null;
        }
        
        // Use the /source-image endpoint (not /api/ to avoid Gradio routing conflicts)
        // Handles both RAW and regular images with proper WSL path conversion
        const url = `/source-image?path=${encodeURIComponent(imgPath)}`;
        console.log(`[FullRes] Setting src to: ${url}`);
        
        showLoadingIndicator(imgElement);
        
        // Set up event handlers before setting src
        imgElement.onload = () => {
            console.log(`[FullRes] OnLoad fired for ID: ${previewId}`);
            
            // Check concurrency again with same relaxed logic
            if (previewId !== currentPreviewId) {
                const currentPath = getSelectedImagePath();
                if (imgPath !== currentPath) {
                    console.log(`[FullRes] OnLoad stale: user moved to new image (${currentPath}), ignoring.`);
                     hideLoadingIndicator(imgElement); // Ensure spinner is gone
                    return;
                }
                 console.log(`[FullRes] OnLoad ID mistmatch but path OK`);
            }
            
            hideLoadingIndicator(imgElement);
            imgElement.dataset.fullResLoaded = 'true';
            imgElement.dataset.fullResPath = imgPath;
            console.log(`[FullRes] Success, spinner hidden`);
        };
        
        imgElement.onerror = (e) => {
            console.error('[FullRes] OnError fired:', e);
            hideLoadingIndicator(imgElement);
            // Don't set fullResLoaded so we can retry if needed
        };
        
        // Direct assignment - lets browser handle caching and connection
        imgElement.src = url;
    }
    
    function handlePreviewChange() {
        const img = getCurrentPreviewImg();
        
        // If no preview image, we might be in grid mode.
        if (!img) {
            // Cancel any pending
            if (loadTimeout) clearTimeout(loadTimeout);
            if (abortController) abortController.abort();
            
            // Cleanup previous ObjectURL
            if (previousObjectURL) {
                URL.revokeObjectURL(previousObjectURL);
                previousObjectURL = null;
            }
            
            currentPreviewId++;
            window.currentSelectedImagePath = null; // Clear global path when preview closes
            return;
        }
        
        // DETECT NAVIGATION: Check if the underlying src is back to a thumbnail
        // If the src is NOT our blob/source-image, but we thought we loaded it, reset state.
        const isHighRes = img.src.startsWith('blob:') || img.src.includes('/source-image');
        
        if (!isHighRes && img.dataset.fullResLoaded === 'true') {
             // We navigated to a new image (Gradio reset the src)
             img.dataset.fullResLoaded = 'false';
             delete img.dataset.fullResPath;
        }

        // RETRY LOGIC: The path textbox might be stale immediately after navigation.
        // We need to poll until we get a path that makes sense or timeout.
        
        let attempts = 0;
        const checkPathAndLoad = () => {
             // Retrieve path
            let path = getSelectedImagePath();
            
            
            // CRITICAL FIX: During arrow key navigation, Gradio does NOT fire gallery.select() event,
            // so the path textbox is NEVER updated. We must extract path from the thumbnail src itself.
            if (!path || (img.dataset.lastLoadedPath === path && !isHighRes)) {
                // Try to extract path from the current image src
                // Gradio thumbnail URLs have format: /file=<path> or /api/...<path>
                const srcPath = extractPathFromSrc(img.src);
                
                if (srcPath && srcPath !== path) {
                    path = srcPath;
                    console.log('Extracted path from img src:', path);
                }
            }
            
            // If still no path after 5 attempts, give up
            if (!path) {
                if (attempts < 5) {
                     attempts++;
                     setTimeout(checkPathAndLoad, 150);
                }
                return;
            }
            
             // Check if we already loaded this path for this session?
            if (img.dataset.fullResPath === path && (isHighRes || img.dataset.fullResLoaded === 'true')) {
                 return; // Already initiated or loaded
            }
            
            // New image detected!
            currentPreviewId++;
            const myPreviewId = currentPreviewId;
            
            img.dataset.fullResPath = path; // Mark as handled
            img.dataset.lastLoadedPath = path; // Track for stale check
            
            // Cancel previous
            if (loadTimeout) clearTimeout(loadTimeout);
            if (abortController) abortController.abort();
            
            // Cleanup previous ObjectURL (if we are switching faster than load completes)
            if (previousObjectURL) {
                URL.revokeObjectURL(previousObjectURL);
                previousObjectURL = null;
            }
            
            // Set delay
            loadTimeout = setTimeout(() => {
                loadFullResolution(path, myPreviewId, img);
            }, LOAD_DELAY_MS);
        };
        
        checkPathAndLoad();
    }
    
    // Intercept fullscreen button clicks to load source image
    function interceptFullscreenButton() {
        // Find fullscreen buttons in gallery preview
        document.addEventListener('click', function(e) {
            // Check if click is on fullscreen button or its SVG/path child
            const fullscreenBtn = e.target.closest('button[aria-label="Fullscreen"], button[title="Fullscreen"]') ||
                                 e.target.closest('button.icon-button')?.querySelector('svg[viewBox*="24"]')?.closest('button') ||
                                 (e.target.closest('button') && e.target.closest('button').querySelector('svg')?.innerHTML.includes('maximize'));
            
            if (!fullscreenBtn) {
                // Also check SVG path for maximize icon
                const svg = e.target.closest('svg');
                if (svg && svg.parentElement?.closest('button')) {
                    const btn = svg.parentElement.closest('button');
                    if (btn && (btn.getAttribute('aria-label') === 'Fullscreen' || btn.getAttribute('title') === 'Fullscreen')) {
                        // This is a fullscreen button
                        handleFullscreenClick(btn, e);
                    }
                }
                return;
            }
            
            handleFullscreenClick(fullscreenBtn, e);
        }, true);  // Use capture phase to catch early
        
        function handleFullscreenClick(btn, e) {
            
            // Check if we're in a gallery preview context
            const galleryPreview = btn.closest('.gallery') || btn.closest('[class*="preview"]') || document.querySelector('.gallery');
            if (!galleryPreview) return;
            
            // Get the source image path
            const imgPath = getSelectedImagePath();
            if (!imgPath) {
                console.log('Fullscreen: No image path found');
                return;
            }
            
            console.log('Fullscreen button clicked, path:', imgPath);
            
            // Cancel any pending lazy load
            if (loadTimeout) clearTimeout(loadTimeout);
            if (abortController) abortController.abort();
            
            // Immediately load source image when fullscreen is clicked
            currentPreviewId++;
            const myPreviewId = currentPreviewId;
            
            // Watch for fullscreen modal to appear and replace image
            function waitForFullscreenModal(attemptNum = 0) {
                
                // Try multiple selectors for fullscreen modal
                const selectors = [
                    '.gallery .preview img',
                    'img.preview-image',
                    '.modal img',
                    '[role="dialog"] img',
                    '.gallery img[src*="/file="]',
                    '.gallery img[src*="/api/"]',
                    'img[data-testid="detailed-image"]'
                ];
                
                let fullscreenImg = null;
                let matchedSelector = null;
                for (const selector of selectors) {
                    const found = document.querySelector(selector);
                    if (found) {
                        fullscreenImg = found;
                        matchedSelector = selector;
                        break;
                    }
                }
                
                
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
        }
    }
    
    // NEW APPROACH: Monitor image src changes directly in the gallery
    // This is more reliable than trying to detect preview state
    let monitoredImages = new WeakSet();
    let lastProcessedSrc = null;
    
    function monitorImageElement(img) {
        if (!img || monitoredImages.has(img)) return;
        monitoredImages.add(img);
        
        // Create observer for this specific image
        const imgObserver = new MutationObserver((mutations) => {
            mutations.forEach(mutation => {
                if (mutation.type === 'attributes' && mutation.attributeName === 'src') {
                    const newSrc = img.src;
                    
                    // Skip if this is the same src we just processed
                    if (newSrc === lastProcessedSrc) return;
                    
                    lastProcessedSrc = newSrc;
                    handlePreviewChange();
                }
            });
        });
        
        imgObserver.observe(img, { attributes: true, attributeFilter: ['src'] });
    }
    
    // Watch for new gallery images being added to DOM
    const observer = new MutationObserver((mutations) => {
        mutations.forEach(mutation => {
            mutation.addedNodes.forEach(node => {
                if (node.nodeType === 1) {
                    // Check if this node is an image in the gallery
                    if (node.tagName === 'IMG') {
                        const inGallery = node.closest('.gallery, [class*="gallery"]');
                        if (inGallery) {
                            monitorImageElement(node);
                        }
                    }
                    
                    // Also check child images
                    const imgs = node.querySelectorAll ? node.querySelectorAll('img') : [];
                    imgs.forEach(img => {
                        const inGallery = img.closest('.gallery, [class*="gallery"]');
                        if (inGallery) {
                            monitorImageElement(img);
                        }
                    });
                }
            });
        });
        
        // Also monitor existing images on each mutation batch
        const galleryImgs = document.querySelectorAll('.gallery img, [class*="gallery"] img');
        galleryImgs.forEach(img => monitorImageElement(img));
    });
    
    observer.observe(document.body, { childList: true, subtree: true });
    
    // Also intercept fullscreen button clicks
    interceptFullscreenButton();

    // Add keyboard navigation for fullscreen/preview mode
    document.addEventListener('keydown', (e) => {
        // Only if we are in preview mode
        const previewImg = document.querySelector('.gallery .preview img, .gallery button.preview img, img.preview-image');
        if (!previewImg) return;

        if (e.key === 'ArrowRight') {
            // Find "Next" button in gallery and click it
            const nextBtns = document.querySelectorAll('.gallery button[aria-label="Next"], .gallery button.next-btn, .gallery button[title="Next"]');
            for (const btn of nextBtns) {
                if (btn.offsetParent !== null) { // Visible
                    btn.click();
                    break;
                }
            }
        } else if (e.key === 'ArrowLeft') {
            // Find "Previous" button in gallery and click it
            const prevBtns = document.querySelectorAll('.gallery button[aria-label="Previous"], .gallery button.prev-btn, .gallery button[title="Previous"]');
            for (const btn of prevBtns) {
                if (btn.offsetParent !== null) { // Visible
                    btn.click();
                    break;
                }
            }
        } else if (e.key === 'Escape') {
             // Ensure we close and return to grid
             const closeBtn = document.querySelector('.gallery button[aria-label="Close"], .gallery .close-btn');
             if (closeBtn) closeBtn.click();
             
             // Also try the custom back button
             const backBtn = document.getElementById('gallery-close-btn');
             if (backBtn) backBtn.click();
        }
    });

    // Auto-close preview when exiting browser fullscreen
    document.addEventListener('fullscreenchange', () => {
        if (!document.fullscreenElement) {
             const closeBtn = document.querySelector('.gallery button[aria-label="Close"], .gallery .close-btn');
             if (closeBtn) closeBtn.click();
             
             const backBtn = document.getElementById('gallery-close-btn');
             if (backBtn) backBtn.click();
        }
    });
}

// Initialize Gallery Path Tracking
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initGalleryPathTracking);
} else {
    initGalleryPathTracking();
}

// Initialize Lazy Loader
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initLazyFullResolution);
} else {
    initLazyFullResolution();
}

</script>
"""

def get_tree_js():
    return tree_js

"""
Shared UI utilities and helper functions.

This module provides:
- Keyword highlighting utilities (conversion between string and HighlightedText format)
- Wrapper functions for image operations (fix metadata, rerun scoring/tagging, delete)
- Default state definitions (get_empty_details) for consistent UI clearing

All wrapper functions accept runner instances as arguments to support dependency injection
and avoid global state dependencies.
"""
import gradio as gr
import os
import json
from modules import db, thumbnails

# Color palette for keyword tags - distinct, vibrant colors
KEYWORD_COLORS = [
    "#3b82f6",  # blue
    "#10b981",  # emerald
    "#f59e0b",  # amber
    "#ef4444",  # red
    "#8b5cf6",  # violet
    "#ec4899",  # pink
    "#06b6d4",  # cyan
    "#84cc16",  # lime
    "#f97316",  # orange
    "#6366f1",  # indigo
    "#14b8a6",  # teal
    "#a855f7",  # purple
]

# Generate color_map for HighlightedText (category names map to background colors)
KEYWORD_COLOR_MAP = {f"c{i}": color for i, color in enumerate(KEYWORD_COLORS)}


def keywords_to_highlighted(keywords_str):
    """
    Converts a comma-separated keywords string to HighlightedText format.
    Returns list of (keyword, category) tuples with rotating color categories.
    """
    if not keywords_str:
        return []
    keywords_list = [k.strip() for k in keywords_str.split(',') if k.strip()]
    # Assign rotating color categories for unique backgrounds
    return [(kw, f"c{i % len(KEYWORD_COLORS)}") for i, kw in enumerate(keywords_list)]


def highlighted_to_keywords(highlighted_data):
    """
    Converts HighlightedText format back to comma-separated string.
    Accepts list of (text, category) tuples.
    """
    if not highlighted_data:
        return ""
    if isinstance(highlighted_data, str):
        return highlighted_data  # Already a string (fallback)
    # Extract just the text from each tuple
    return ",".join([item[0].strip() for item in highlighted_data if item[0].strip()])

def fix_image_wrapper(details, scoring_runner):
    """Wrapper for fix_image_metadata."""
    if not details or not isinstance(details, dict):
        return gr.update(visible=True), "❌ No image selected"
        
    file_path = details.get('file_path')
    if not file_path:
        return gr.update(visible=True), "❌ Invalid image data"
        
    success, msg = scoring_runner.fix_image_metadata(file_path)
    
    if success:
        return gr.update(visible=True), f"✅ {msg}"
    else:
        return gr.update(visible=True), f"❌ {msg}"

def rerun_scoring_wrapper(details, scoring_runner):
    """Wrapper for run_single_image in scoring."""
    if not details or not isinstance(details, dict):
        return gr.update(visible=True), "❌ No image selected"
    file_path = details.get('file_path')
    if not file_path:
        return gr.update(visible=True), "❌ Invalid image data"
    
    success, msg = scoring_runner.run_single_image(file_path)
    if success:
        return gr.update(visible=True), f"✅ {msg}"
    else:
        return gr.update(visible=True), f"❌ {msg}"

def rerun_keywords_wrapper(details, tagging_runner):
    """Wrapper for run_single_image in tagging."""
    if not details or not isinstance(details, dict):
        return gr.update(visible=True), "❌ No image selected"
    file_path = details.get('file_path')
    if not file_path:
        return gr.update(visible=True), "❌ Invalid image data"
        
    success, msg = tagging_runner.run_single_image(file_path)
    if success:
        return gr.update(visible=True), f"✅ {msg}"
    else:
        return gr.update(visible=True), f"❌ {msg}"

def delete_nef(details):
    """
    Deletes the NEF file associated with the image.
    """
    if not details:
        return gr.update(value="No image selected", visible=True), gr.update(visible=False)
    
    try:
        # Resolve 'details' if it's a string (though it should be dict from State?)
        # Gradio might pass the dict as JSON object
        
        # Find NEF path
        # 1. Try nef_metadata['file_path']
        # 2. Try replacing extension of main file_path
        
        nef_path = None
        
        # Check nef_metadata
        scores_json = details.get('scores_json', {})
        if isinstance(scores_json, str):
             try: scores_json = json.loads(scores_json)
             except (json.JSONDecodeError, ValueError): scores_json = {}
             
        nef_meta = scores_json.get('nef_metadata', {})
        if nef_meta.get('file_path'):
            nef_path = nef_meta.get('file_path')
            
        # Fallback: Assume simple sidecar
        if not nef_path:
            base_path = details.get('file_path', '')
            if base_path:
                # Replace suffix with .NEF (try sensitive)
                p = os.path.splitext(base_path)[0]
                candidates = [p + ".NEF", p + ".nef"]
                for c in candidates:
                    if os.path.exists(c):
                        nef_path = c
                        break
        
        deleted_files = []
        if nef_path and os.path.exists(nef_path):
            os.remove(nef_path)
            deleted_files.append("NEF")
            
        # Delete Thumbnail
        thumb_path = thumbnails.get_thumb_wsl(details)  # WebUI runs in WSL
        if thumb_path and os.path.exists(thumb_path):
            try:
                os.remove(thumb_path)
                deleted_files.append("Thumb")
            except OSError:
                pass
                
        # Delete DB Record
        file_path = details.get('file_path')
        if file_path:
            db.delete_image(file_path)
            deleted_files.append("DB")
            
        if deleted_files:
            return gr.update(value=f"Deleted: {', '.join(deleted_files)}", visible=True), gr.update(visible=False)
        else:
            return gr.update(value=f"NEF file not found: {nef_path}", visible=True), gr.update(visible=False)
            
    except Exception as e:
        return gr.update(value=f"Error deleting: {e}", visible=True), gr.update(visible=True)

def get_empty_details():
    """
    Returns a list of default values for all image detail outputs.
    Used to clear the side panel when no image is selected or when switching categories.
    Order MUST match detail_outputs in gallery.py and wires in app.py.
    """
    return [
        "",                             # res_info (Markdown)
        {},                             # d_score_gen (Label)
        {},                             # d_score_weighted (Label)
        {},                             # d_score_models (Label)
        {},                             # image_details (State)
        gr.update(visible=False),       # delete_btn
        "",                             # d_title (Textbox)
        "",                             # d_desc (Textbox)
        [],                             # d_keywords (HighlightedText)
        "0",                            # d_rating (Dropdown)
        "None",                         # d_label (Dropdown)
        gr.update(visible=False),       # save_status (Label)
        "",                             # gallery_selected_path (Textbox)
        '<div style="display: none;"></div>', # d_culling_status (HTML)
        gr.update(visible=False),       # fix_btn
        gr.update(visible=False),       # fix_status
        gr.update(visible=False),       # rerun_score_btn
        gr.update(visible=False),       # rerun_tags_btn
        None,                           # current_selection_index (State)
        gr.update(visible=False),       # extract_preview_btn
        gr.update(value=None, visible=False), # preview_image
        gr.update(value="", visible=False)    # preview_status
    ]

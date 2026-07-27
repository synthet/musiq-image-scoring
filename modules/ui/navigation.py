"""
Navigation functions for cross-tab interactions in the WebUI.

This module provides functions to switch between tabs while preserving filter state
and context. All functions return Gradio component updates for seamless UI transitions.

Key functions:
- open_folder_in_gallery: Opens a folder in the Gallery tab with filters applied
- open_stack_in_gallery: Displays a stack's images in the Gallery tab
- open_folder_in_pipeline: Switches to the Pipeline tab and sets folder context.

All navigation functions maintain consistency with the Gallery's sorting and filtering
logic to ensure a smooth user experience.
"""
import os

import gradio as gr


def open_folder_in_gallery(folder, sort_by, sort_order, rating_filter, label_filter, keyword_filter, min_gen, min_aes, min_tech, start_date, end_date, update_gallery_fn):
    """
    Switches to gallery tab and filters by folder.
    
    Args:
        folder (str): The folder path to open.
        ...filters...
        update_gallery_fn (callable): The function to call to get gallery data.
    
    Returns:
        tuple: (Tabs update, folder state, context visible, folder html, page, *gallery_outputs)
    """
    if not folder:
        # If no folder provided, treat as "Reset / View All"
        # Call update_gallery with None folder
        gal_outs = update_gallery_fn(1, sort_by, sort_order, rating_filter, label_filter, keyword_filter, min_gen, min_aes, min_tech, start_date, end_date, folder=None, stack_id=None)
        # Returns: tabs, folder_state, stack_state, context_visible, folder_html, page, *gallery_outputs
        return gr.update(selected="gallery"), None, None, gr.update(visible=False), "", 1, *gal_outs

    # Create HTML display
    folder_name = os.path.basename(folder)
    parent_path = os.path.dirname(folder)
    folder_html = f"""
    <div style="display: flex; align-items: center; gap: 12px;">
        <span style="font-size: 1.5rem;">📁</span>
        <div>
            <div style="font-size: 1.1rem; font-weight: 600; color: #e6edf3;">{folder_name}</div>
            <div style="font-size: 0.8rem; color: #8b949e;">{parent_path}</div>
        </div>
    </div>
    """
    
    gal_outs = update_gallery_fn(1, sort_by, sort_order, rating_filter, label_filter, keyword_filter, min_gen, min_aes, min_tech, start_date, end_date, folder, stack_id=None)
    
    return gr.update(selected="gallery"), folder, None, gr.update(visible=True), folder_html, 1, *gal_outs

def open_folder_in_pipeline(folder):
    """Switches to Pipeline tab and sets input folder."""
    if not folder:
        return gr.update(selected="pipeline"), gr.update()
    return gr.update(selected="pipeline"), folder

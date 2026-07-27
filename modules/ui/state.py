"""
Shared state type definitions for the WebUI.

This module defines dataclasses for type-safe shared state management.
Currently, AppState is defined but not actively used - app.py creates states
directly. This module is kept for potential future refactoring to use the
dataclass pattern for better type safety and organization.
"""
from dataclasses import dataclass

import gradio as gr


@dataclass
class AppState:
    """
    Holds shared state components for the application.
    
    Note: Currently unused - app.py creates states directly. This is kept
    for potential future refactoring to improve type safety.
    """
    current_page: gr.State
    current_paths: gr.State
    current_folder: gr.State

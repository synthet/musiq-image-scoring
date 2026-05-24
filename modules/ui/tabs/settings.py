"""
Settings/Configuration tab module for application settings.

This module provides UI for configuring:
- Scoring defaults (force re-score, default sort)
- Processing options (queue sizes, batch size)
- Stacks & Culling legacy (shared threshold, time gap, force rescan, auto export)
- UI preferences (page size, export format)
- Tagging defaults (overwrite, captions, tokens, CLIP model)

All changes are saved to config.json and persist across sessions.
"""
import gradio as gr
from modules import config

def create_tab(app_config):
    """
    Creates the Settings/Configuration tab.
    
    Args:
        app_config (dict): The loaded application configuration.
        
    Returns:
        dict: A dictionary of components (currently empty/minimal as other tabs don't depend on these inputs directly).
    """
    
    # Load current config values with defaults
    scoring_config = app_config.get('scoring', {})
    processing_config = app_config.get('processing', {})
    clustering_config = app_config.get('clustering', {})
    culling_config = app_config.get('culling', {})
    ui_config = app_config.get('ui', {})
    tagging_config = app_config.get('tagging', {})
    
    with gr.TabItem("Settings", id="settings"):
        gr.Markdown("### ⚙️ Experimental & Advanced Configuration")
        gr.Markdown("*Configure experimental options and advanced settings. Changes are saved to config.json.*")
        
        # Scoring Configuration
        with gr.Accordion("🎯 Scoring Configuration", open=False):
            with gr.Row():
                with gr.Column():
                    cfg_force_rescore = gr.Checkbox(
                        label="Force Re-score (Default)",
                        value=scoring_config.get('force_rescore_default', False),
                        info="Default value for 'Force Re-score' checkbox in Scoring tab"
                    )
                    cfg_default_sort_by = gr.Dropdown(
                        choices=[
                            ("📅 Date Added", "created_at"),
                            ("🆔 ID", "id"),
                            ("⭐ General Score", "score_general"),
                            ("🔧 Technical Score", "score_technical"),
                            ("🎨 Aesthetic Score", "score_aesthetic"),
                        ],
                        value=scoring_config.get('default_sort_by', 'score_general'),
                        label="Default Sort Field"
                    )
                    cfg_default_sort_order = gr.Radio(
                        choices=[("↓ Descending (Highest First)", "desc"), ("↑ Ascending (Lowest First)", "asc")],
                        value=scoring_config.get('default_sort_order', 'desc'),
                        label="Default Sort Order"
                    )
        
        # Processing Configuration
        with gr.Accordion("⚙️ Processing Configuration", open=False):
            with gr.Row():
                with gr.Column():
                    gr.Markdown("**Queue Sizes** (for threaded pipeline)")
                    cfg_prep_queue_size = gr.Number(
                        value=processing_config.get('prep_queue_size', 50),
                        label="Prep Queue Max Size",
                        info="Maximum items in preparation queue (default: 50)"
                    )
                    cfg_scoring_queue_size = gr.Number(
                        value=processing_config.get('scoring_queue_size', 10),
                        label="Scoring Queue Max Size",
                        info="Maximum items in scoring queue - keep small to avoid VRAM overload (default: 10)"
                    )
                    cfg_result_queue_size = gr.Number(
                        value=processing_config.get('result_queue_size', 50),
                        label="Result Queue Max Size",
                        info="Maximum items in result queue (default: 50)"
                    )
                with gr.Column():
                    gr.Markdown("**Batch Processing**")
                    cfg_clustering_batch_size = gr.Number(
                        value=processing_config.get('clustering_batch_size', 32),
                        label="Clustering Batch Size",
                        info="Number of images processed per batch for clustering (default: 32)"
                    )
        
        # Stacks & Culling (Legacy) - shared threshold/time_gap used by both tabs
        with gr.Accordion("📚 Stacks & Culling (Legacy)", open=False):
            gr.Markdown("*Used when Stacks or Culling tabs are enabled (legacy_tabs_enabled).*")
            with gr.Row():
                with gr.Column():
                    cfg_stack_threshold = gr.Slider(
                        0.01, 1.0,
                        value=clustering_config.get('default_threshold', 0.15),
                        step=0.01,
                        label="Default Similarity Threshold",
                        info="Threshold for grouping similar images (Stacks & Culling)"
                    )
                    cfg_stack_time_gap = gr.Number(
                        value=clustering_config.get('default_time_gap', 120),
                        label="Default Time Gap (seconds)",
                        info="Time gap for splitting groups (default: 120)"
                    )
                with gr.Column():
                    cfg_clustering_force_rescan = gr.Checkbox(
                        label="Force Rescan (Default)",
                        value=clustering_config.get('force_rescan_default', False),
                        info="Default for 'Force Rescan' in Stacks tab"
                    )
                    cfg_culling_auto_export = gr.Checkbox(
                        label="Auto Export (Default)",
                        value=culling_config.get('auto_export_default', False),
                        info="Default for 'Auto-export to XMP' in Culling tab"
                    )
        
        # UI Configuration
        with gr.Accordion("🖼️ UI Configuration", open=False):
            with gr.Row():
                with gr.Column():
                    cfg_gallery_page_size = gr.Number(
                        value=ui_config.get('gallery_page_size', 50),
                        label="Gallery Page Size",
                        info="Number of images per page in gallery (default: 50)"
                    )
                    cfg_default_export_format = gr.Dropdown(
                        choices=[
                            ("📄 JSON (Full Data)", "json"),
                            ("📊 CSV (Spreadsheet)", "csv"),
                            ("📗 Excel (.xlsx)", "xlsx")
                        ],
                        value=ui_config.get('default_export_format', 'json'),
                        label="Default Export Format"
                    )
        
        # Tagging Configuration
        with gr.Accordion("🏷️ Tagging Configuration", open=False):
            with gr.Row():
                with gr.Column():
                    cfg_tagging_overwrite = gr.Checkbox(
                        label="Overwrite Existing Tags (Default)",
                        value=tagging_config.get('overwrite_default', False),
                        info="Default value for 'Overwrite' checkbox in Tagging tab"
                    )
                    cfg_tagging_captions = gr.Checkbox(
                        label="Generate Captions (Default)",
                        value=tagging_config.get('captions_default', False),
                        info="Default value for 'Captions' checkbox in Tagging tab"
                    )
                    cfg_tagging_max_tokens = gr.Number(
                        value=tagging_config.get('max_new_tokens', 50),
                        label="Max New Tokens (BLIP)",
                        info="Maximum tokens for BLIP caption generation (default: 50)"
                    )
                with gr.Column():
                    cfg_tagging_clip_model = gr.Dropdown(
                        choices=[
                            ("CLIP Base (ViT-B/32)", "openai/clip-vit-base-patch32"),
                            ("CLIP Large (ViT-L/14)", "openai/clip-vit-large-patch14")
                        ],
                        value=tagging_config.get('clip_model', 'openai/clip-vit-base-patch32'),
                        label="CLIP Model Selection",
                        info="CLIP model for keyword extraction"
                    )
        
        # Save and Reset buttons
        with gr.Row():
            cfg_save_btn = gr.Button("💾 Save All Configuration", variant="primary", size="lg")
            cfg_reset_btn = gr.Button("🔄 Reset to Defaults", variant="secondary", size="lg")
        
        cfg_status = gr.Textbox(label="Status", interactive=False, visible=False)
        
        # Configuration save handler
        def save_all_config(
            force_rescore, sort_by, sort_order,
            prep_queue, scoring_queue, result_queue, clustering_batch,
            stack_threshold, stack_gap, clust_force, cull_auto,
            page_size, export_format,
            tag_overwrite, tag_captions, tag_tokens, tag_clip_model
        ):
            try:
                thresh = float(stack_threshold) if stack_threshold else 0.15
                gap = int(stack_gap) if stack_gap else 120
                config.save_config_value('scoring', {
                    'force_rescore_default': force_rescore,
                    'default_sort_by': sort_by,
                    'default_sort_order': sort_order
                })
                config.save_config_value('processing', {
                    'prep_queue_size': int(prep_queue) if prep_queue else 50,
                    'scoring_queue_size': int(scoring_queue) if scoring_queue else 10,
                    'result_queue_size': int(result_queue) if result_queue else 50,
                    'clustering_batch_size': int(clustering_batch) if clustering_batch else 32
                })
                config.save_config_value('clustering', {
                    'default_threshold': thresh,
                    'default_time_gap': gap,
                    'force_rescan_default': clust_force
                })
                config.save_config_value('culling', {
                    'default_threshold': thresh,
                    'default_time_gap': gap,
                    'auto_export_default': cull_auto
                })
                config.save_config_value('ui', {
                    'gallery_page_size': int(page_size) if page_size else 50,
                    'default_export_format': export_format
                })
                config.save_config_value('tagging', {
                    'overwrite_default': tag_overwrite,
                    'captions_default': tag_captions,
                    'max_new_tokens': int(tag_tokens) if tag_tokens else 50,
                    'clip_model': tag_clip_model
                })
                return gr.update(value="✅ Configuration saved successfully! Restart the application for some changes to take effect.", visible=True)
            except Exception as e:
                return gr.update(value=f"❌ Error saving configuration: {str(e)}", visible=True)
        
        # Reset to defaults handler
        def reset_config_defaults():
            return (
                False, 'score_general', 'desc',
                50, 10, 50, 32,
                0.15, 120, False, False,
                50, 'json',
                False, False, 50, 'openai/clip-vit-base-patch32'
            )
        
        # Wire up events
        cfg_inputs = [
            cfg_force_rescore, cfg_default_sort_by, cfg_default_sort_order,
            cfg_prep_queue_size, cfg_scoring_queue_size, cfg_result_queue_size,
            cfg_clustering_batch_size,
            cfg_stack_threshold, cfg_stack_time_gap, cfg_clustering_force_rescan, cfg_culling_auto_export,
            cfg_gallery_page_size, cfg_default_export_format,
            cfg_tagging_overwrite, cfg_tagging_captions, cfg_tagging_max_tokens, cfg_tagging_clip_model
        ]
        
        cfg_save_btn.click(
            fn=save_all_config,
            inputs=cfg_inputs,
            outputs=[cfg_status]
        )
        
        cfg_reset_btn.click(
            fn=reset_config_defaults,
            inputs=[],
            outputs=cfg_inputs
        )
        
    return {}

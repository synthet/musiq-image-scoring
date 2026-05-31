import gradio as gr
import os
import json
import datetime
import platform
import time
from modules import db, config, utils, thumbnails
from modules.ui import common
from modules import debug

IS_WINDOWS = (platform.system() == 'Windows')


def _build_active_chips_html(rating_filter, label_filter, keyword_filter,
                             min_gen, min_aes, min_tech, start_date, end_date):
    """Builds HTML showing currently active filters as read-only chips."""
    chips = []
    if rating_filter:
        chips.append(f"Rating: {', '.join(str(r) for r in rating_filter)}")
    if label_filter:
        chips.append(f"Label: {', '.join(label_filter)}")
    if keyword_filter and keyword_filter.strip():
        chips.append(f'Keyword: "{keyword_filter.strip()}"')
    if min_gen and float(min_gen) > 0.0:
        chips.append(f"Min General: {float(min_gen):.2f}")
    if min_aes and float(min_aes) > 0.0:
        chips.append(f"Min Aesthetic: {float(min_aes):.2f}")
    if min_tech and float(min_tech) > 0.0:
        chips.append(f"Min Technical: {float(min_tech):.2f}")
    if start_date and str(start_date).strip():
        chips.append(f"From: {str(start_date).strip()}")
    if end_date and str(end_date).strip():
        chips.append(f"To: {str(end_date).strip()}")
    if not chips:
        return ""
    parts = ["<div class='active-chips-strip' role='list' aria-label='Active filters'>"]
    for chip in chips:
        parts.append(f"<span class='active-chip' role='listitem'>{chip}</span>")
    parts.append("</div>")
    return "".join(parts)


# --- Helper Functions ---

def get_gallery_data(page, page_size, sort_by, sort_order, rating_filter, label_filter, keyword_filter, min_gen, min_aes, min_tech, start_date, end_date, folder=None, stack_id=None):
    """Fetch images for gallery with pagination."""
    date_range = (start_date, end_date) if (start_date or end_date) else None
    
    try:
        wsl_folder = utils.convert_path_to_wsl(folder) if folder else None
        
        # OPTIMIZATION: Use combined query to get rows AND count in single DB round-trip
        rows = []
        total_count = 0
        with debug.PerformanceTimer("Gallery Combined DB Query"):
            rows, total_count = db.get_images_paginated_with_count(
                page, page_size, sort_by, sort_order, 
                rating_filter, label_filter, keyword_filter, 
                min_score_general=min_gen, 
                min_score_aesthetic=min_aes, 
                min_score_technical=min_tech, 
                date_range=date_range,
                folder_path=wsl_folder,
                stack_id=stack_id
            )

        
        total_pages = (total_count + page_size - 1) // page_size if total_count > 0 else 1
        
        images = []
        raw_paths = []

        with debug.PerformanceTimer(f"Process {len(rows)} Rows"):
            resolve_ms_total = 0.0
            resolve_ms_max = 0.0
            used_thumb = 0
            resolved_ok = 0
            resolved_none = 0
            cache_hits = 0
            cache_misses = 0
            fallback_calls = 0
            
            # 1. Collect IDs for batch resolution
            image_ids = [row['id'] for row in rows if 'id' in row.keys() and row['id']]
            
            # 2. Batch fetch resolved paths
            resolved_map = {}
            if image_ids:
                try:
                    with debug.PerformanceTimer("Batch Path Resolution"):
                        resolved_map = db.get_resolved_paths_batch(image_ids)
                        # Set thread-local cache for any downstream utils.resolve_file_path calls
                        utils.set_batch_path_cache(resolved_map)
                except Exception as e:
                    print(f"Batch resolve error: {e}")
            
            try:
                for row in rows:
                    file_path = row['file_path']
                    raw_paths.append(file_path)
                    image_id = row['id'] if 'id' in row.keys() else None
                    
                    t_r0 = time.perf_counter()
                    
                    # OPTIMIZED Resolution Logic
                    p = None
                    used_cache = False
                    
                    # Strategy 1: Use pre-stored WSL thumbnail path (WebUI runs in WSL)
                    local_thumb = thumbnails.get_thumb_wsl(row)
                    if local_thumb:
                        p = local_thumb
                        used_thumb += 1
                        used_cache = True
                        cache_hits += 1

                    # Strategy 2: Try Batch Cache (for image file paths)
                    if not p and image_id and image_id in resolved_map:
                        cached_path = resolved_map[image_id]
                        if cached_path:
                            p = cached_path
                            used_cache = True
                            cache_hits += 1
                    
                    # Strategy 3: Fallback to resolve_file_path (Slower)
                    if not p:
                        cache_misses += 1
                        fallback_calls += 1
                        p = utils.resolve_file_path(file_path, image_id) or utils.convert_path_to_local(file_path)

                    t_r1 = time.perf_counter()
                    
                    dt_ms = (t_r1 - t_r0) * 1000
                    resolve_ms_total += dt_ms
                    if dt_ms > resolve_ms_max:
                        resolve_ms_max = dt_ms
                    
                    # Log slow resolutions for debugging
                    if dt_ms > 20 and not used_cache:
                        debug.log_metric(f"Slow Resolve: {row['file_name']}", f"{dt_ms:.1f}", "ms")
                    
                    if p:
                        resolved_ok += 1
                    else:
                        resolved_none += 1
                        
                    # Create label with score
                    score = row['score_general']
                    score_str = f"{score:.2f}" if score is not None else "N/A"
                    label = f"{row['file_name']}\nGen: {score_str}"
                    
                    images.append((p, label))
            finally:
                # Ensure cache is cleared
                utils.clear_batch_path_cache()
            
        page_label = f"Page {page} of {total_pages} ({total_count} images)"

        # Performance Metrics
        debug.log_metric("Avg Resolve Time", f"{resolve_ms_total/len(rows):.2f}" if len(rows)>0 else "0", "ms")
        debug.log_metric("Max Resolve Time", f"{resolve_ms_max:.2f}", "ms")
        debug.log_metric("Cache Hit Rate", f"{cache_hits}/{len(rows)} ({100*cache_hits/len(rows):.1f}%)" if len(rows)>0 else "0/0", "")
        debug.log_metric("Fallback Calls", f"{fallback_calls}", "")

        return images, page_label, total_pages, raw_paths
        
    except Exception as e:
        print(f"Error fetching gallery data: {e}")
        import traceback
        traceback.print_exc()

        return [], f"Error: {e}", 1, []

def export_database(export_format, cols_basic, cols_scores, cols_metadata, cols_other,
                    filter_rating, filter_label, filter_keyword, filter_folder,
                    filter_min_gen, filter_min_aes, filter_min_tech,
                    filter_date_start, filter_date_end):
    """
    Exports the database to the specified format with optional column selection and filtering.
    Returns status message.
    """
    
    # Combine selected columns
    selected_columns = []
    if cols_basic: selected_columns.extend(cols_basic)
    if cols_scores: selected_columns.extend(cols_scores)
    if cols_metadata: selected_columns.extend(cols_metadata)
    if cols_other: selected_columns.extend(cols_other)
    
    columns = selected_columns if selected_columns else None
    
    # Process filters
    rating_filter_processed = None
    if filter_rating:
        rating_filter_processed = [0 if r == "Unrated" else int(r) for r in filter_rating]
    
    keyword_filter_processed = filter_keyword.strip() if filter_keyword and filter_keyword.strip() else None
    folder_path = filter_folder.strip() if filter_folder and filter_folder.strip() else None
    
    date_range = None
    if filter_date_start or filter_date_end:
        date_range = (filter_date_start if filter_date_start else None,
                     filter_date_end if filter_date_end else None)
    
    # Generate output filename
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))), "output") # ../../../output from modules/ui/tabs/gallery.py? No, assume app root level logic.
    # webui.py used os.path.dirname(__file__), "output". 
    # Since we are deep in structure, we should just use absolute path or relative to CWD.
    output_dir = os.path.join(os.getcwd(), "output")
    os.makedirs(output_dir, exist_ok=True)
    
    success = False
    msg = ""
    
    if export_format == "json":
        output_path = os.path.join(output_dir, f"export_{timestamp}.json")
        success, msg = db.export_db_to_json(output_path)
    elif export_format == "csv":
        output_path = os.path.join(output_dir, f"export_{timestamp}.csv")
        success, msg = db.export_db_to_csv(
            output_path, columns=columns,
            rating_filter=rating_filter_processed, label_filter=filter_label,
            keyword_filter=keyword_filter_processed, folder_path=folder_path,
            min_score_general=filter_min_gen, min_score_aesthetic=filter_min_aes,
            min_score_technical=filter_min_tech, date_range=date_range
        )
    elif export_format == "xlsx":
        output_path = os.path.join(output_dir, f"export_{timestamp}.xlsx")
        success, msg = db.export_db_to_excel(
            output_path, columns=columns,
            rating_filter=rating_filter_processed, label_filter=filter_label,
            keyword_filter=keyword_filter_processed, folder_path=folder_path,
            min_score_general=filter_min_gen, min_score_aesthetic=filter_min_aes,
            min_score_technical=filter_min_tech, date_range=date_range
        )
    else:
        return gr.update(value=f"Unknown format: {export_format}", visible=True)
    
    if success:
        return gr.update(value=f"✅ {msg}", visible=True)
    else:
        return gr.update(value=f"❌ {msg}", visible=True)

# Helper Actions Wrappers - defined in common, but wrappers for click events here
def find_similar_handler(image_details, limit=20, folder_path=None):
    """
    Find images visually similar to the selected image.
    Returns (gallery_images, status_markdown) for the Similar Images accordion.
    """
    if not image_details or not isinstance(image_details, dict):
        return [], "Select an image first."
    image_id = image_details.get("id")
    if not image_id:
        return [], "No image selected."
    try:
        from modules import similar_search, utils
        wsl_folder = utils.convert_path_to_wsl(folder_path) if folder_path else None
        result = similar_search.search_similar_images(
            example_image_id=image_id,
            limit=limit,
            folder_path=wsl_folder,
            min_similarity=0.80,
        )
    except Exception as e:
        return [], f"Error: {e}"
    if isinstance(result, dict) and "error" in result:
        return [], result["error"]
    if not result:
        return [], "No similar images found."
    images = []
    for r in result:
        file_path = r.get("file_path")
        sim = r.get("similarity", 0)
        image_id_r = r.get("image_id")
        if not file_path:
            continue
        details = db.get_image_details(file_path)
        p = None
        if details:
            p = thumbnails.get_thumb_wsl(details)
        if not p:
            p = utils.resolve_file_path(file_path, image_id_r) or utils.convert_path_to_local(file_path)
        if p and os.path.exists(p):
            label = f"{sim:.0%} similar"
            images.append((p, label))
    if not images:
        return [], "No similar images found (thumbnails unavailable)."
    status = f"Found {len(images)} similar image(s)."
    return images, status


def save_metadata_action(details, title, desc, keywords, rating, label, tagging_runner):
    if not details or not isinstance(details, dict):
         return "Error: No image selected.", gr.update(visible=True)
         
    file_path = details.get('file_path')
    if not file_path:
         return "Error: Invalid image record.", gr.update(visible=True)
         
    # Parse Keywords
    if isinstance(keywords, list):
        # HighlightedText returns list of (token, class)
        keywords_str = common.highlighted_to_keywords(keywords)
    else:
        keywords_str = keywords
        
    kw_list = [k.strip() for k in keywords_str.split(',') if k.strip()]
    
    try:
        r_val = int(rating) if rating else 0
        l_val = label if label != "None" else ""
        
        success = db.update_image_metadata(file_path, keywords_str, title, desc, r_val, l_val)
        if not success:
             return "Failed to update database.", gr.update(visible=True)
             
        if tagging_runner.write_metadata(file_path, kw_list, title, desc, r_val, l_val):
            return f"Saved metadata for {os.path.basename(file_path)}", gr.update(visible=False)
        else:
             return "Saved to DB, but failed to write to file.", gr.update(visible=True)
             
    except Exception as e:
        return f"Error saving metadata: {e}", gr.update(visible=True)

def display_details(raw_paths, evt: gr.SelectData = None, forced_index=None):
    """Fetches and formats image details for the side panel."""
    try:

        
        index = None
        if forced_index is not None:
            index = forced_index
        elif evt is not None:
            index = evt.index
                
        # Debug info for empty return case
        if index is None or not raw_paths or not isinstance(index, int) or index >= len(raw_paths):
            empty = common.get_empty_details()
            debug_msg = "**DEBUG INFO:** No selection or invalid index.\n"
            if index is None: debug_msg += "- Index is None\n"
            else: debug_msg += f"- Index: {index}\n"
            
            if not raw_paths: debug_msg += "- Raw Paths is Empty/None\n"
            else: debug_msg += f"- Raw Paths Len: {len(raw_paths)}\n"
            
            # Additional Type Debugging
            debug_msg += f"\n- Arg raw_paths type: {type(raw_paths)}\n"
            debug_msg += f"- Arg evt type: {type(evt)}\n"

            empty[0] = debug_msg
            return empty
        
        file_path = raw_paths[index]
        

        
        details = db.get_image_details(file_path)
        if not details:
            empty = common.get_empty_details()
            empty[0] = f"**DEBUG ERROR:**\nDetails not found for path:\n`{file_path}`\n\nRaw Paths Len: {len(raw_paths)}\nIndex: {index}"
            return empty

        # Legacy inference timing (blob-only until dedicated storage exists)
        model_times = common.legacy_model_times_from_details(details)

        # Logic for Delete Button (NEF only + specific ratings/labels)
        show_delete = False
        is_nef = os.path.splitext(file_path)[1].lower() in ['.nef', '.nrw']
        if is_nef:
            rating = int(details.get('rating') or 0)
            label = details.get('label') or ''
            if (rating > 0 and rating <= 2) or label in ["Red", "Yellow"]:
                show_delete = True

        # Prepare Visual Outputs
        filename = details.get('file_name', os.path.basename(file_path))
        created = details.get('created_at', 'Unknown')
        
        # Convert path for display (WSL -> Windows if needed)
        display_path = utils.convert_path_to_local(file_path)
        
        res_info = f"**File:** `{filename}`\n\n**Path:** `{display_path}`\n\n**Date:** {created}"
        
        gen_score = details.get('score_general')
        gen_score = float(gen_score) if gen_score is not None else 0.0
        # Ensure we pass a dict to Label to force bar visualization, but handle 0.0 explicitly
        gen_label = {"General Score": gen_score}
        
        tech = details.get('score_technical')
        tech = float(tech) if tech is not None else 0.0
        aes = details.get('score_aesthetic')
        aes = float(aes) if aes is not None else 0.0
        weighted_label = {"Technical": tech, "Aesthetic": aes}
        
        models_label = {}
        
        ims_scores: dict[str, float | None] = {}
        try:
            image_id = details.get('id')
            if image_id is not None:
                ims_map = db.get_batch_image_model_scores([int(image_id)]) or {}
                for name, entry in (ims_map.get(int(image_id)) or {}).items():
                    if entry.get('is_shadow'):
                        continue
                    val = entry.get('normalized')
                    if val is None:
                        val = entry.get('raw_score')
                    if val is not None:
                        ims_scores[name] = float(val)
        except Exception:
            ims_scores = {}

        model_scores_map = {
            'spaq': ('SPAQ', ims_scores.get('spaq', 0) or 0),
            'ava': ('AVA', ims_scores.get('ava', 0) or 0),
            'koniq': ('KonIQ', ims_scores.get('koniq', 0) or 0),
            'paq2piq': ('PaQ2PiQ', ims_scores.get('paq2piq', 0) or 0),
            'liqe': ('LIQE', ims_scores.get('liqe', 0) or 0),
        }
        
        for model_key, (model_name, score) in model_scores_map.items():
            if score and score > 0:
                if model_key in model_times:
                    models_label[f"{model_name} ({model_times[model_key]:.3f}s)"] = score
                else:
                    models_label[model_name] = score

        # Metadata fields
        title = details.get('title', '')
        desc = details.get('description', '')
        keywords_str = details.get('keywords', '')
        keywords_highlighted = common.keywords_to_highlighted(keywords_str)
        rating_val = str(details.get('rating', 0))
        label_val = details.get('label', 'None') or 'None'
        
        # Culling Status HTML (Optional DB sidecar)
        try:
            culling_status = db.get_image_culling_status(file_path) if hasattr(db, 'get_image_culling_status') else None
        except Exception:
            culling_status = None
            
        culling_html = '<div style="display: none;"></div>'
        if culling_status:
            color = "#3fb950" if culling_status == "pick" else "#f85149" if culling_status == "reject" else "#d29922"
            text = "Pick" if culling_status == "pick" else "Reject" if culling_status == "reject" else "Maybe"
            culling_html = f'<div style="margin-top: 10px; padding: 5px 10px; border-radius: 5px; background: {color}22; border: 1px solid {color}44; color: {color}; font-weight: bold; text-align: center;">AI Status: {text}</div>'

        # Fix button visibility logic - use resolved_path first
        image_id = details.get('id')
        local_p = utils.resolve_file_path(file_path, image_id) or utils.convert_path_to_local(file_path)
        show_fix = local_p and os.path.exists(local_p)
        
        # RAW Preview logic
        is_raw = os.path.splitext(file_path)[1].lower() in ['.nef', '.nrw', '.cr2', '.cr3', '.arw', '.dng', '.orf', '.rw2']

        return [
            res_info, gen_label, weighted_label, models_label, details,
            gr.update(visible=show_delete), title, desc, keywords_highlighted,
            rating_val, label_val, gr.update(visible=False), 
            file_path, culling_html, gr.update(visible=show_fix), 
            gr.update(visible=False), gr.update(visible=show_fix), gr.update(visible=show_fix), index,
            gr.update(visible=is_raw), gr.update(value=None, visible=False), gr.update(value="", visible=False)
        ]

    except Exception as e:
        import traceback
        traceback.print_exc()
        empty = common.get_empty_details()
        empty[0] = f"**SYSTEM ERROR in display_details:**\n\n{str(e)}\n\nSee console for traceback."
        return empty

# --- RAW Preview Action ---
def extract_preview_action(path):
    import gradio as gr
    if not path:
        return gr.update(visible=True, value="No image selected"), gr.update(visible=False)
    
    from modules.thumbnails import generate_preview
    import os
    try:
        # Convert path to WSL if running within container
        from modules import utils
        import platform
        if platform.system() != 'Windows':
            # Best attempt to rewrite path for generation logic if provided path is Windows format
            path = utils.convert_path_to_local(path)

        preview_path = generate_preview(path)
        if preview_path and os.path.exists(preview_path):
            return gr.update(visible=False, value=""), gr.update(value=preview_path, visible=True)
        else:
            return gr.update(visible=True, value="Failed to generate preview."), gr.update(visible=False)
    except Exception as e:
        return gr.update(visible=True, value=f"Error: {e}"), gr.update(visible=False)

# --- Component Creation ---

def create_tab(shared_state, current_folder_state, current_stack_state, runner, tagging_runner, app_config):
    PAGE_SIZE = app_config.get('ui', {}).get('gallery_page_size', 50)
    current_page, current_paths, image_details = shared_state
    
    # Internal wrappers that close over variables
    def update_gallery(page, sort_by, sort_order, rating_filter, label_filter, keyword_filter, min_gen, min_aes, min_tech, start_date, end_date, folder=None, stack_id=None):
        images, label, total_pages, raw_paths = get_gallery_data(
            page, PAGE_SIZE, sort_by, sort_order, rating_filter, label_filter, keyword_filter, 
            min_gen, min_aes, min_tech, start_date, end_date, folder, stack_id
        )

        # Details cleared must match detail_outputs list
        # We need a predictable list of default values for all detail outputs
        # List order: [res_info, gen_label, weighted_label, models_label, details_state, delete_btn, title, desc, keywords, rating, label, save_status, current_path, culling_html, fix_btn, fix_status, rerun_score_btn, rerun_tags_btn, selected_index]
        return [images, label, raw_paths] + common.get_empty_details()

    def next_page(page, *args):
        # args match filter_inputs below, minus folder_context_group?
        # args will be [sort_by, sort_order, ...]
        # We need to extract folder from args if present.
        # But filter_inputs includes folder_context_group which is just a Group. 
        # Actually in webui.py `current_folder_state` was passed.
        stack_id = args[-1]
        folder = args[-2]
        other_args = args[:-2]
        _, _, total, _ = get_gallery_data(page, PAGE_SIZE, *other_args, folder=folder, stack_id=stack_id)
        new = min(page + 1, total)
        return [new] + update_gallery(new, *other_args, folder=folder, stack_id=stack_id)

    def prev_page(page, *args):
        stack_id = args[-1]
        folder = args[-2]
        other_args = args[:-2]
        new = max(page - 1, 1)
        return [new] + update_gallery(new, *other_args, folder=folder, stack_id=stack_id)
    
    def first_page(*args):
        stack_id = args[-1]
        folder = args[-2]
        other_args = args[:-2]
        return [1] + update_gallery(1, *other_args, folder=folder, stack_id=stack_id)
    
    def last_page(*args):
        stack_id = args[-1]
        folder = args[-2]
        other_args = args[:-2]
        _, _, total, _ = get_gallery_data(1, PAGE_SIZE, *other_args, folder=folder, stack_id=stack_id)
        return [total] + update_gallery(total, *other_args, folder=folder, stack_id=stack_id)
        
    def reset_folder_filter(*args):
         # Returns: folder_context_group, folder_display, current_folder_state, page, *gallery_outputs
         folder = None 
         # args are filters + stack_id? No, reset_folder_btn inputs don't include stack_id in base logic usually calling first_page.
         # But reset_folder_btn should also clear stack?
         # "Clear Filter" usually clears folder. User might want to clear stack too.
         # Let's say it clears both for "View All".
         stack_id = None
         # args will be other filters
         gal_outs = update_gallery(1, *args, folder=None, stack_id=None)
         return gr.update(visible=False), "", None, None, 1, *gal_outs

    def display_details_wrapper(evt, raw_paths):
        return display_details(evt, raw_paths)

    def remove_from_db_and_refresh(details, page, sort_by, sort_order, rating_filter, label_filter, keyword_filter, min_gen, min_aes, min_tech, start_date, end_date, folder=None, stack_id=None):
        """
        Remove selected image from DB (does not delete the file), then refresh the gallery.
        Returns outputs matching: [current_page, gallery, page_label, current_paths] + detail_outputs
        """
        msg = "❌ No image selected"
        try:
            if details and isinstance(details, dict):
                file_path = details.get('file_path')
                if file_path:
                    success, db_msg = db.delete_image(file_path)
                    msg = f"✅ {db_msg}" if success else f"❌ {db_msg}"
                else:
                    msg = "❌ Invalid image data (missing file_path)"
        except Exception as e:
            msg = f"❌ Failed to remove from DB: {e}"

        # Refresh gallery and clamp page if needed after deletion
        images, label, total_pages, raw_paths = get_gallery_data(
            page, PAGE_SIZE, sort_by, sort_order, rating_filter, label_filter, keyword_filter,
            min_gen, min_aes, min_tech, start_date, end_date, folder, stack_id
        )
        if page > total_pages:
            page = total_pages
            images, label, total_pages, raw_paths = get_gallery_data(
                page, PAGE_SIZE, sort_by, sort_order, rating_filter, label_filter, keyword_filter,
                min_gen, min_aes, min_tech, start_date, end_date, folder, stack_id
            )

        cleared = common.get_empty_details()
        # Reuse fix_status textbox to show the result message
        cleared[15] = gr.update(value=msg, visible=True)

        return [page, images, label, raw_paths] + cleared

    # Re-declare display_details locally or import? 
    # I already defined `display_details` at module level.
    
    with gr.TabItem("Gallery", id="gallery", visible=False):
        # Folder Context Bar
        with gr.Group(visible=False, elem_classes=["folder-context-bar"]) as folder_context_group:
            with gr.Row():
                 with gr.Column(scale=4):
                     folder_display = gr.HTML(value="")
                 with gr.Column(scale=1, min_width=150):
                     reset_folder_btn = gr.Button("✕ Clear Filter", variant="secondary", size="sm")

        # Main Controls Row
        with gr.Row(elem_classes=["gallery-header"]):
            with gr.Column(scale=1, min_width=200):
                refresh_btn = gr.Button("🔄 Refresh", variant="primary", size="lg")
            with gr.Column(scale=2):
                with gr.Row():
                    sort_dropdown = gr.Dropdown(
                        choices=[
                            ("📅 Date Added", "created_at"),
                            ("📷 Capture Date (EXIF)", "date_time_original"),
                            ("🆔 ID", "id"),
                            ("⭐ General Score", "score_general"),
                            ("🔧 Technical Score", "score_technical"),
                            ("🎨 Aesthetic Score", "score_aesthetic"),
                        ],
                        value=app_config.get('scoring', {}).get('default_sort_by', 'score_general'),
                        label="Sort By", container=False)
                    order_dropdown = gr.Dropdown(
                        choices=[("↓ Highest First", "desc"), ("↑ Lowest First", "asc")], 
                        value=app_config.get('scoring', {}).get('default_sort_order', 'desc'), 
                        label="Order", container=False)

        # Filter Presets
        with gr.Row(elem_classes=["filter-preset-row"]):
            gr.HTML("<span style='font-size:0.82rem;color:var(--text-muted);align-self:center;'>Presets:</span>")
            preset_top_rated = gr.Button("Top Rated", size="sm", elem_classes=["filter-chip"])
            preset_needs_review = gr.Button("Needs Review", size="sm", elem_classes=["filter-chip"])
            preset_has_keywords = gr.Button("Has Keywords", size="sm", elem_classes=["filter-chip"])
            preset_reset_all = gr.Button("Reset All", size="sm", elem_classes=["secondary-btn"])

        # Active Filter Chips
        active_chips_html = gr.HTML(value="", elem_classes=["active-chips-strip"])

        # Filters Section
        with gr.Accordion("🔍 Filters & Search", open=False):
            with gr.Row():
                filter_rating = gr.CheckboxGroup(choices=["1", "2", "3", "4", "5"], label="Rating Filter")
                filter_label = gr.CheckboxGroup(choices=["Red", "Yellow", "Green", "Blue", "Purple", "None"], label="Color Label")
            with gr.Row():
                f_min_gen = gr.Slider(0.0, 1.0, value=0.0, step=0.05, label="Min General")
                f_min_aes = gr.Slider(0.0, 1.0, value=0.0, step=0.05, label="Min Aesthetic")
                f_min_tech = gr.Slider(0.0, 1.0, value=0.0, step=0.05, label="Min Technical")
            with gr.Row():
                f_date_start = gr.Textbox(label="From Date", placeholder="YYYY-MM-DD", scale=1)
                f_date_end = gr.Textbox(label="To Date", placeholder="YYYY-MM-DD", scale=1)
                filter_keyword = gr.Textbox(label="Keyword Search", placeholder="Search tags...", scale=2)
        
        # Export Section
        with gr.Accordion("📤 Export Data", open=False, elem_classes=["accordion"]):
            with gr.Row():
                 export_format = gr.Dropdown(
                    choices=[("📄 JSON", "json"), ("📊 CSV", "csv"), ("📗 Excel", "xlsx")],
                    value=app_config.get('ui', {}).get('default_export_format', 'json'),
                    label="Export Format", scale=1)
                 export_btn = gr.Button("⬇️ Export All Images", variant="primary", size="sm", scale=1)
                 export_status = gr.Textbox(label="Status", visible=False) # Helper output
            
            with gr.Accordion("⚙️ Advanced Options", open=False):
                 available_columns = db.get_available_columns()
                 basic_cols = ['id', 'file_path', 'file_name', 'file_type', 'created_at']
                 # Per-model scores (spaq/ava/koniq/paq2piq/liqe) live in
                 # ``image_model_scores`` and are not selectable via this
                 # ``images``-table export. Use the REST API or run an
                 # IMS-aware SQL export to pull per-model values.
                 score_cols = ['score_general', 'score_technical', 'score_aesthetic']
                 metadata_cols = ['rating', 'label', 'keywords', 'title', 'description']
                 other_cols = [c for c in available_columns if c not in basic_cols + score_cols + metadata_cols]
                 
                 with gr.Row():
                     with gr.Column(scale=1): 
                         gr.Markdown("**Basic**")
                         export_cols_basic = gr.CheckboxGroup(choices=basic_cols, value=basic_cols, show_label=False)
                     with gr.Column(scale=1): 
                         gr.Markdown("**Scores**")
                         export_cols_scores = gr.CheckboxGroup(choices=score_cols, value=score_cols, show_label=False)
                     with gr.Column(scale=1): 
                         gr.Markdown("**Metadata**")
                         export_cols_metadata = gr.CheckboxGroup(choices=metadata_cols, value=metadata_cols, show_label=False)
                     with gr.Column(scale=1): 
                         gr.Markdown("**Other**")
                         export_cols_other = gr.CheckboxGroup(choices=other_cols, value=[], show_label=False)

        # Pagination
        with gr.Row(elem_classes=["pagination-container"]):
             first_btn = gr.Button("⏮", size="sm", elem_classes=["page-btn"], scale=0)
             prev_btn = gr.Button("◀", size="sm", elem_classes=["page-btn"], scale=0)
             page_label = gr.Button(value="Page 1 of 1", interactive=False, elem_classes=["page-indicator"], scale=1)
             next_btn = gr.Button("▶", size="sm", elem_classes=["page-btn"], scale=0)
             last_btn = gr.Button("⏭", size="sm", elem_classes=["page-btn"], scale=0)

        # Main Content
        with gr.Row():
            with gr.Column(scale=3):
                gallery = gr.Gallery(label="📸 Image Gallery", columns=5, height=600, object_fit="cover", allow_preview=True)
            
            with gr.Column(scale=1, min_width=320, elem_classes=["details-panel"]):
                res_info = gr.Markdown()
                d_score_gen = gr.Label(label="General", num_top_classes=1)
                d_score_weighted = gr.Label(label="Weighted")
                d_score_models = gr.Label(label="Models")
                d_culling_status = gr.HTML(value='<div style="display: none;"></div>')
                
                with gr.Accordion("ℹ️ Image Details", open=False):
                    d_title = gr.Textbox(label="Title", interactive=False)
                    d_desc = gr.Textbox(label="Description", interactive=False)
                    # Use our custom color map so keyword chips aren't pastel-light (unreadable with white text)
                    d_keywords = gr.HighlightedText(
                        label="Keywords",
                        combine_adjacent=False,
                        color_map=common.KEYWORD_COLOR_MAP,
                    )
                    with gr.Row():
                        d_rating = gr.Dropdown(choices=["0", "1", "2", "3", "4", "5"], label="Rating", interactive=False)
                        d_label = gr.Dropdown(choices=["None", "Red", "Yellow", "Green", "Blue", "Purple"], label="Label", interactive=False)
                    save_btn = gr.Button("💾 Save", visible=False)
                    save_status = gr.Label(visible=False)

                with gr.Row():
                    fix_btn = gr.Button("🔧 Fix Data", variant="secondary", size="sm", visible=False)
                    rerun_score_btn = gr.Button("🔄 Re-Run Scoring", variant="secondary", size="sm", visible=False)
                    rerun_tags_btn = gr.Button("🏷️ Re-Run Keywords", variant="secondary", size="sm", visible=False)
                    find_similar_btn = gr.Button("🔍 Find Similar", variant="secondary", size="sm")
                    remove_db_btn = gr.Button("🗑️ Remove from DB", variant="stop", visible=True, size="sm")
                    delete_btn = gr.Button("🗑️ Delete NEF", variant="stop", visible=False, size="sm")
                
                with gr.Accordion("🖼️ RAW Preview", open=False):
                    extract_preview_btn = gr.Button("Extract Full Preview", variant="primary", visible=False)
                    preview_status = gr.Textbox(label="Status", visible=False)
                    preview_image = gr.Image(label="Preview", interactive=False, visible=False)
                
                with gr.Accordion("🔍 Similar Images", open=False) as similar_accordion:
                    similar_gallery = gr.Gallery(label="Similar", columns=5, height=200, object_fit="cover", allow_preview=True)
                    similar_status = gr.Markdown(value="")
                
                fix_status = gr.Textbox(label="Status", visible=False)
                # delete_status defined implicitly in return of delete_nef if separate, 
                # but we usually reuse a label or separate one.
                # In display_details, we just used gr.update.
                # Let's add delete_status
                # In webui.py it wasn't explicit component? 
                # Wait, delete_nef returned (status, visible_update).
                # We can reuse fix_status or make new one.
                delete_status = gr.Textbox(label="Status", visible=False) # Separate one
                
                # Store path in a hidden textbox - MUST be visible=True for DOM rendering
                # Hide with CSS instead of visible=False (which removes from DOM entirely)
                gallery_selected_path = gr.Textbox(
                    value="", 
                    visible=True,  # Must be True to render in DOM
                    elem_id="gallery-selected-path",
                    elem_classes=["hidden-path-storage"],  # CSS class for hiding
                    container=False,
                    interactive=False,
                    show_label=False
                )
                current_selection_index = gr.State(None)

        # Component validation function
        def validate_components():
            """Ensure all components are initialized before wiring."""
            components = [
                res_info, d_score_gen, d_score_weighted, d_score_models, image_details,
                delete_btn, d_title, d_desc, d_keywords, d_rating, d_label, save_status,
                gallery_selected_path, d_culling_status, fix_btn, fix_status,
                rerun_score_btn, rerun_tags_btn, current_selection_index,
                extract_preview_btn, preview_image, preview_status
            ]
            for i, comp in enumerate(components):
                if comp is None:
                    raise ValueError(f"Component at index {i} in detail_outputs is None! "
                                   f"Component names: res_info, d_score_gen, d_score_weighted, "
                                   f"d_score_models, image_details, delete_btn, d_title, d_desc, "
                                   f"d_keywords, d_rating, d_label, save_status, gallery_selected_path, "
                                   f"d_culling_status, fix_btn, fix_status, rerun_score_btn, "
                                   f"rerun_tags_btn, current_selection_index, extract_preview_btn, preview_image, preview_status")
            return components

        # Definition of detail_outputs for wiring
        # Order MUST match update_gallery return and display_details return
        detail_outputs = validate_components()
        
        # Wiring Logic
        filter_inputs_base = [sort_dropdown, order_dropdown, filter_rating, filter_label, filter_keyword, f_min_gen, f_min_aes, f_min_tech, f_date_start, f_date_end, current_folder_state, current_stack_state]
        
        refresh_btn.click(fn=first_page, inputs=filter_inputs_base, outputs=[current_page, gallery, page_label, current_paths] + detail_outputs)
        
        # Pagination Events
        next_btn.click(fn=next_page, inputs=[current_page] + filter_inputs_base, outputs=[current_page, gallery, page_label, current_paths] + detail_outputs)
        prev_btn.click(fn=prev_page, inputs=[current_page] + filter_inputs_base, outputs=[current_page, gallery, page_label, current_paths] + detail_outputs)
        first_btn.click(fn=first_page, inputs=filter_inputs_base, outputs=[current_page, gallery, page_label, current_paths] + detail_outputs)
        last_btn.click(fn=last_page, inputs=filter_inputs_base, outputs=[current_page, gallery, page_label, current_paths] + detail_outputs)
        
        # Filter Changes (always_last debounces slider drags to avoid flickering)
        for inp in filter_inputs_base[:-2]: # exclude folder_state and stack_state
            # When filter changes, go to first page
             inp.change(fn=first_page, inputs=filter_inputs_base, outputs=[current_page, gallery, page_label, current_paths] + detail_outputs, trigger_mode="always_last")

        # Active chips: update whenever any filter changes
        chip_inputs = [filter_rating, filter_label, filter_keyword, f_min_gen, f_min_aes, f_min_tech, f_date_start, f_date_end]
        for inp in chip_inputs:
            inp.change(
                fn=_build_active_chips_html,
                inputs=chip_inputs,
                outputs=[active_chips_html],
                trigger_mode="always_last",
            )

        # --- Filter Presets ---
        gallery_outputs = [current_page, gallery, page_label, current_paths] + detail_outputs

        def _apply_preset_top_rated(folder, stack_id):
            """Top Rated: rating 4-5, sort by general score."""
            rating = ["4", "5"]
            gal = update_gallery(1, "score_general", "desc", rating, [], "", 0.0, 0.0, 0.0, "", "", folder, stack_id)
            chips = _build_active_chips_html(rating, [], "", 0.0, 0.0, 0.0, "", "")
            return [rating, [], "", 0.0, 0.0, 0.0, "", "", "score_general", "desc", chips, 1] + list(gal)

        def _apply_preset_needs_review(folder, stack_id):
            """Needs Review: no rating filter, sort by general score (unrated images surface)."""
            gal = update_gallery(1, "score_general", "desc", [], [], "", 0.0, 0.0, 0.0, "", "", folder, stack_id)
            chips = _build_active_chips_html([], [], "", 0.0, 0.0, 0.0, "", "")
            return [[], [], "", 0.0, 0.0, 0.0, "", "", "score_general", "desc", chips, 1] + list(gal)

        def _apply_preset_has_keywords(folder, stack_id):
            """Has Keywords: keyword search with wildcard to surface tagged images."""
            gal = update_gallery(1, "score_general", "desc", [], [], "%", 0.0, 0.0, 0.0, "", "", folder, stack_id)
            chips = _build_active_chips_html([], [], "%", 0.0, 0.0, 0.0, "", "")
            return [[], [], "%", 0.0, 0.0, 0.0, "", "", "score_general", "desc", chips, 1] + list(gal)

        def _apply_preset_reset(folder, stack_id):
            """Reset all filters to defaults."""
            default_sort = app_config.get('scoring', {}).get('default_sort_by', 'score_general')
            default_order = app_config.get('scoring', {}).get('default_sort_order', 'desc')
            gal = update_gallery(1, default_sort, default_order, [], [], "", 0.0, 0.0, 0.0, "", "", folder, stack_id)
            return [[], [], "", 0.0, 0.0, 0.0, "", "", default_sort, default_order, "", 1] + list(gal)

        preset_outputs = [
            filter_rating, filter_label, filter_keyword,
            f_min_gen, f_min_aes, f_min_tech,
            f_date_start, f_date_end,
            sort_dropdown, order_dropdown,
            active_chips_html,
            current_page,
        ] + [gallery, page_label, current_paths] + detail_outputs

        preset_inputs = [current_folder_state, current_stack_state]

        preset_top_rated.click(fn=_apply_preset_top_rated, inputs=preset_inputs, outputs=preset_outputs)
        preset_needs_review.click(fn=_apply_preset_needs_review, inputs=preset_inputs, outputs=preset_outputs)
        preset_has_keywords.click(fn=_apply_preset_has_keywords, inputs=preset_inputs, outputs=preset_outputs)
        preset_reset_all.click(fn=_apply_preset_reset, inputs=preset_inputs, outputs=preset_outputs)

        # Reset Folder
        reset_folder_btn.click(
            fn=reset_folder_filter, 
            inputs=filter_inputs_base[:-2], # filters only
            outputs=[folder_context_group, folder_display, current_folder_state, current_stack_state, current_page, gallery, page_label, current_paths] + detail_outputs
        )
        
        # Gallery Select
        gallery.select(
            fn=display_details,
            inputs=[current_paths], 
            outputs=detail_outputs
        )
        
        # Actions
        fix_btn.click(
            fn=lambda d: common.fix_image_wrapper(d, runner),
            inputs=[image_details],
            outputs=[fix_btn, fix_status]
        )
        
        rerun_score_btn.click(
            fn=lambda d: common.rerun_scoring_wrapper(d, runner),
            inputs=[image_details],
            outputs=[fix_btn, fix_status] # reuse fix_status for message
        )
        
        rerun_tags_btn.click(
            fn=lambda d: common.rerun_keywords_wrapper(d, tagging_runner),
            inputs=[image_details],
            outputs=[fix_btn, fix_status]
        )
        
        def find_similar_wrapper(details, folder):
            imgs, msg = find_similar_handler(details, limit=20, folder_path=folder)
            return imgs, msg
        
        find_similar_btn.click(
            fn=find_similar_wrapper,
            inputs=[image_details, current_folder_state],
            outputs=[similar_gallery, similar_status]
        )
        
        save_btn.click(
            fn=lambda d, t, desc, k, r, l: save_metadata_action(d, t, desc, k, r, l, tagging_runner),
            inputs=[image_details, d_title, d_desc, d_keywords, d_rating, d_label],
            outputs=[save_status, save_status] # msg, visibility
        )
        
        delete_btn.click(
            fn=common.delete_nef, 
            inputs=[image_details],
            outputs=[delete_status, delete_btn] # msg, visibility
        )

        remove_db_btn.click(
            fn=remove_from_db_and_refresh,
            inputs=[image_details, current_page] + filter_inputs_base,
            outputs=[current_page, gallery, page_label, current_paths] + detail_outputs
        )
        
        extract_preview_btn.click(
            fn=extract_preview_action,
            inputs=[gallery_selected_path],
            outputs=[preview_status, preview_image]
        )
        
        # Export
        export_btn.click(
            fn=export_database,
            inputs=[export_format, export_cols_basic, export_cols_scores, export_cols_metadata, export_cols_other, 
                    filter_rating, filter_label, filter_keyword, current_folder_state, 
                    f_min_gen, f_min_aes, f_min_tech, f_date_start, f_date_end],
            outputs=[export_status]
        )

    return {
        'gallery': gallery,
        'folder_context_group': folder_context_group,
        'folder_display': folder_display,
        'page_label': page_label,
        'detail_outputs': detail_outputs,
        'filter_inputs': filter_inputs_base,
        'update_gallery_fn': update_gallery, # For external use
        # Components needed for external wiring if any
    }

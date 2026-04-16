import datetime
import html
import json
import gradio as gr
from modules import db
from modules import ui_tree
from modules.phases import PhaseRegistry
from modules.pipeline_selector_composer import compose_selector_request, validate_and_preview, save_preset, load_presets

# Cache for timer-based status updates to avoid unnecessary SSE pushes
_last_status_cache = {"state": None}


def _parse_phase_summary(folder_path, force_refresh=False):
    """
    Calls db.get_folder_phase_summary() and converts the list result
    into a dict keyed by phase code for easy lookup.

    Returns: (summary_by_code: dict, total_count: int)
      summary_by_code = {
        "indexing": {"status": ..., "done_count": ..., "total_count": ...},
        "scoring":  { ... },
        ...
      }
    """
    if not folder_path:
        return {}, 0

    summary_list = db.get_folder_phase_summary(folder_path, force_refresh=force_refresh)
    # summary_list is [{code, name, sort_order, status, done_count, total_count}, ...]
    summary_by_code = {}
    total_count = 0
    for item in summary_list:
        code = item.get("code", "")
        summary_by_code[code] = item
        # All phases report the same total_count (number of images in folder)
        tc = item.get("total_count", 0)
        if tc > total_count:
            total_count = tc

    return summary_by_code, total_count


def create_tab(app_config, scoring_runner, tagging_runner, selection_runner, orchestrator) -> dict:
    """Consolidated Pipeline tab containing workspace targets, stage progress, controls, and active monitor."""
    components = {}

    with gr.Tab("Runs", id="pipeline"):
        with gr.Row(equal_height=False):
            # SIDEBAR
            with gr.Column(scale=1, min_width=300, elem_classes=["sidebar"]):
                gr.Markdown("### Workspace Targets (Folders)")
                with gr.Row():
                    components["refresh_btn"] = gr.Button("Refresh", elem_classes=["secondary-btn"])

                components["tree_view"] = gr.HTML(
                    value=ui_tree.get_tree_html(),
                    elem_classes=["tree-container"]
                )
                # Must be visible=True for DOM rendering so JS selectFolder() can update it.
                # Hide with CSS (visible=False removes from DOM entirely).
                components["selected_path"] = gr.Textbox(
                    value="",
                    visible=True,
                    elem_id="folder_tree_selection",
                    elem_classes=["hidden-path-storage"],
                    container=False,
                    interactive=False,
                    show_label=False,
                )

                gr.HTML("<div class='section-divider'></div>")

                components["folder_summary_html"] = gr.HTML(
                    _build_folder_summary(None, 0)
                )

                gr.HTML("<div class='section-divider'></div>")

            # MAIN DASHBOARD
            with gr.Column(scale=3):
                # QUICK START PANEL
                components["quick_start_html"] = gr.HTML(
                    _build_quick_start_html(None),
                    elem_classes=["animate-in"],
                )

                # PANEL: Target Composer
                with gr.Group(elem_classes=["panel"]):
                    gr.HTML("<div class='panel-header'><h2 class='panel-title'>Target Composer</h2></div>")
                    with gr.Column(elem_classes=["panel-body"]):
                        components["composer_modes"] = gr.CheckboxGroup(
                            choices=["image", "file", "folder", "subtree", "list"],
                            value=["folder"],
                            label="Selector chips",
                        )
                        components["composer_input_path"] = gr.Textbox(label="Path (image or folder)", value="")
                        with gr.Row():
                            components["composer_image_ids"] = gr.Textbox(label="Image IDs (csv)", value="")
                            components["composer_folder_ids"] = gr.Textbox(label="Folder IDs (csv)", value="")
                        components["composer_image_paths"] = gr.Textbox(label="Image paths (csv/newline)", lines=2, value="")
                        components["composer_folder_paths"] = gr.Textbox(label="Folder paths (csv/newline)", lines=2, value="")
                        components["composer_exclude_paths"] = gr.Textbox(label="Exclude image paths (csv/newline)", lines=2, value="")
                        components["composer_recursive"] = gr.Checkbox(label="Include subfolders", value=True)
                        with gr.Row():
                            components["composer_preset_name"] = gr.Textbox(label="Save preset as", value="")
                            components["composer_preset_select"] = gr.Dropdown(label="Saved presets", choices=sorted(load_presets().keys()), value=None)
                        with gr.Row():
                            components["composer_preview_btn"] = gr.Button("Validate + Preview", elem_classes=["secondary-btn"])
                            components["composer_save_preset_btn"] = gr.Button("Save Preset", elem_classes=["secondary-btn"])
                        components["composer_preview_html"] = gr.HTML("<p class='section-microcopy'>Compose selectors and preview count before submit.</p>")

                # PANEL: Pipeline Progress
                with gr.Group(elem_classes=["panel"]):
                    gr.HTML(
                        """
                        <div class="panel-header">
                            <h2 class="panel-title">Pipeline / WorkflowRun Progress</h2>
                        </div>
                        <div class="pipeline-overview" role="region" aria-label="Pipeline workflow explanation">
                            <p class="section-microcopy">
                                <strong>5 stages (StageRuns)</strong> execute in order: <strong>1. Discovery</strong> (scan and register images) →
                                <strong>2. Inspection</strong> (extract EXIF/XMP) →
                                <strong>3. Quality Analysis</strong> (AI quality scores) →
                                <strong>4. Similarity Clustering</strong> (pick best per stack) →
                                <strong>5. Tagging</strong> (keywords/captions). Each StageRun shows <em>done / total</em> work items.
                                Discovery and Inspection run inside Quality Analysis; counts can differ until scoring finishes.
                            </p>
                        </div>
                        """
                    )
                    with gr.Column(elem_classes=["panel-body"]):
                        components["stepper_html"] = gr.HTML(_build_pipeline_stepper_html(None))
                        with gr.Row(elem_classes=["pipeline-actions"]):
                            components["run_all_btn"] = gr.Button("Queue All Pending", variant="primary", elem_classes=["primary-btn"])
                            components["stop_all_btn"] = gr.Button("Cancel Active Run", variant="stop", elem_classes=["danger-btn"])
                            components["run_metadata_btn"] = gr.Button("Run Inspection", variant="secondary", elem_classes=["secondary-btn"])
                        gr.HTML(
                            "<p class='section-microcopy'>"
                            "<strong>Queue All Pending</strong> \u2014 starts pending StageRuns in this WorkflowRun for the selected WorkspaceTarget. "
                            "<strong>Cancel Active Run</strong> \u2014 halts the active WorkflowRun; StageRun progress is preserved. "
                            "<strong>Run Inspection</strong> \u2014 runs the Inspection StageRun (EXIF/XMP + thumbnails) for WorkspaceTarget items missing metadata."
                            "</p>"
                        )
                        # Stop All confirmation (hidden until Stop All clicked)
                        with gr.Row(visible=False, elem_classes=["confirm-row"]) as stop_confirm_row:
                            gr.HTML(
                                "<span class='confirm-text'>"
                                "This will cancel the active run immediately. The current batch will not complete."
                                "</span>"
                            )
                            stop_confirm_yes = gr.Button("Yes, Cancel Run", elem_classes=["danger-btn"], size="sm")
                            stop_confirm_cancel = gr.Button("Cancel", elem_classes=["secondary-btn"], size="sm")
                        components["stop_confirm_row"] = stop_confirm_row
                        components["stop_confirm_yes"] = stop_confirm_yes
                        components["stop_confirm_cancel"] = stop_confirm_cancel

                        with gr.Row():
                            components["skip_reason"] = gr.Textbox(label="Skip reason", value="", placeholder="optional reason")
                            components["skip_actor"] = gr.Textbox(label="Actor", value="ui_user", placeholder="who skipped")
                        with gr.Group(elem_classes=["panel"]):
                            gr.Markdown("#### Scoped Controls")
                            with gr.Row():
                                components["run_pause_btn"] = gr.Button("Pause Run", elem_classes=["secondary-btn"])
                                components["run_cancel_btn"] = gr.Button("Cancel Run", elem_classes=["danger-btn"])
                                components["run_restart_btn"] = gr.Button("Restart Run", elem_classes=["danger-btn"])
                            with gr.Row(visible=False, elem_classes=["confirm-row"]) as run_pause_confirm_row:
                                gr.HTML("<span class='confirm-text'>Pause current run? You can resume by pressing Run All Pending.</span>")
                                run_pause_yes = gr.Button("Yes, Pause", elem_classes=["secondary-btn"], size="sm")
                                run_pause_cancel = gr.Button("Cancel", elem_classes=["secondary-btn"], size="sm")
                            components["run_pause_confirm_row"] = run_pause_confirm_row
                            components["run_pause_yes"] = run_pause_yes
                            components["run_pause_cancel"] = run_pause_cancel

                            with gr.Row():
                                components["run_strong_confirm_text"] = gr.Textbox(
                                    label="Strong confirm",
                                    placeholder="Type CANCEL or RESTART to enable destructive actions",
                                    value="",
                                )
                            with gr.Row(visible=False, elem_classes=["confirm-row"]) as run_cancel_confirm_row:
                                gr.HTML("<span class='confirm-text'>Cancel is destructive: queued work is dropped and active work is stopped.</span>")
                                run_cancel_yes = gr.Button("Yes, Cancel Run", elem_classes=["danger-btn"], size="sm")
                                run_cancel_cancel = gr.Button("Cancel", elem_classes=["secondary-btn"], size="sm")
                            components["run_cancel_confirm_row"] = run_cancel_confirm_row
                            components["run_cancel_yes"] = run_cancel_yes
                            components["run_cancel_cancel"] = run_cancel_cancel

                            with gr.Row(visible=False, elem_classes=["confirm-row"]) as run_restart_confirm_row:
                                gr.HTML("<span class='confirm-text'>Restart is destructive: in-flight progress may be interrupted.</span>")
                                run_restart_yes = gr.Button("Yes, Restart Run", elem_classes=["danger-btn"], size="sm")
                                run_restart_cancel = gr.Button("Cancel", elem_classes=["secondary-btn"], size="sm")
                            components["run_restart_confirm_row"] = run_restart_confirm_row
                            components["run_restart_yes"] = run_restart_yes
                            components["run_restart_cancel"] = run_restart_cancel

                            with gr.Row():
                                components["restart_stage"] = gr.Dropdown(
                                    choices=["scoring", "culling", "keywords"],
                                    value="scoring",
                                    label="Restart from stage",
                                )
                                components["restart_stage_btn"] = gr.Button("Restart From Stage", elem_classes=["danger-btn"])

                            with gr.Row():
                                components["step_image_id"] = gr.Number(label="Step image_id", precision=0)
                                components["step_phase_code"] = gr.Dropdown(
                                    choices=["indexing", "metadata", "scoring", "culling", "keywords"],
                                    value="metadata",
                                    label="Step phase",
                                )
                                components["step_rerun_btn"] = gr.Button("Rerun Failed Step", elem_classes=["secondary-btn"])

                # PANEL: Stages (Card Grid)
                with gr.Group(elem_classes=["panel"]):
                    with gr.Row(elem_classes=["panel-body", "phase-grid"]):

                        # Scoring Card
                        with gr.Column(elem_classes=["phase-card"]):
                            components["scoring_card_html"] = gr.HTML(_build_phase_card_html("Quality Analysis", "Not Started", 0, 0))
                            components["scoring_run_btn"] = gr.Button("Run Quality Analysis", elem_classes=["secondary-btn"])
                            with gr.Accordion("Options", open=False, elem_classes=["options-accordion"]):
                                components["scoring_force"] = gr.Checkbox(label="Force Re-score", value=False)
                            components["scoring_skip_btn"] = gr.Button("Skip Quality Analysis", elem_classes=["danger-btn"])
                            with gr.Row(visible=False, elem_classes=["confirm-row"]) as scoring_skip_confirm:
                                gr.HTML("<span class='confirm-text'>Marks Quality Analysis as skipped for this scope.</span>")
                                scoring_skip_yes = gr.Button("Yes, Skip", elem_classes=["danger-btn"], size="sm")
                                scoring_skip_cancel = gr.Button("Cancel", elem_classes=["secondary-btn"], size="sm")
                            components["scoring_skip_confirm"] = scoring_skip_confirm
                            components["scoring_skip_yes"] = scoring_skip_yes
                            components["scoring_skip_cancel"] = scoring_skip_cancel
                            components["scoring_retry_btn"] = gr.Button("Retry Skipped", elem_classes=["secondary-btn"])
                            gr.HTML("<p class='action-help'>Run \u2014 scores unprocessed images. Skip \u2014 marks done without running. Retry \u2014 re-queues skipped.</p>")

                        # Culling Card
                        with gr.Column(elem_classes=["phase-card"]):
                            components["culling_card_html"] = gr.HTML(_build_phase_card_html("Similarity Clustering", "Not Started", 0, 0))
                            components["culling_run_btn"] = gr.Button("Run Similarity Clustering", elem_classes=["secondary-btn"])
                            with gr.Accordion("Options", open=False, elem_classes=["options-accordion"]):
                                components["culling_force"] = gr.Checkbox(label="Force Re-run", value=False)
                            components["culling_skip_btn"] = gr.Button("Skip Similarity Clustering", elem_classes=["danger-btn"])
                            with gr.Row(visible=False, elem_classes=["confirm-row"]) as culling_skip_confirm:
                                gr.HTML("<span class='confirm-text'>Marks Similarity Clustering as skipped for this scope.</span>")
                                culling_skip_yes = gr.Button("Yes, Skip", elem_classes=["danger-btn"], size="sm")
                                culling_skip_cancel = gr.Button("Cancel", elem_classes=["secondary-btn"], size="sm")
                            components["culling_skip_confirm"] = culling_skip_confirm
                            components["culling_skip_yes"] = culling_skip_yes
                            components["culling_skip_cancel"] = culling_skip_cancel
                            components["culling_retry_btn"] = gr.Button("Retry Skipped", elem_classes=["secondary-btn"])
                            gr.HTML("<p class='action-help'>Run \u2014 selects picks by composition score. Skip \u2014 marks done. Retry \u2014 re-runs on skipped.</p>")

                        # Keywords Card
                        with gr.Column(elem_classes=["phase-card"]):
                            components["keywords_card_html"] = gr.HTML(_build_phase_card_html("Tagging", "Not Started", 0, 0))
                            components["keywords_run_btn"] = gr.Button("Run Tagging", elem_classes=["secondary-btn"])
                            with gr.Accordion("Options", open=False, elem_classes=["options-accordion"]):
                                components["keywords_overwrite"] = gr.Checkbox(label="Overwrite Existing", value=False)
                                components["keywords_captions"] = gr.Checkbox(label="Generate Captions", value=False)
                            components["keywords_skip_btn"] = gr.Button("Skip Tagging", elem_classes=["danger-btn"])
                            with gr.Row(visible=False, elem_classes=["confirm-row"]) as keywords_skip_confirm:
                                gr.HTML("<span class='confirm-text'>Marks Tagging as skipped for this scope.</span>")
                                keywords_skip_yes = gr.Button("Yes, Skip", elem_classes=["danger-btn"], size="sm")
                                keywords_skip_cancel = gr.Button("Cancel", elem_classes=["secondary-btn"], size="sm")
                            components["keywords_skip_confirm"] = keywords_skip_confirm
                            components["keywords_skip_yes"] = keywords_skip_yes
                            components["keywords_skip_cancel"] = keywords_skip_cancel
                            components["keywords_retry_btn"] = gr.Button("Retry Skipped", elem_classes=["secondary-btn"])
                            gr.HTML("<p class='action-help'>Run \u2014 generates keyword tags. Skip \u2014 skips tagging. Retry \u2014 re-tags skipped.</p>")

                # PANEL: Active Job Monitor
                with gr.Group(elem_classes=["panel", "monitor-card"]):
                    components["monitor_html"] = gr.HTML(_build_idle_html(recovery_info=app_config.get("job_recovery"), queued_jobs=[]))
                    components["action_snackbar"] = gr.Textbox(
                        label="Action status",
                        value="",
                        interactive=False,
                        elem_classes=["section-microcopy"],
                    )
                    with gr.Accordion("Console Output", open=False):
                        components["console_output"] = gr.Textbox(
                            lines=12, label="", max_lines=12, interactive=False, elem_classes=["console-code"]
                        )

                # PANEL: Telemetry
                with gr.Group(elem_classes=["panel", "telemetry-card"]):
                    gr.HTML("<div class='panel-header'><h2 class='panel-title'>Telemetry</h2></div>")
                    with gr.Row(elem_classes=["pipeline-actions"]):
                        components["telemetry_collapse_noisy"] = gr.Checkbox(label="Collapse noisy per-image logs", value=True)
                        components["telemetry_pin_critical"] = gr.Checkbox(label="Pin critical failures", value=True)
                    components["telemetry_html"] = gr.HTML(_build_telemetry_html([], collapse_noisy=True, pin_critical=True))
                    components["telemetry_state"] = gr.State({"last_seq": 0, "last_runner_log": "", "last_running": False, "events": []})

    def _sync_composer_path(path):
        return path or ""

    # Wire up folder selection to update HTML rendering (force_refresh to avoid stale cache)
    components["selected_path"].change(
        fn=lambda p: _update_folder_selection(p, force_refresh=True)[:6],
        inputs=[components["selected_path"]],
        outputs=[
            components["folder_summary_html"],
            components["stepper_html"],
            components["scoring_card_html"],
            components["culling_card_html"],
            components["keywords_card_html"],
            components["quick_start_html"],
        ]
    ).then(
        fn=_sync_composer_path,
        inputs=[components["selected_path"]],
        outputs=[components["composer_input_path"]],
    )

    def _on_refresh_click(selected_path):
        """Refresh tree and invalidate folder phase cache so next fetch is live."""
        if selected_path and selected_path.strip():
            db.invalidate_folder_phase_aggregates(folder_path=selected_path)
        tree_html = ui_tree.get_tree_html()
        folder_outputs = _update_folder_selection(selected_path or "", force_refresh=True)
        # Outputs: tree_view + 6 UI components (folder_outputs has 7th elem total_count for internal use)
        return (tree_html,) + folder_outputs[:6]


    components["refresh_btn"].click(
        fn=_on_refresh_click,
        inputs=[components["selected_path"]],
        outputs=[
            components["tree_view"],
            components["folder_summary_html"],
            components["stepper_html"],
            components["scoring_card_html"],
            components["culling_card_html"],
            components["keywords_card_html"],
            components["quick_start_html"],
        ],
    ).then(
        fn=_sync_composer_path,
        inputs=[components["selected_path"]],
        outputs=[components["composer_input_path"]],
    )

    def _compose_request(input_path, image_ids, image_paths, folder_ids, folder_paths, exclude_paths, recursive):
        return compose_selector_request(
            input_path=input_path,
            image_ids_raw=image_ids,
            image_paths_raw=image_paths,
            folder_ids_raw=folder_ids,
            folder_paths_raw=folder_paths,
            exclude_image_paths_raw=exclude_paths,
            recursive=recursive,
        )

    def _preview_composer(input_path, image_ids, image_paths, folder_ids, folder_paths, exclude_paths, recursive):
        request = _compose_request(input_path, image_ids, image_paths, folder_ids, folder_paths, exclude_paths, recursive)
        preview = validate_and_preview(request)
        warning_items = ''.join(f"<li>{w}</li>" for w in (preview.get("warnings") or [])) or "<li>None</li>"
        return (
            "<div class='section-microcopy'>"
            f"<p><strong>Preview count:</strong> {preview.get('preview_count', 0)}</p>"
            "<p><strong>Conflict warnings</strong></p>"
            f"<ul>{warning_items}</ul>"
            "</div>"
        )

    def _save_composer_preset(name, input_path, image_ids, image_paths, folder_ids, folder_paths, exclude_paths, recursive):
        request = _compose_request(input_path, image_ids, image_paths, folder_ids, folder_paths, exclude_paths, recursive)
        presets = save_preset(name, request)
        return gr.update(choices=sorted(presets.keys()), value=name.strip() if name else None)

    def _load_composer_preset(name):
        presets = load_presets()
        request = presets.get(name or "", {})
        return (
            request.get("input_path") or "",
            ",".join(str(v) for v in (request.get("image_ids") or [])),
            "\n".join(request.get("image_paths") or []),
            ",".join(str(v) for v in (request.get("folder_ids") or [])),
            "\n".join(request.get("folder_paths") or []),
            "\n".join(request.get("exclude_image_paths") or []),
            bool(request.get("recursive", True)),
        )


    # --- Run button handlers ---
    # All runners use start_batch(input_path, job_id, **kwargs)

    def _run_scoring(path, force):
        if not path:
            return
        db.enqueue_job(
            path,
            phase_code="scoring",
            job_type="scoring",
            queue_payload={"input_path": path, "skip_existing": not force},
        )

    def _run_metadata(path):
        """Run indexing and metadata extraction only (no scoring)."""
        if not path:
            return
        db.enqueue_job(
            path,
            phase_code="scoring",
            job_type="scoring",
            queue_payload={
                "input_path": path,
                "skip_existing": False,
                "target_phases": ["indexing", "metadata"],
            },
        )

    def _run_culling(path, force):
        if not path:
            return
        db.enqueue_job(
            path,
            phase_code="culling",
            job_type="selection",
            queue_payload={"input_path": path, "force_rescan": force},
        )

    def _run_tagging(path, overwrite, captions):
        if not path:
            return
        db.enqueue_job(
            path,
            phase_code="keywords",
            job_type="tagging",
            queue_payload={"input_path": path, "overwrite": overwrite, "generate_captions": captions},
        )


    def _stop_runner_for_phase(phase_code):
        if phase_code == "scoring":
            scoring_runner.stop()
        elif phase_code == "culling":
            selection_runner.stop()
        elif phase_code == "keywords":
            tagging_runner.stop()

    def _skip_phase(path, phase_code, reason, actor):
        if not path:
            return
        _stop_runner_for_phase(phase_code)
        db.set_folder_phase_status(
            folder_path=path,
            phase_code=phase_code,
            status="skipped",
            reason=reason or "manual_skip",
            actor=actor or "ui_user",
        )

    def _retry_phase(path, phase_code):
        if not path:
            return
        db.set_folder_phase_status(
            folder_path=path,
            phase_code=phase_code,
            status="running",
        )
        if phase_code == "scoring":
            _run_scoring(path, force=False)
        elif phase_code == "culling":
            _run_culling(path, force=True)
        elif phase_code == "keywords":
            _run_tagging(path, overwrite=False, captions=False)

    def _run_all_pending(path):
        if not path:
            return
        orchestrator.start(path)

    def _pipeline_action_result(message, level="info"):
        rollback = "Rollback: use Retry Stage or Restart From Stage to recover."
        return f"[{level.upper()}] {message} | {rollback}"

    def _stop_all():
        orchestrator.stop()
        # Also stop individual runners in case they were started independently
        scoring_runner.stop()
        selection_runner.stop()
        tagging_runner.stop()

    def _pause_run():
        _stop_all()
        return _pipeline_action_result("Run paused", level="soft")

    def _cancel_run(path):
        _stop_all()
        if path:
            for job in db.get_queued_jobs(limit=500):
                input_path = str(job.get("input_path") or "")
                if input_path.startswith(path):
                    db.request_cancel_job(job.get("id"))
        return _pipeline_action_result("Run canceled", level="strong")

    def _restart_run(path):
        _stop_all()
        if path:
            orchestrator.start(path)
        return _pipeline_action_result("Run restarted", level="strong")

    def _restart_from_stage(path, phase_code):
        if not path:
            return _pipeline_action_result("Select a folder first", level="warn")
        ordered = ["scoring", "culling", "keywords"]
        phase = (phase_code or "scoring").strip().lower()
        if phase not in ordered:
            return _pipeline_action_result(f"Unsupported stage: {phase_code}", level="warn")

        start = ordered.index(phase)
        for code in ordered[start:]:
            db.set_folder_phase_status(folder_path=path, phase_code=code, status="running")

        if phase == "scoring":
            _run_scoring(path, force=True)
        elif phase == "culling":
            _run_culling(path, force=True)
        elif phase == "keywords":
            _run_tagging(path, overwrite=True, captions=False)

        return _pipeline_action_result(f"Restarted from stage: {phase}", level="strong")

    def _rerun_step(image_id, phase_code):
        if image_id is None:
            return _pipeline_action_result("Provide image_id", level="warn")
        phase = (phase_code or "").strip().lower()
        # Conservative idempotency allow-list for targeted per-step rerun
        idempotent_phases = {"metadata", "keywords", "culling"}
        if phase not in idempotent_phases:
            return _pipeline_action_result(f"Step rerun blocked for non-idempotent phase: {phase}", level="warn")

        img_id = int(image_id)
        statuses = db.get_image_phase_statuses(img_id) or []
        phase_row = next((row for row in statuses if str(row.get("phase_code") or "").lower() == phase), None)
        current_status = str((phase_row or {}).get("status") or "not_started").lower()
        if current_status != "failed":
            return _pipeline_action_result(
                f"Step rerun requires failed status. Current status for phase '{phase}' is '{current_status}'",
                level="warn",
            )

        db.set_image_phase_status(img_id, phase, "running")
        return _pipeline_action_result(f"Marked image {img_id} phase '{phase}' for rerun", level="info")

    components["scoring_run_btn"].click(
        fn=_run_scoring,
        inputs=[components["selected_path"], components["scoring_force"]],
        outputs=[]
    )
    components["culling_run_btn"].click(
        fn=_run_culling,
        inputs=[components["selected_path"], components["culling_force"]],
        outputs=[]
    )
    components["keywords_run_btn"].click(
        fn=_run_tagging,
        inputs=[components["selected_path"], components["keywords_overwrite"], components["keywords_captions"]],
        outputs=[]
    )
    components["run_all_btn"].click(
        fn=_run_all_pending,
        inputs=[components["selected_path"]],
        outputs=[]
    )
    components["run_metadata_btn"].click(
        fn=_run_metadata,
        inputs=[components["selected_path"]],
        outputs=[]
    )
    # Stop All: two-step confirmation
    components["stop_all_btn"].click(
        fn=lambda: gr.update(visible=True),
        inputs=[],
        outputs=[components["stop_confirm_row"]],
    )
    components["stop_confirm_cancel"].click(
        fn=lambda: gr.update(visible=False),
        inputs=[],
        outputs=[components["stop_confirm_row"]],
    )
    components["stop_confirm_yes"].click(
        fn=_stop_all,
        inputs=[],
        outputs=[],
    ).then(
        fn=lambda: gr.update(visible=False),
        inputs=[],
        outputs=[components["stop_confirm_row"]],
    )

    # Scoring skip: two-step confirmation
    components["scoring_skip_btn"].click(
        fn=lambda: gr.update(visible=True),
        inputs=[],
        outputs=[components["scoring_skip_confirm"]],
    )
    components["scoring_skip_cancel"].click(
        fn=lambda: gr.update(visible=False),
        inputs=[],
        outputs=[components["scoring_skip_confirm"]],
    )
    components["scoring_skip_yes"].click(
        fn=lambda p, r, a: _skip_phase(p, "scoring", r, a),
        inputs=[components["selected_path"], components["skip_reason"], components["skip_actor"]],
        outputs=[],
    ).then(
        fn=lambda: gr.update(visible=False),
        inputs=[],
        outputs=[components["scoring_skip_confirm"]],
    )

    # Culling skip: two-step confirmation
    components["culling_skip_btn"].click(
        fn=lambda: gr.update(visible=True),
        inputs=[],
        outputs=[components["culling_skip_confirm"]],
    )
    components["culling_skip_cancel"].click(
        fn=lambda: gr.update(visible=False),
        inputs=[],
        outputs=[components["culling_skip_confirm"]],
    )
    components["culling_skip_yes"].click(
        fn=lambda p, r, a: _skip_phase(p, "culling", r, a),
        inputs=[components["selected_path"], components["skip_reason"], components["skip_actor"]],
        outputs=[],
    ).then(
        fn=lambda: gr.update(visible=False),
        inputs=[],
        outputs=[components["culling_skip_confirm"]],
    )

    # Keywords skip: two-step confirmation
    components["keywords_skip_btn"].click(
        fn=lambda: gr.update(visible=True),
        inputs=[],
        outputs=[components["keywords_skip_confirm"]],
    )
    components["keywords_skip_cancel"].click(
        fn=lambda: gr.update(visible=False),
        inputs=[],
        outputs=[components["keywords_skip_confirm"]],
    )
    components["keywords_skip_yes"].click(
        fn=lambda p, r, a: _skip_phase(p, "keywords", r, a),
        inputs=[components["selected_path"], components["skip_reason"], components["skip_actor"]],
        outputs=[],
    ).then(
        fn=lambda: gr.update(visible=False),
        inputs=[],
        outputs=[components["keywords_skip_confirm"]],
    )
    components["scoring_retry_btn"].click(
        fn=lambda p: _retry_phase(p, "scoring"),
        inputs=[components["selected_path"]],
        outputs=[]
    )
    components["culling_retry_btn"].click(
        fn=lambda p: _retry_phase(p, "culling"),
        inputs=[components["selected_path"]],
        outputs=[]
    )
    components["keywords_retry_btn"].click(
        fn=lambda p: _retry_phase(p, "keywords"),
        inputs=[components["selected_path"]],
        outputs=[]
    )

    # Scoped run controls with confirmation levels
    components["run_pause_btn"].click(
        fn=lambda: gr.update(visible=True),
        inputs=[],
        outputs=[components["run_pause_confirm_row"]],
    )
    components["run_pause_cancel"].click(
        fn=lambda: gr.update(visible=False),
        inputs=[],
        outputs=[components["run_pause_confirm_row"]],
    )
    components["run_pause_yes"].click(
        fn=_pause_run,
        inputs=[],
        outputs=[components["action_snackbar"]],
    ).then(
        fn=lambda: gr.update(visible=False),
        inputs=[],
        outputs=[components["run_pause_confirm_row"]],
    )

    components["run_cancel_btn"].click(
        fn=lambda txt: gr.update(visible=(txt or "").strip().upper() == "CANCEL"),
        inputs=[components["run_strong_confirm_text"]],
        outputs=[components["run_cancel_confirm_row"]],
    )
    components["run_cancel_cancel"].click(
        fn=lambda: gr.update(visible=False),
        inputs=[],
        outputs=[components["run_cancel_confirm_row"]],
    )
    components["run_cancel_yes"].click(
        fn=_cancel_run,
        inputs=[components["selected_path"]],
        outputs=[components["action_snackbar"]],
    ).then(
        fn=lambda: gr.update(visible=False),
        inputs=[],
        outputs=[components["run_cancel_confirm_row"]],
    )

    components["run_restart_btn"].click(
        fn=lambda txt: gr.update(visible=(txt or "").strip().upper() == "RESTART"),
        inputs=[components["run_strong_confirm_text"]],
        outputs=[components["run_restart_confirm_row"]],
    )
    components["run_restart_cancel"].click(
        fn=lambda: gr.update(visible=False),
        inputs=[],
        outputs=[components["run_restart_confirm_row"]],
    )
    components["run_restart_yes"].click(
        fn=_restart_run,
        inputs=[components["selected_path"]],
        outputs=[components["action_snackbar"]],
    ).then(
        fn=lambda: gr.update(visible=False),
        inputs=[],
        outputs=[components["run_restart_confirm_row"]],
    )

    components["restart_stage_btn"].click(
        fn=_restart_from_stage,
        inputs=[components["selected_path"], components["restart_stage"]],
        outputs=[components["action_snackbar"]],
    )
    components["step_rerun_btn"].click(
        fn=_rerun_step,
        inputs=[components["step_image_id"], components["step_phase_code"]],
        outputs=[components["action_snackbar"]],
    )

    components["composer_preview_btn"].click(
        fn=_preview_composer,
        inputs=[
            components["composer_input_path"],
            components["composer_image_ids"],
            components["composer_image_paths"],
            components["composer_folder_ids"],
            components["composer_folder_paths"],
            components["composer_exclude_paths"],
            components["composer_recursive"],
        ],
        outputs=[components["composer_preview_html"]],
    )
    components["composer_save_preset_btn"].click(
        fn=_save_composer_preset,
        inputs=[
            components["composer_preset_name"],
            components["composer_input_path"],
            components["composer_image_ids"],
            components["composer_image_paths"],
            components["composer_folder_ids"],
            components["composer_folder_paths"],
            components["composer_exclude_paths"],
            components["composer_recursive"],
        ],
        outputs=[components["composer_preset_select"]],
    )
    components["composer_preset_select"].change(
        fn=_load_composer_preset,
        inputs=[components["composer_preset_select"]],
        outputs=[
            components["composer_input_path"],
            components["composer_image_ids"],
            components["composer_image_paths"],
            components["composer_folder_ids"],
            components["composer_folder_paths"],
            components["composer_exclude_paths"],
            components["composer_recursive"],
        ],
    )

    return components


def _update_folder_selection(folder_path: str, force_refresh=False, is_running=False):
    """Updates the static UI components when a new folder is selected.

    Returns: (summary_html, stepper_html, scoring_card, culling_card, keywords_card, quick_start_html, total_count)
    """
    if not folder_path:
        return (
            _build_folder_summary(None, 0),
            _build_pipeline_stepper_html(None),
            _build_phase_card_html("Quality Analysis", "Not Started", 0, 0),
            _build_phase_card_html("Similarity Clustering", "Not Started", 0, 0),
            _build_phase_card_html("Tagging", "Not Started", 0, 0),
            _build_quick_start_html(None, is_running=is_running),
            0,
        )

    summary_by_code, total_count = _parse_phase_summary(folder_path, force_refresh=force_refresh)

    sc = summary_by_code.get("scoring", {})
    cu = summary_by_code.get("culling", {})
    kw = summary_by_code.get("keywords", {})

    return (
        _build_folder_summary(folder_path, total_count),
        _build_pipeline_stepper_html(folder_path, summary_by_code, total_count),
        _build_phase_card_html("Quality Analysis", sc.get("status", "not_started"), sc.get("done_count", 0), total_count),
        _build_phase_card_html("Similarity Clustering", cu.get("status", "not_started"), cu.get("done_count", 0), total_count),
        _build_phase_card_html("Tagging", kw.get("status", "not_started"), kw.get("done_count", 0), total_count),
        _build_quick_start_html(folder_path, summary_by_code, is_running=is_running),
        total_count,
    )


def get_status_update(scoring_runner, tagging_runner, selection_runner, orchestrator, selected_folder, telemetry_state, collapse_noisy, pin_critical):
    """Called regularly by the main app timer to update components."""
    # Process Orchestrator tick
    orchestrator.on_tick()

    is_running, mon_name, mon_msg, mon_cur, mon_tot, console_out, pipeline_depth = _unified_monitor_status(
        scoring_runner, tagging_runner, selection_runner
    )

    queued_jobs = db.get_queued_jobs(limit=50, include_related=True)

    telemetry_state = telemetry_state or {}
    telemetry_events = list(telemetry_state.get("events", []))

    # Poll persisted telemetry from DB/runners broadcast points
    last_seq = telemetry_state.get("last_seq", 0)
    event_batch = db.get_pipeline_events(since_seq=last_seq, limit=300)
    telemetry_events.extend(event_batch.get("events", []))
    telemetry_state["last_seq"] = event_batch.get("latest_seq", last_seq)

    # Ingest runner status stream into telemetry events (progress/log)
    log_text = console_out or ""
    prev_log = telemetry_state.get("last_runner_log", "")
    if log_text != prev_log:
        new_lines = [ln for ln in log_text[len(prev_log):].splitlines() if ln.strip()] if log_text.startswith(prev_log) else [ln for ln in log_text.splitlines() if ln.strip()]
        for line in new_lines[-80:]:
            sev = "error" if "error" in line.lower() else ("warning" if "warn" in line.lower() else "info")
            telemetry_events.append({
                "event_type": "log" if sev == "info" else ("error" if sev == "error" else "log"),
                "message": line,
                "severity": sev,
                "workflow_run": None,
                "stage_run": mon_name.lower() if mon_name else None,
                "step_run": "runner:log",
                "category": "runner-log",
                "critical": sev == "error",
                "noisy": True,
                "source": "runner.get_status",
                "timestamp": "",
                "seq": 0,
            })
    telemetry_state["last_runner_log"] = log_text

    # State transitions from runner polling
    if telemetry_state.get("last_running") != is_running:
        telemetry_events.append({
            "event_type": "state-change",
            "message": "Pipeline run started" if is_running else "Pipeline run became idle",
            "severity": "info",
            "workflow_run": None,
            "stage_run": mon_name.lower() if mon_name else "pipeline",
            "step_run": "runner:state",
            "category": "phase-transition",
            "critical": False,
            "noisy": False,
            "source": "runner.get_status",
            "timestamp": "",
            "seq": 0,
        })
    telemetry_state["last_running"] = is_running

    # Throughput counter from monitor values
    if is_running and mon_tot > 0:
        telemetry_events.append({
            "event_type": "progress",
            "message": f"{mon_name}: {mon_cur}/{mon_tot}",
            "severity": "info",
            "workflow_run": None,
            "stage_run": mon_name.lower() if mon_name else None,
            "step_run": "runner:throughput",
            "category": "throughput",
            "critical": False,
            "noisy": True,
            "source": "get_status_update",
            "timestamp": "",
            "seq": 0,
        })

    if len(telemetry_events) > 600:
        telemetry_events = telemetry_events[-600:]
    telemetry_state["events"] = telemetry_events
    telemetry_html = _build_telemetry_html(telemetry_events, collapse_noisy=bool(collapse_noisy), pin_critical=bool(pin_critical))

    # Rebuild stepper/cards from current folder state (force_refresh when running for real-time updates)
    res_summary, res_stepper, res_sc, res_cu, res_kw, res_qs, folder_total = _update_folder_selection(
        selected_folder, force_refresh=is_running, is_running=is_running
    )

    if is_running:
        monitor_html = _build_monitor_html(
            mon_name, mon_msg, mon_cur, mon_tot, queued_jobs,
            folder_total=folder_total, pipeline_depth=pipeline_depth
        )
    else:
        status = orchestrator.get_status()
        monitor_html = _build_idle_html(
            recovery_info=status.get("recovery"),
            queued_jobs=queued_jobs,
        )

    not_running = not is_running

    # Return order must match monitor_outputs in app.py:
    # stepper, scoring_card, culling_card, keywords_card,
    # monitor, console, run_all, stop_all, sc_run, cu_run, kw_run, repair, run_meta, quick_start
    result = (
        res_stepper,
        res_sc,
        res_cu,
        res_kw,
        monitor_html,
        console_out,
        gr.update(interactive=not_running),  # run_all
        gr.update(interactive=is_running),   # stop_all
        gr.update(interactive=not_running),  # scoring_run
        gr.update(interactive=not_running),  # culling_run
        gr.update(interactive=not_running),  # keywords_run
        gr.update(interactive=not_running),  # repair_index_meta
        gr.update(interactive=not_running),  # run_metadata
        res_qs,                              # quick_start
        telemetry_html,
        telemetry_state,
    )

    # Skip SSE push if nothing changed since last tick
    cache_key = (res_stepper, res_sc, res_cu, res_kw, monitor_html, console_out, is_running, telemetry_html)
    if cache_key == _last_status_cache["state"]:
        return tuple(gr.skip() for _ in range(16))
    _last_status_cache["state"] = cache_key

    return result


# --- HTML Helpers ---

def _unified_monitor_status(scoring_runner, tagging_runner, selection_runner):
    """Finds whichever runner is active and returns data for the live run monitor."""
    for runner_obj, name in [
        (scoring_runner, "Quality Analysis"),
        (selection_runner, "Similarity Clustering"),
        (tagging_runner, "Tagging"),
    ]:
        if not runner_obj:
            continue
        result = runner_obj.get_status()
        is_running, log, msg, cur, tot = result[:5]
        depth = result[5] if len(result) > 5 else 0
        if is_running:
            return True, name, msg, cur, tot, log, depth
    return False, "", "", 0, 0, "", 0


def get_runner_activity_snapshot(scoring_runner, tagging_runner, selection_runner, clustering_runner=None):
    """Return a plain-dict snapshot of all runner states for operator status pages."""
    is_running, name, msg, cur, tot, log, depth = _unified_monitor_status(
        scoring_runner, tagging_runner, selection_runner
    )
    runners = []
    for runner_obj, label in [
        (scoring_runner, "Quality Analysis"),
        (selection_runner, "Similarity Clustering"),
        (tagging_runner, "Tagging"),
        (clustering_runner, "Clustering"),
    ]:
        if runner_obj is None:
            continue
        result = runner_obj.get_status()
        r_running, r_log, r_msg, r_cur, r_tot = result[:5]
        runners.append({
            "name": label,
            "running": r_running,
            "message": r_msg,
            "current": r_cur,
            "total": r_tot,
            "log": r_log,
        })
    return {
        "any_running": is_running,
        "active_runner": name if is_running else None,
        "active_message": msg if is_running else "",
        "active_progress": f"{cur}/{tot}" if is_running and tot else "",
        "active_log": log if is_running else "",
        "runners": runners,
    }


def _build_quick_start_html(folder_path, summary_by_code=None, is_running=False):
    """Context-aware Quick Start guide: 1. Select scope → 2. Queue pending stages → 3. Review in Gallery."""
    summary_by_code = summary_by_code or {}

    if not folder_path:
        steps = [
            ("current", "Select a WorkspaceTarget (folder) from the tree"),
            ("", "Queue all pending stages"),
            ("", "Open Gallery and review results"),
        ]
    elif is_running:
        steps = [
            ("done", "WorkspaceTarget selected"),
            ("current", "WorkflowRun is running\u2026"),
            ("", "Open Gallery and review results"),
        ]
    else:
        pending = any(
            summary_by_code.get(c, {}).get("status") not in ("done", "skipped")
            for c in ("scoring", "culling", "keywords")
        )
        if pending:
            steps = [
                ("done", "WorkspaceTarget selected"),
                ("current", "Queue All Pending to process work items"),
                ("", "Open Gallery and review results"),
            ]
        else:
            steps = [
                ("done", "WorkspaceTarget selected"),
                ("done", "All stages complete"),
                ("current", "Open Gallery and review results"),
            ]

    parts = [
        "<div class='quick-start-panel'>",
        "<strong style='font-size:0.9rem;color:var(--text-primary)'>Quick Start</strong>",
        "<div class='quick-start-steps'>",
    ]
    for i, (state, label) in enumerate(steps):
        parts.append(
            f"<div class='qs-step {state}' role='listitem'>"
            f"<span class='qs-step-num'>{i + 1}</span>"
            f"<span>{label}</span>"
            f"</div>"
        )
        if i < len(steps) - 1:
            parts.append("<span class='qs-arrow' aria-hidden='true'>\u203a</span>")
    parts.append("</div></div>")
    return "".join(parts)


def _build_folder_summary(path, count):
    path_display = path if path else "-"
    return f"""
    <div class="folder-summary">
      <h3>Selected WorkspaceTarget (Folder)</h3>
      <p><strong>{path_display}</strong><br>{count} images</p>
    </div>
    """


def _format_queue_time(raw):
    if not raw:
        return "-"
    if isinstance(raw, datetime.datetime):
        return raw.strftime("%Y-%m-%d %H:%M:%S")
    try:
        return datetime.datetime.fromisoformat(str(raw)).strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return str(raw)


def _status_chip(status):
    norm = (status or "unknown").strip().lower()
    label = norm.replace("_", " ").title()
    return f"<span class='queue-chip queue-chip-{norm}'>{html.escape(label)}</span>"


def _render_queue_html(queued_jobs):
    if not queued_jobs:
        return "<p class='phase-stats'>Pipeline queue: empty</p>"

    rows = []
    for job in queued_jobs:
        status = (job.get("status") or "queued").strip().lower()
        job_id = job.get("id")
        rows.append(
            "<tr>"
            f"<td data-sort='{job.get('queue_position')}'>{html.escape(str(job.get('queue_position')))}</td>"
            f"<td data-sort='{job.get('priority')}'>{html.escape(str(job.get('priority')))}</td>"
            f"<td data-sort='{html.escape(str(job.get('enqueued_at') or ''))}'>{html.escape(_format_queue_time(job.get('enqueued_at')))}</td>"
            f"<td>{html.escape(str(job.get('target_scope') or '-'))}</td>"
            f"<td>{html.escape(str(job.get('selected_phases') or '-'))}</td>"
            f"<td>{html.escape(str(job.get('dependency_blockers') or 'None'))}</td>"
            f"<td data-sort='{html.escape(str(job.get('estimated_start') or ''))}'>{html.escape(_format_queue_time(job.get('estimated_start')))}</td>"
            f"<td data-sort='{job.get('retry_count')}'>{html.escape(str(job.get('retry_count') or 0))}</td>"
            f"<td>{_status_chip(status)}</td>"
            "<td class='queue-actions'>"
            f"<button class='queue-action-btn' data-job-id='{job_id}' data-action='bump_priority' {'disabled' if status not in ('queued', 'paused') else ''} title='Increase priority'>⬆ Priority</button>"
            f"<button class='queue-action-btn' data-job-id='{job_id}' data-action='pause' {'disabled' if status != 'queued' else ''} title='Pause item'>⏸ Pause</button>"
            f"<button class='queue-action-btn' data-job-id='{job_id}' data-action='cancel' {'disabled' if status not in ('queued','paused') else ''} title='Cancel item'>✖ Cancel</button>"
            f"<button class='queue-action-btn' data-job-id='{job_id}' data-action='restart' {'disabled' if status != 'failed' else ''} title='Restart failed'>↻ Restart</button>"
            "</td>"
            "</tr>"
        )

    return (
        "<div class='queue-board'>"
        "<div class='phase-stats'>Job queue board</div>"
        "<div class='queue-board-help section-microcopy'>Sortable columns: Position, Priority, Enqueue Time, ETA, Retry.</div>"
        "<div class='queue-table-wrap'>"
        "<table class='queue-table'>"
        "<thead><tr>"
        "<th data-sort-col='0'>Position</th>"
        "<th data-sort-col='1'>Priority</th>"
        "<th data-sort-col='2'>Enqueue Time</th>"
        "<th>Target Scope</th>"
        "<th>Selected Phases</th>"
        "<th>Dependency Blockers</th>"
        "<th data-sort-col='6'>Estimated Start</th>"
        "<th data-sort-col='7'>Retry</th>"
        "<th>Status</th>"
        "<th>Actions</th>"
        "</tr></thead>"
        f"<tbody>{''.join(rows)}</tbody>"
        "</table></div>"
        "<script>(function(){"
        "const root=document.currentScript.closest('.queue-board'); if(!root) return;"
        "const table=root.querySelector('.queue-table'); if(!table || table.dataset.enhanced==='1') return; table.dataset.enhanced='1';"
        "const headers=table.querySelectorAll('th[data-sort-col]');"
        "headers.forEach((th)=>th.addEventListener('click',()=>{"
        "const idx=parseInt(th.dataset.sortCol,10);"
        "const tbody=table.querySelector('tbody');"
        "const rows=Array.from(tbody.querySelectorAll('tr'));"
        "const asc=th.dataset.asc!=='1';"
        "headers.forEach((h)=>delete h.dataset.asc); th.dataset.asc=asc?'1':'0';"
        "rows.sort((a,b)=>{"
        "const va=(a.children[idx].dataset.sort||a.children[idx].innerText||'').trim();"
        "const vb=(b.children[idx].dataset.sort||b.children[idx].innerText||'').trim();"
        "const na=Number(va), nb=Number(vb);"
        "const cmp=(!Number.isNaN(na)&&!Number.isNaN(nb))?(na-nb):va.localeCompare(vb);"
        "return asc?cmp:-cmp;"
        "}); rows.forEach((r)=>tbody.appendChild(r));"
        "}));"
        "const endpoint=(action,jobId)=>{"
        "if(action==='cancel') return `/api/jobs/${jobId}/cancel`;"
        "if(action==='pause') return `/api/jobs/${jobId}/pause`;"
        "if(action==='restart') return `/api/jobs/${jobId}/restart`;"
        "if(action==='bump_priority') return `/api/jobs/${jobId}/priority?delta=10`;"
        "return null;"
        "};"
        "root.querySelectorAll('.queue-action-btn[data-action]').forEach((btn)=>{"
        "btn.addEventListener('click',async()=>{"
        "if(btn.disabled) return;"
        "const action=btn.dataset.action; const jobId=btn.dataset.jobId;"
        "const url=endpoint(action,jobId); if(!url) return;"
        "btn.disabled=true;"
        "try {"
        "const res=await fetch(url,{method:'POST'});"
        "if(!res.ok){ console.warn('Queue action failed', action, jobId); btn.disabled=false; return; }"
        "btn.textContent='✓';"
        "} catch(e){ console.warn('Queue action error', e); btn.disabled=false; }"
        "});"
        "});"
        "})();</script>"
        "</div>"
    )


def _build_idle_html(recovery_info=None, queued_jobs=None):
    base = "<div class='panel-body'><p>No active pipeline runs.</p>"
    if recovery_info:
        recovered = recovery_info.get("recovered_running_jobs") or []
        interrupted = recovery_info.get("interrupted_pipeline_jobs") or []
        auto_resumed = recovery_info.get("auto_resumed")
        if recovered or interrupted or auto_resumed:
            base += (
                f"<p><strong>Recovery:</strong> marked {len(recovered)} running job(s) as interrupted; "
                f"found {len(interrupted)} interrupted pipeline run(s); "
                f"auto-resumed: {'yes' if auto_resumed else 'no'}.</p>"
            )
    queued_jobs = queued_jobs or []
    return base + _render_queue_html(queued_jobs) + "</div>"


def _build_monitor_html(name, msg, current, total, queued_jobs=None, folder_total=None, pipeline_depth=0):
    """Build monitor HTML. Numbers show current batch progress; folder_total adds folder-scope context."""
    queued_jobs = queued_jobs or []
    pct = (current / total * 100) if total > 0 else 0
    batch_line = f"{msg} ({current}/{total})"
    folder_line = ""
    if folder_total is not None and folder_total > 0 and folder_total != total:
        folder_line = f"<p class='section-microcopy'>Batch: {current}/{total} · Folder total: {folder_total} images</p>"
    else:
        folder_line = "<p class='section-microcopy'>Processing images in current batch. See Console Output for per-image progress.</p>"
    pipeline_line = ""
    if pipeline_depth > 0:
        pipeline_line = f"<p class='section-microcopy'>Pipeline queue: {pipeline_depth} work item(s) pending</p>"
    return f"""
    <div class="panel-body">
      <div class="phase-head">
        <div class="phase-title">{name} Progress</div>
      </div>
      <div class="phase-stats">{batch_line}</div>
      {folder_line}
      {pipeline_line}
      <div class="progress"><div class="progress-fill" style="width: {pct:.1f}%;"></div></div>
      {_render_queue_html(queued_jobs)}
    </div>
    """


def _build_telemetry_html(events, collapse_noisy=True, pin_critical=True):
    events = events or []
    if not events:
        return "<div class='panel-body'><p class='section-microcopy'>No telemetry events yet.</p></div>"

    critical = [e for e in events if e.get("critical")]
    normal = [e for e in events if not e.get("critical")]
    noisy_count = 0
    if collapse_noisy:
        filtered = []
        for ev in normal:
            if ev.get("noisy") and ev.get("category") in ("runner-log", "phase", "throughput"):
                noisy_count += 1
                continue
            filtered.append(ev)
        normal = filtered

    ordered = (critical + normal) if pin_critical else events
    ordered = ordered[-120:]

    lines = ["<div class='panel-body'><div class='telemetry-list'>"]
    if noisy_count:
        lines.append(f"<p class='section-microcopy'>Collapsed {noisy_count} noisy event(s).</p>")

    for ev in ordered:
        etype = (ev.get("event_type") or "log").strip()
        severity = (ev.get("severity") or "info").strip()
        cls = f"telemetry-item telemetry-{severity}"
        run = " / ".join(x for x in [str(ev.get("workflow_run") or ""), str(ev.get("stage_run") or ""), str(ev.get("step_run") or "")] if x)
        run_html = f"<div class='section-microcopy'>{run}</div>" if run else ""
        stamp = ev.get("timestamp") or ""
        badge = "<span class='status-badge error'>PIN</span>" if ev.get("critical") else ""
        lines.append(
            f"<div class='{cls}'>"
            f"<div><strong>[{etype}]</strong> {ev.get('message','')}</div>"
            f"{run_html}"
            f"<div class='section-microcopy'>{stamp} · {ev.get('source','')}</div>"
            f"{badge}"
            f"</div>"
        )

    lines.append("</div></div>")
    return "".join(lines)


_STATUS_LABELS = {
    "done": "Done",
    "partial": "In Progress",
    "not_started": "Not Started",
    "failed": "Failed",
    "running": "Running",
    "queued": "Queued",
    "paused": "Paused",
    "cancel_requested": "Cancel Requested",
    "restarting": "Restarting",
    "skipped": "Skipped",
}


_STATUS_BADGE_CLASS = {
    "done": "success",
    "partial": "info",
    "running": "info",
    "queued": "info",
    "paused": "warning",
    "cancel_requested": "warning",
    "restarting": "info",
    "failed": "error",
    "skipped": "warning",
    "not_started": "",
}


def _build_phase_card_html(title, status, done, total):
    pct = (done / total * 100) if total > 0 else 0
    initial = title[0]
    status_label = _STATUS_LABELS.get(status, status.replace("_", " ").title())
    badge_class = _STATUS_BADGE_CLASS.get(status, "")
    badge_cls = f"phase-status status-badge {badge_class}" if badge_class else "phase-status"
    running_cls = " phase-card running" if status in ("running", "partial") else ""
    return f"""
    <div class="phase-card{running_cls}" role="region" aria-label="{title} stage: {status_label}">
      <div class="phase-head">
        <div class="phase-title">
          <div class="phase-icon">{initial}</div>
          {title}
        </div>
        <div class="{badge_cls}">{status_label}</div>
      </div>
      <div class="phase-stats">{done}/{total} work items processed</div>
      <div class="progress"><div class="progress-fill" style="width: {pct:.1f}%;"></div></div>
    </div>
    """


def _build_pipeline_stepper_html(folder_path, summary_by_code=None, total=0):
    if not folder_path:
        return "<p>Select a WorkspaceTarget from the tree to view pipeline progress.</p>"

    if not summary_by_code or total == 0:
        return (
            "<p class='section-microcopy'>No images in this folder. "
            "Run Quality Analysis first to index images from disk.</p>"
        )

    phase_defs = db.get_all_phases(enabled_only=True) or []
    if not phase_defs:
        return "<p class='section-microcopy'>No enabled phases found.</p>"

    summary_by_code = summary_by_code or {}
    registry = {}
    for executor in PhaseRegistry.get_all():
        code = executor.code.value if hasattr(executor.code, "value") else str(executor.code)
        registry[code] = executor

    retry_totals = _get_folder_phase_retry_totals(folder_path)
    selected_targets, step_runs_by_phase = _get_folder_step_run_breakdowns(folder_path)

    phase_codes = [p.get("code") for p in phase_defs if p.get("code")]
    x_positions = {code: (idx * 180) + 72 for idx, code in enumerate(phase_codes)}
    svg_w = max(220, len(phase_codes) * 180)

    edge_lines = []
    for phase in phase_defs:
        code = phase.get("code")
        executor = registry.get(code)
        dependencies = executor.depends_on if executor and executor.depends_on else []
        for dep in dependencies:
            dep_code = dep.value if hasattr(dep, "value") else str(dep)
            if dep_code in x_positions and code in x_positions:
                x1 = x_positions[dep_code] + 54
                x2 = x_positions[code] - 54
                edge_lines.append(
                    f"<line x1='{x1}' y1='70' x2='{x2}' y2='70' stroke='var(--border-color-primary)' stroke-width='2' marker-end='url(#phaseArrow)' />"
                )

    node_html = []
    for idx, phase in enumerate(phase_defs, start=1):
        code = phase.get("code")
        name = phase.get("name") or code
        info = summary_by_code.get(code, {})
        status = info.get("status", "not_started")
        status_label = _STATUS_LABELS.get(status, status.replace("_", " ").title())
        done = info.get("done_count", 0)
        failed = info.get("failed_count", 0)
        skipped = info.get("skipped_count", 0)
        retries = retry_totals.get(code, 0)
        is_selected = (not selected_targets) or (code in selected_targets)
        selected_label = "Selected in run" if is_selected else "Not selected"
        executor = registry.get(code)
        deps = executor.depends_on if executor and executor.depends_on else []
        dep_labels = []
        for dep in deps:
            dep_code = dep.value if hasattr(dep, "value") else str(dep)
            dep_labels.append(dep_code)
        dep_line = ", ".join(dep_labels) if dep_labels else "None"
        run_rows = step_runs_by_phase.get(code, [])
        run_items = []
        if run_rows:
            for run in run_rows:
                err = html.escape((run.get("error") or "").strip())
                err_line = f"<div><strong>Error:</strong> {err}</div>" if err else ""
                run_items.append(
                    "<li>"
                    f"<div><strong>Job #{run.get('job_id')}</strong> · {run.get('job_status')} · {run.get('duration')}</div>"
                    f"<div>Sub-phase state: {run.get('step_state')}</div>"
                    f"<div>Started: {run.get('started')}</div>"
                    f"<div>Finished: {run.get('finished')}</div>"
                    f"{err_line}"
                    "</li>"
                )
        else:
            run_items.append("<li>No recorded StepRun data for this phase in this folder yet.</li>")

        node_html.append(
            f"""
            <details class="pipeline-node status-{status} {'selected' if is_selected else 'not-selected'}" style="left:{x_positions[code]-62}px;" open={"open" if status in ("running", "failed") else ""}>
              <summary>
                <div class="node-title">{idx}. {html.escape(name)}</div>
                <div class="node-meta">{status_label} · {selected_label}</div>
                <div class="node-mini-stats">{done}/{total} · failed {failed} · skipped {skipped} · retries {retries}</div>
              </summary>
              <div class="node-breakdown">
                <div><strong>Dependencies:</strong> {html.escape(dep_line)}</div>
                <div><strong>Executor:</strong> {html.escape(getattr(executor, 'executor_version', 'unbound') if executor else 'unbound')}</div>
                <div><strong>StepRun breakdown:</strong></div>
                <ul>{''.join(run_items)}</ul>
              </div>
            </details>
            """
        )

    return f"""
    <div class="pipeline-graph-view">
      <style>
        .pipeline-graph-view .graph-canvas {{ position: relative; min-height: 300px; overflow-x: auto; padding: 8px 0 0; }}
        .pipeline-graph-view .pipeline-node {{ position: absolute; width: 124px; border: 1px solid var(--border-color-primary); border-radius: 10px; background: var(--panel-background-fill); }}
        .pipeline-graph-view .pipeline-node summary {{ list-style: none; cursor: pointer; padding: 8px; }}
        .pipeline-graph-view .pipeline-node summary::-webkit-details-marker {{ display:none; }}
        .pipeline-graph-view .node-title {{ font-weight: 600; font-size: 0.82rem; }}
        .pipeline-graph-view .node-meta, .pipeline-graph-view .node-mini-stats {{ font-size: 0.72rem; color: var(--body-text-color-subdued); }}
        .pipeline-graph-view .node-breakdown {{ padding: 0 8px 8px; font-size: 0.74rem; }}
        .pipeline-graph-view .node-breakdown ul {{ margin: 6px 0 0 16px; padding: 0; }}
        .pipeline-graph-view .status-done {{ border-color: #27ae60; }}
        .pipeline-graph-view .status-partial, .pipeline-graph-view .status-running {{ border-color: #3498db; }}
        .pipeline-graph-view .status-failed {{ border-color: #e74c3c; }}
        .pipeline-graph-view .status-skipped {{ border-color: #f39c12; }}
        .pipeline-graph-view .pipeline-node.not-selected {{ opacity: 0.6; }}
      </style>
      <div class="section-microcopy">Graph view from <code>pipeline_phases</code> + executor bindings. Click a node to inspect StepRun breakdown (sub-phases, timings, errors).</div>
      <div class="graph-canvas" role="group" aria-label="Pipeline phase graph">
        <svg width="{svg_w}" height="250" viewBox="0 0 {svg_w} 250" aria-hidden="true">
          <defs>
            <marker id="phaseArrow" markerWidth="8" markerHeight="8" refX="5" refY="3" orient="auto">
              <polygon points="0 0, 6 3, 0 6" fill="var(--border-color-primary)" />
            </marker>
          </defs>
          {''.join(edge_lines)}
        </svg>
        {''.join(node_html)}
      </div>
    </div>
    """


def _get_folder_phase_retry_totals(folder_path):
    """Aggregate retry totals (attempt_count - 1) per phase for folder descendants."""
    from modules import utils

    wsl_path = utils.convert_path_to_wsl(folder_path) if hasattr(utils, "convert_path_to_wsl") else folder_path
    target_path = wsl_path if wsl_path else folder_path
    if not target_path:
        return {}

    retries = {}
    conn = db.get_db()
    c = conn.cursor()
    try:
        path_like_unix = target_path + "/%"
        path_like_win = target_path + "\\%"
        c.execute(
            """
            SELECT pp.code, COALESCE(SUM(CASE WHEN ips.attempt_count > 1 THEN ips.attempt_count - 1 ELSE 0 END), 0) AS retries
            FROM image_phase_status ips
            JOIN pipeline_phases pp ON pp.id = ips.phase_id
            JOIN images i ON i.id = ips.image_id
            JOIN folders f ON f.id = i.folder_id
            WHERE f.path = ? OR f.path LIKE ? OR f.path LIKE ?
            GROUP BY pp.code
            """,
            (target_path, path_like_unix, path_like_win),
        )
        for row in c.fetchall():
            code = row[0].strip() if isinstance(row[0], str) else row[0]
            retries[code] = row[1] or 0
    except Exception:
        return {}
    finally:
        conn.close()
    return retries


def _get_folder_step_run_breakdowns(folder_path):
    """Return (selected_target_phases, phase->recent step runs) for a folder."""
    selected_targets = set()
    phase_runs = {}
    conn = db.get_db()
    c = conn.cursor()
    try:
        c.execute(
            """
            SELECT id, status, created_at, started_at, finished_at, queue_payload
            FROM jobs
            WHERE input_path = ?
            ORDER BY COALESCE(started_at, created_at) DESC
            FETCH FIRST 20 ROWS ONLY
            """,
            (folder_path,),
        )
        jobs = c.fetchall()
        for row in jobs:
            job_id = row[0]
            job_status = (row[1] or "unknown").strip()
            queue_payload = row[5]
            payload = None
            if queue_payload:
                try:
                    payload = json.loads(queue_payload)
                except Exception:
                    payload = None
            if payload and isinstance(payload, dict) and not selected_targets:
                for code in payload.get("target_phases") or []:
                    selected_targets.add(str(code))

            c.execute(
                """
                SELECT phase_code, state, started_at, completed_at, error_message
                FROM job_phases
                WHERE job_id = ?
                ORDER BY phase_order
                """,
                (job_id,),
            )
            step_rows = c.fetchall()
            if not step_rows and payload and isinstance(payload, dict):
                codes = payload.get("target_phases") or []
                for code in codes:
                    phase_runs.setdefault(str(code), [])
                continue

            for step in step_rows:
                code = step[0]
                if not code:
                    continue
                started = step[2] or row[3]
                finished = step[3] or row[4]
                phase_runs.setdefault(code, []).append({
                    "job_id": job_id,
                    "job_status": job_status,
                    "step_state": step[1] or "unknown",
                    "started": str(started) if started else "-",
                    "finished": str(finished) if finished else "-",
                    "duration": _format_duration(started, finished),
                    "error": step[4] or "",
                })

        for code in phase_runs:
            phase_runs[code] = phase_runs[code][:3]
    except Exception:
        return selected_targets, phase_runs
    finally:
        conn.close()
    return selected_targets, phase_runs


def _format_duration(started, finished):
    if not started:
        return "-"
    if not finished:
        return "running"
    try:
        delta = finished - started
        total = int(delta.total_seconds())
        mins, secs = divmod(max(total, 0), 60)
        hrs, mins = divmod(mins, 60)
        if hrs:
            return f"{hrs}h {mins}m {secs}s"
        if mins:
            return f"{mins}m {secs}s"
        return f"{secs}s"
    except Exception:
        return "-"

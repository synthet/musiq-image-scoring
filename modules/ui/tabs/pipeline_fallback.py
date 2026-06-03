import gradio as gr

from modules import config, db
from modules.run_manifest import REASON_SOURCE_LEGACY_API, attach_run_reason, build_legacy_api_summary
from modules.ui.tabs import pipeline as pipeline_full


def _gradio_queue_payload(payload: dict, *, job_kind: str, path: str) -> dict:
    return attach_run_reason(
        payload,
        source=REASON_SOURCE_LEGACY_API,
        summary=build_legacy_api_summary(job_kind=job_kind, input_path=path),
        trigger="gradio",
        tool_id="pipeline_fallback",
    )


def _folder_view(folder_path: str, force_refresh: bool = False):
    """Build minimal fallback display values for selected folder."""
    path = (folder_path or "").strip()
    if not path:
        return (
            "### Selected Folder\n- (none)",
            "### Pipeline Progress\n- Select a folder.",
            "### Scoring\n- Status: Not Started\n- Progress: 0/0",
            "### Culling\n- Status: Not Started\n- Progress: 0/0",
            "### Keywords\n- Status: Not Started\n- Progress: 0/0",
            "### Quick Start\n1. Select folder\n2. Run scoring/culling/keywords\n3. Review in Gallery",
        )

    summary = db.get_folder_phase_summary(path, force_refresh=force_refresh) or []
    phases = {item.get("code"): item for item in summary}
    total = max([item.get("total_count", 0) for item in summary] + [0])

    def _phase(code, label):
        item = phases.get(code, {})
        status = item.get("status", "not_started").replace("_", " ").title()
        done = item.get("done_count", 0)
        return f"### {label}\n- Status: {status}\n- Progress: {done}/{total}"

    stepper_lines = ["### Pipeline Progress"]
    for code, label in [
        ("indexing", "Indexing"),
        ("metadata", "Metadata"),
        ("scoring", "Scoring"),
        ("culling", "Culling"),
        ("keywords", "Keywords"),
    ]:
        item = phases.get(code, {})
        status = item.get("status", "not_started").replace("_", " ").title()
        done = item.get("done_count", 0)
        stepper_lines.append(f"- {label}: {status} ({done}/{total})")

    pending = any(phases.get(c, {}).get("status") not in ("done", "skipped") for c in ("scoring", "culling", "keywords"))
    quick = "### Quick Start\n"
    if pending:
        quick += "1. Folder selected\n2. Run pending phases\n3. Review in Gallery"
    else:
        quick += "1. Folder selected\n2. All phases complete\n3. Review in Gallery"

    return (
        f"### Selected Folder\n- Path: `{path}`\n- Images: {total}",
        "\n".join(stepper_lines),
        _phase("scoring", "Scoring"),
        _phase("culling", "Culling"),
        _phase("keywords", "Keywords"),
        quick,
    )


def create_tab(app_config, scoring_runner, tagging_runner, selection_runner, orchestrator) -> dict:
    """Minimal, native-Gradio fallback Pipeline tab."""
    components = {}

    def _folder_choices():
        folders = db.get_all_folders() or []
        return sorted({f for f in folders if f})

    def _save_selected_folder(path: str):
        path = (path or "").strip()
        config.save_config_value("ui.last_selected_folder", path)
        return path

    def _refresh_and_render(path: str):
        path = (path or "").strip()
        choices = _folder_choices()
        if path and path not in choices:
            choices = [path] + choices
        updates = _folder_view(path, force_refresh=True)
        return (gr.update(choices=choices, value=path), path, *updates)

    with gr.Tab("Pipeline", id="pipeline"):
        gr.Markdown("## Pipeline (Fallback UI)")

        last_folder = app_config.get("ui", {}).get("last_selected_folder", "") or ""

        with gr.Row():
            components["folder_dropdown"] = gr.Dropdown(
                choices=_folder_choices(),
                value=last_folder,
                label="Folder",
                allow_custom_value=True,
            )
            components["refresh_btn"] = gr.Button("Refresh")

        components["selected_path"] = gr.Textbox(value=last_folder, label="Selected folder")

        initial_updates = _folder_view(last_folder, force_refresh=False)
        components["folder_summary_html"] = gr.Markdown(initial_updates[0])
        components["quick_start_html"] = gr.Markdown(initial_updates[5])
        components["stepper_html"] = gr.Markdown(initial_updates[1])

        with gr.Row():
            components["run_all_btn"] = gr.Button("Run All Pending", variant="primary")
            components["stop_all_btn"] = gr.Button("Stop All", variant="stop")
            components["repair_index_meta_btn"] = gr.Button("Repair Index/Meta")
            components["run_metadata_btn"] = gr.Button("Run Metadata")

        with gr.Accordion("Scoring", open=True):
            components["scoring_card_html"] = gr.Markdown(initial_updates[2])
            components["scoring_force"] = gr.Checkbox(label="Force Re-score", value=False)
            components["scoring_run_btn"] = gr.Button("Start Scoring")

        with gr.Accordion("Culling", open=False):
            components["culling_card_html"] = gr.Markdown(initial_updates[3])
            components["culling_force"] = gr.Checkbox(label="Force Re-run", value=False)
            components["culling_run_btn"] = gr.Button("Start Culling")

        with gr.Accordion("Keywords", open=False):
            components["keywords_card_html"] = gr.Markdown(initial_updates[4])
            components["keywords_overwrite"] = gr.Checkbox(label="Overwrite Existing", value=False)
            components["keywords_captions"] = gr.Checkbox(label="Generate Captions", value=False)
            components["keywords_run_btn"] = gr.Button("Start Keywords")

        components["monitor_html"] = gr.Markdown("No active jobs in the pipeline.")
        components["console_output"] = gr.Textbox(lines=12, label="Console Output", interactive=False)

    def _run_scoring(path, force):
        if path:
            db.enqueue_job(
                path,
                phase_code="scoring",
                job_type="scoring",
                queue_payload=_gradio_queue_payload(
                    {"input_path": path, "skip_existing": not force},
                    job_kind="scoring",
                    path=path,
                ),
            )

    def _run_metadata(path):
        if path:
            db.enqueue_job(
                path,
                phase_code="scoring",
                job_type="scoring",
                queue_payload=_gradio_queue_payload(
                    {"input_path": path, "skip_existing": False, "target_phases": ["indexing", "metadata"]},
                    job_kind="indexing and metadata",
                    path=path,
                ),
            )

    def _run_culling(path, force):
        if path:
            db.enqueue_job(
                path,
                phase_code="culling",
                job_type="selection",
                queue_payload=_gradio_queue_payload(
                    {"input_path": path, "force_rescan": force},
                    job_kind="culling",
                    path=path,
                ),
            )

    def _run_tagging(path, overwrite, captions):
        if path:
            db.enqueue_job(
                path,
                phase_code="keywords",
                job_type="tagging",
                queue_payload=_gradio_queue_payload(
                    {"input_path": path, "overwrite": overwrite, "generate_captions": captions},
                    job_kind="tagging",
                    path=path,
                ),
            )

    def _run_all_pending(path):
        if path:
            orchestrator.start(path)

    def _stop_all():
        orchestrator.stop()
        scoring_runner.stop()
        selection_runner.stop()
        tagging_runner.stop()

    def _repair_index_meta(path):
        if path:
            db.backfill_index_meta_for_folder(path)

    components["folder_dropdown"].change(
        fn=lambda p: _refresh_and_render(_save_selected_folder(p)),
        inputs=[components["folder_dropdown"]],
        outputs=[
            components["folder_dropdown"],
            components["selected_path"],
            components["folder_summary_html"],
            components["stepper_html"],
            components["scoring_card_html"],
            components["culling_card_html"],
            components["keywords_card_html"],
            components["quick_start_html"],
        ],
    )

    components["refresh_btn"].click(
        fn=_refresh_and_render,
        inputs=[components["selected_path"]],
        outputs=[
            components["folder_dropdown"],
            components["selected_path"],
            components["folder_summary_html"],
            components["stepper_html"],
            components["scoring_card_html"],
            components["culling_card_html"],
            components["keywords_card_html"],
            components["quick_start_html"],
        ],
    )

    components["scoring_run_btn"].click(fn=_run_scoring, inputs=[components["selected_path"], components["scoring_force"]], outputs=[])
    components["culling_run_btn"].click(fn=_run_culling, inputs=[components["selected_path"], components["culling_force"]], outputs=[])
    components["keywords_run_btn"].click(fn=_run_tagging, inputs=[components["selected_path"], components["keywords_overwrite"], components["keywords_captions"]], outputs=[])
    components["run_all_btn"].click(fn=_run_all_pending, inputs=[components["selected_path"]], outputs=[])
    components["run_metadata_btn"].click(fn=_run_metadata, inputs=[components["selected_path"]], outputs=[])
    components["repair_index_meta_btn"].click(fn=_repair_index_meta, inputs=[components["selected_path"]], outputs=[])
    components["stop_all_btn"].click(fn=_stop_all, inputs=[], outputs=[])

    return components


def get_status_update(
    scoring_runner,
    tagging_runner,
    selection_runner,
    orchestrator,
    selected_folder,
    telemetry_state,
    collapse_noisy,
    pin_critical,
):
    """Reuse canonical monitor/update behavior from full pipeline tab."""
    return pipeline_full.get_status_update(
        scoring_runner,
        tagging_runner,
        selection_runner,
        orchestrator,
        selected_folder,
        telemetry_state,
        collapse_noisy,
        pin_critical,
    )

import gradio as gr

CUSTOM_CSS = """
:root {
  --accent-primary: #007acc;
  --accent-hover: #159cff;
  --accent-success: #4caf50;
  --accent-danger: #f14f45;
  --accent-queued: #80838a;

  --bg-page: #1b1b1f;
  --bg-topbar: #2a2b31;
  --bg-panel: #25262c;
  --bg-surface: #343640;
  --bg-input: #3b3d47;
  --bg-console: #17181e;

  --ink-base: rgba(255, 255, 255, 0.92);
  --ink-muted: #c7c9d2;
  --ink-dim: #8b8f99;

  --line: #474a56;
  --line-light: #5a5e6a;

  --radius-sm: 4px;
  --radius-md: 6px;
  --radius-lg: 8px;

  --shadow-soft: 0 8px 20px rgba(0, 0, 0, 0.18);
  --transition-fast: 160ms ease;
}

html,
body,
.gradio-container {
  margin: 0 !important;
  padding: 0 !important;
  min-height: 100vh !important;
  background:
    radial-gradient(circle at 18% -10%, rgba(0, 122, 204, 0.1), transparent 42%),
    var(--bg-page) !important;
  color: var(--ink-base);
  font-family: "Segoe UI", Tahoma, Geneva, Verdana, sans-serif;
}

.gradio-container {
  max-width: 100% !important;
}

.block.padded {
  padding-top: 0.5rem !important;
  padding-bottom: 0.5rem !important;
}

/* TOPBAR */
.topbar {
  display: flex !important;
  align-items: center;
  gap: 14px;
  width: 100%;
  padding: 10px 18px;
  background: linear-gradient(180deg, var(--bg-topbar), #30323a);
  border-bottom: 1px solid var(--line);
  box-shadow: var(--shadow-soft);
}

.brand {
  font-weight: 600;
  font-size: 1.12rem;
  line-height: 1;
}

.topbar-spacer {
  flex-grow: 1;
}

.connection-pill {
  color: var(--accent-success);
  font-size: 0.85rem;
  font-weight: 500;
  display: inline-flex;
  align-items: center;
  gap: 6px;
}

.connection-pill::before {
  content: "";
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: var(--accent-success);
  box-shadow: 0 0 10px rgba(76, 175, 80, 0.75);
}

.folder-meta {
  font-size: 0.85rem;
  color: var(--ink-dim);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

/* TABS */
.tabs {
  display: flex;
  border-bottom: 1px solid var(--line) !important;
  margin-bottom: 10px !important;
}

.tabs .tab-nav {
  gap: 4px;
  background: transparent !important;
  border: none !important;
}

.tabs .tab-nav button {
  background: transparent !important;
  border: none !important;
  border-radius: var(--radius-md) !important;
  color: var(--ink-muted) !important;
  padding: 9px 12px !important;
  font-size: 0.9rem !important;
  box-shadow: none !important;
  transition: color var(--transition-fast), box-shadow var(--transition-fast);
}

.tabs .tab-nav button.selected {
  background: transparent !important;
  color: var(--accent-hover) !important;
  box-shadow: inset 0 -2px 0 var(--accent-primary) !important;
}

.tabs .tab-nav button:hover:not(.selected) {
  background: var(--bg-input) !important;
}

/* SIDEBAR & PANELS */
.sidebar {
  background-color: var(--bg-panel) !important;
  border-right: 1px solid var(--line) !important;
  border-radius: var(--radius-md);
  padding: 10px 12px !important;
  overflow-y: auto;
}

.sidebar h3 {
  margin-top: 0;
}

.panel {
  background-color: var(--bg-panel) !important;
  border: 1px solid var(--line) !important;
  border-radius: var(--radius-lg) !important;
  overflow: hidden;
  margin-bottom: 14px;
  padding: 0 !important;
  box-shadow: var(--shadow-soft);
}

.panel-header {
  padding: 12px 16px;
  border-bottom: 1px solid var(--line);
  background-color: #2f3038;
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
}

.panel-title {
  margin: 0;
  font-size: 1rem;
  font-weight: 600;
}

.panel-body {
  padding: 14px;
}

.header-note {
  font-size: 0.85rem;
  color: var(--ink-muted);
}

/* BUTTONS */
button,
.gr-button {
  border-radius: var(--radius-md) !important;
  font-size: 0.9rem !important;
  min-height: 38px !important;
  transition:
    transform var(--transition-fast),
    background-color var(--transition-fast),
    border-color var(--transition-fast);
}

.btn,
.secondary-btn,
.secondary-btn button {
  background-color: var(--bg-input) !important;
  color: var(--ink-base) !important;
  border: 1px solid var(--line-light) !important;
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

/* TREE */
.tree-container {
  font-family: "Segoe UI", Tahoma, sans-serif;
  font-size: 0.85rem;
  color: var(--ink-muted);
  line-height: 1.75;
  margin-top: 8px;
}

.tree-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 5px 8px;
  border-radius: var(--radius-md);
  cursor: pointer;
  transition: background-color var(--transition-fast), color var(--transition-fast);
}

.tree-item:hover {
  background-color: var(--bg-surface);
}

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
  color: var(--ink-dim);
}

.tree-indent-1 {
  margin-left: 20px;
}

.tree-indent-2 {
  margin-left: 36px;
}

.tree-indent-3 {
  margin-left: 52px;
}

.folder-summary h3,
.legend-title {
  margin-top: 0;
  margin-bottom: 10px;
}

.folder-summary p {
  font-size: 0.85rem;
  color: var(--ink-muted);
  line-height: 1.5;
  margin: 0;
}

.folder-summary strong {
  color: var(--ink-base);
}

.legend {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 8px;
  font-size: 0.85rem;
  color: var(--ink-muted);
  margin-top: 10px;
}

.legend-item {
  display: inline-flex;
  align-items: center;
  gap: 6px;
}

/* STEPPER */
.stepper {
  display: flex !important;
  align-items: center !important;
  justify-content: space-between !important;
  gap: 8px !important;
  margin-top: 6px;
  margin-bottom: 10px;
  overflow-x: auto;
  padding-bottom: 4px;
}

.step {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  flex: 1;
  min-width: 100px;
}

.step-dot {
  width: 28px;
  height: 28px;
  border-radius: 50%;
  background-color: var(--bg-surface);
  border: 2px solid var(--line-light);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 0.8rem;
  font-weight: bold;
  color: var(--ink-dim);
  position: relative;
  z-index: 2;
}

.step-label {
  font-size: 0.8rem;
  font-weight: 600;
  color: var(--ink-muted);
  text-transform: uppercase;
}

.step-count {
  font-size: 0.75rem;
  color: var(--ink-dim);
}

.connector {
  height: 2px;
  background-color: var(--line-light);
  flex: 1;
  margin-top: -38px;
  min-width: 50px;
  position: relative;
  z-index: 1;
}

.step.done .step-dot {
  border-color: var(--accent-success);
  color: var(--accent-success);
  background-color: rgba(76, 175, 80, 0.1);
}

.step.running .step-dot {
  border-color: var(--accent-primary);
  color: var(--accent-primary);
  background-color: rgba(0, 122, 204, 0.1);
  box-shadow: 0 0 0 4px rgba(0, 122, 204, 0.18);
  animation: running-pulse 1.6s ease-in-out infinite;
}

.connector.done {
  background-color: var(--accent-success);
}

.connector.running {
  background: linear-gradient(90deg, var(--accent-success), var(--accent-primary));
}

/* PHASE CARDS */
.phase-grid {
  gap: 10px;
}

.phase-card {
  background-color: var(--bg-surface) !important;
  border: 1px solid var(--line) !important;
  border-radius: var(--radius-md) !important;
  border-left: 4px solid var(--accent-queued) !important;
  padding: 15px !important;
}

.phase-card.queued {
  border-left-color: var(--accent-queued) !important;
}

.phase-card.running {
  border-color: var(--accent-primary) !important;
  border-left-color: var(--accent-primary) !important;
  box-shadow: 0 0 0 1px rgba(0, 122, 204, 0.2);
}

.phase-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}

.phase-title {
  font-weight: 600;
  font-size: 0.95rem;
  display: flex;
  align-items: center;
  gap: 8px;
  color: var(--ink-base);
}

.phase-icon {
  width: 24px;
  height: 24px;
  background: var(--bg-input);
  border-radius: var(--radius-sm);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 0.8rem;
  color: var(--ink-muted);
  font-weight: bold;
}

.phase-card.running .phase-icon {
  background: var(--accent-primary);
  color: white;
}

.phase-status {
  font-size: 0.75rem;
  padding: 2px 6px;
  border-radius: 4px;
  background-color: var(--bg-input);
  color: var(--ink-muted);
  text-transform: uppercase;
}

.phase-card.running .phase-status {
  background-color: rgba(0, 122, 204, 0.2);
  color: #61baff;
}

.phase-stats {
  font-size: 0.85rem;
  color: var(--ink-muted);
  margin-bottom: 12px;
}

.progress {
  height: 6px;
  background-color: var(--bg-page);
  border-radius: 3px;
  overflow: hidden;
  border: 1px solid var(--line);
  margin-bottom: 15px;
}

.progress-fill {
  height: 100%;
  background-color: var(--ink-dim);
  width: 0%;
}

.phase-card.running .progress-fill {
  background-color: var(--accent-primary);
}

/* OPTIONS ACCORDION */
.options-accordion {
  background: transparent !important;
  border: 1px solid var(--line) !important;
  border-radius: var(--radius-md) !important;
  overflow: hidden;
  margin-top: 10px;
}

.options-accordion > button {
  background-color: rgba(10, 11, 14, 0.2) !important;
  padding: 8px 12px !important;
  font-size: 0.85rem !important;
  font-weight: normal !important;
  color: var(--ink-base) !important;
  border-radius: var(--radius-md) !important;
  border: none !important;
}

.options-accordion.open > button {
  border-bottom: 1px solid var(--line) !important;
  border-bottom-left-radius: 0 !important;
  border-bottom-right-radius: 0 !important;
}

.options-accordion .wrap, .options-accordion .accordion-content {
  padding: 0 !important;
  border: none !important;
}

.options-accordion .label-wrap {
  width: 100%;
  min-height: 38px !important;
  background: transparent !important;
  border: none !important;
  border-bottom: 1px solid var(--line) !important;
  color: var(--ink-muted);
  border-radius: 0 !important;
  padding: 8px 12px !important;
  margin: 0 !important;
  box-shadow: none !important;
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
  gap: 8px;
}

/* CONSOLE */
.console-container {
  background-color: var(--bg-console) !important;
  border: 1px solid var(--line) !important;
  border-radius: var(--radius-md) !important;
  padding: 10px !important;
  font-family: "Consolas", "Courier New", monospace !important;
  font-size: 0.85rem !important;
  color: #d4d4d4 !important;
  max-height: 220px;
  overflow-y: auto;
}

.console-code textarea,
.console-code pre {
  font-family: "Consolas", "Courier New", monospace !important;
  font-size: 0.85rem !important;
  background: transparent !important;
  border: none !important;
}

.section-divider {
  border-top: 1px solid var(--line);
  margin: 15px 0;
}

@keyframes running-pulse {
  0%,
  100% {
    box-shadow: 0 0 0 4px rgba(0, 122, 204, 0.18);
  }

  50% {
    box-shadow: 0 0 0 6px rgba(0, 122, 204, 0.08);
  }
}

@media (max-width: 1200px) {
  .topbar {
    flex-wrap: wrap;
    row-gap: 6px;
  }

  .folder-meta {
    max-width: 100%;
  }
}

@media (max-width: 900px) {
  .sidebar {
    border-right: none !important;
    border-bottom: 1px solid var(--line) !important;
  }

  .step {
    min-width: 92px;
  }

  .step-label {
    font-size: 0.72rem;
  }

  .step-count {
    font-size: 0.7rem;
  }

  .legend {
    grid-template-columns: 1fr;
  }
}
"""


def topbar_html():
    return """
    <div class="topbar">
      <div class="brand">Vexlum WebUI</div>
      <div class="folder-meta">/Photos/D300/28-70mm/2015 - 48 images</div>
      <div class="topbar-spacer"></div>
      <div class="connection-pill">Connected</div>
    </div>
    """


def tree_html():
    return """
    <div class="tree-container">
      <div class="tree-item"><span class="tree-icon empty">+</span><span>Photos</span></div>
      <div class="tree-item tree-indent-1"><span class="tree-icon empty">+</span><span>D300</span></div>
      <div class="tree-item tree-indent-2"><span class="tree-icon empty">+</span><span>28-70mm</span></div>
      <div class="tree-item tree-indent-3 selected"><span class="tree-icon partial">P</span><span>2015</span></div>
      <div class="tree-item tree-indent-1"><span class="tree-icon empty">+</span><span>D90</span></div>
      <div class="tree-item tree-indent-2"><span class="tree-icon empty">+</span><span>10.5mm</span></div>
      <div class="tree-item tree-indent-3"><span class="tree-icon done">D</span><span>2013</span></div>
    </div>
    """


def stepper_html():
    return """
    <div class="stepper">
      <div class="step done">
        <div class="step-dot">1</div>
        <div class="step-label">Index</div>
        <div class="step-count">48 / 48</div>
      </div>
      <div class="connector done"></div>

      <div class="step done">
        <div class="step-dot">2</div>
        <div class="step-label">Meta</div>
        <div class="step-count">48 / 48</div>
      </div>
      <div class="connector running"></div>

      <div class="step running">
        <div class="step-dot">3</div>
        <div class="step-label">Scoring</div>
        <div class="step-count">32 / 48</div>
      </div>
      <div class="connector"></div>

      <div class="step">
        <div class="step-dot">4</div>
        <div class="step-label">Culling</div>
        <div class="step-count">0 / 48</div>
      </div>
      <div class="connector"></div>

      <div class="step">
        <div class="step-dot">5</div>
        <div class="step-label">Keywords</div>
        <div class="step-count">0 / 48</div>
      </div>
    </div>
    """


def phase_card_html(title, initial, status, processed, progress):
    return f"""
    <div class="phase-head">
      <div class="phase-title">
        <div class="phase-icon">{initial}</div>
        {title}
      </div>
      <div class="phase-status">{status}</div>
    </div>
    <div class="phase-stats">{processed} images processed</div>
    <div class="progress"><div class="progress-fill" style="width: {progress}%;"></div></div>
    """


with gr.Blocks(title="Vexlum WebUI") as demo:
    gr.HTML(topbar_html())

    with gr.Tabs(elem_classes=["tabs"]):
        with gr.Tab("Pipeline"):
            with gr.Row(equal_height=False):
                # SIDEBAR
                with gr.Column(scale=1, min_width=300, elem_classes=["sidebar"]):
                    gr.Markdown("### Folders")
                    with gr.Row():
                        gr.Button("Refresh", elem_classes=["secondary-btn"])
                        gr.Button("Collapse", elem_classes=["secondary-btn"])

                    gr.HTML(tree_html())

                    gr.HTML("<div class='section-divider'></div>")

                    gr.HTML(
                        """
                        <div class="folder-summary">
                          <h3>Selected Folder</h3>
                          <p><strong>D300 / 28-70mm / 2015</strong><br>48 images</p>
                        </div>
                        """
                    )
                    gr.Button("Back to Gallery", elem_classes=["success-btn"])

                    gr.HTML("<div class='section-divider'></div>")

                    gr.HTML(
                        """
                        <h3 class="legend-title">Legend</h3>
                        <div class="legend">
                            <span class="legend-item"><strong class="tree-icon done">D</strong> Done</span>
                            <span class="legend-item"><strong class="tree-icon partial">P</strong> Running</span>
                            <span class="legend-item"><strong class="tree-icon failed">F</strong> Failed</span>
                            <span class="legend-item"><strong class="tree-icon empty">N</strong> Not Started</span>
                        </div>
                        """
                    )

                # MAIN DASHBOARD
                with gr.Column(scale=3):
                    # PANEL: Pipeline Progress
                    with gr.Group(elem_classes=["panel"]):
                        gr.HTML(
                            """
                            <div class="panel-header">
                                <h2 class="panel-title">Pipeline Progress</h2>
                                <div class="folder-meta">Active: Scoring Mode</div>
                            </div>
                            """
                        )
                        with gr.Column(elem_classes=["panel-body"]):
                            gr.HTML(stepper_html())
                            with gr.Row(elem_classes=["pipeline-actions"]):
                                gr.Button("Run All Pending", elem_classes=["primary-btn"])
                                gr.Button("Stop All", elem_classes=["danger-btn"])

                    # PANEL: Phases (Card Grid)
                    with gr.Group(elem_classes=["panel"]):
                        with gr.Row(elem_classes=["panel-body", "phase-grid"]):
                            # Scoring
                            with gr.Column(elem_classes=["phase-card", "running"]):
                                gr.HTML(phase_card_html("Scoring", "S", "Running", "32 / 48", 66.7))
                                gr.Button("Pause Scoring", elem_classes=["primary-btn"])
                                with gr.Accordion("Options", open=False, elem_classes=["options-accordion"]):
                                    gr.Checkbox(label="Force Re-score existing")
                                    gr.Checkbox(label="Check metadata before scoring")

                            # Culling
                            with gr.Column(elem_classes=["phase-card", "queued"]):
                                gr.HTML(phase_card_html("Culling", "C", "Queued", "0 / 48", 0))
                                gr.Button("Run Culling", elem_classes=["secondary-btn"])
                                with gr.Accordion("Options", open=False, elem_classes=["options-accordion"]):
                                    gr.Checkbox(label="Force Re-run")

                            # Keywords
                            with gr.Column(elem_classes=["phase-card", "queued"]):
                                gr.HTML(phase_card_html("Keywords", "K", "Queued", "0 / 48", 0))
                                gr.Button("Run Keywords", elem_classes=["secondary-btn"])
                                with gr.Accordion("Options", open=False, elem_classes=["options-accordion"]):
                                    gr.Checkbox(label="Overwrite existing tags")
                                    gr.Checkbox(label="Generate captions")

                    # PANEL: Console
                    with gr.Group(elem_classes=["panel"]):
                        gr.HTML(
                            """
                            <div class="panel-header">
                                <h2 class="panel-title">Active Job Monitor (Scoring)</h2>
                                <div class="header-note">Auto-scroll active</div>
                            </div>
                            """
                        )
                        with gr.Column(elem_classes=["panel-body"]):
                            gr.Code(
                                value="[10:12:21] INFO model loaded: mobilenet_v2 + aesthetic head\n[10:12:22] INFO scanning 48 candidate files from selected folder\n[10:12:24] SUCCESS scored IMG_1832.jpg score=0.82\n[10:12:25] SUCCESS scored IMG_1833.jpg score=0.77\n[10:12:25] INFO updating database IMAGE_PHASE_STATUS for row_id=8941\n[10:12:28] SUCCESS scored IMG_1834.jpg score=0.69",
                                language="shell",
                                interactive=False,
                                elem_classes=["console-container", "console-code"],
                            )
                            gr.Markdown("*Unified monitor rotates to Culling and Keywords automatically when they become active.*")

        with gr.Tab("Gallery"):
            gr.Markdown("## Gallery")

        with gr.Tab("Settings"):
            gr.Markdown("## Settings")

if __name__ == "__main__":
    demo.launch(server_name="127.0.0.1", server_port=7869, css=CUSTOM_CSS, theme=gr.themes.Base())

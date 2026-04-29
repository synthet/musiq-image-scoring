import gradio as gr

CUSTOM_CSS = """
:root {
  --accent-primary: #58a6ff;
  --accent-success: #3fb950;
  --accent-danger: #f85149;
  --text-muted: #8b949e;
  --bg-primary: #0d1117;
  --bg-secondary: #161b22;
  --bg-tertiary: #21262d;
  --border-color: #30363d;
  --text-primary: #c9d1d9;
}

html, body, .gradio-container {
  margin: 0 !important;
  padding: 0 !important;
  min-height: 100vh !important;
  background:
    radial-gradient(circle at top, rgba(88, 166, 255, 0.08), transparent 35%),
    linear-gradient(180deg, #0b1020 0%, var(--bg-primary) 28%, #090d16 100%);
  color: var(--text-primary);
  font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
}

.gradio-container { max-width: 100% !important; }

#app-shell {
  min-height: 100vh;
  padding: 22px;
}

#title {
  font-size: 26px;
  font-weight: 700;
  margin: 6px 0 18px;
}

.tabs {
  border-bottom: 1px solid var(--border-color);
  margin-bottom: 18px;
}

.tabs .tab-nav {
  gap: 14px;
}

.tabs .tab-nav button {
  background: transparent !important;
  border: none !important;
  border-radius: 0 !important;
  color: var(--text-primary) !important;
  padding: 10px 12px !important;
  box-shadow: none !important;
}

.tabs .tab-nav button.selected {
  color: #ff9b45 !important;
  border-bottom: 2px solid #ff9b45 !important;
}

.panel, .card, .phase-card {
  background: rgba(22, 27, 34, 0.88) !important;
  border: 1px solid var(--border-color) !important;
  border-radius: 12px !important;
  box-shadow: 0 10px 30px rgba(0,0,0,0.18);
}

.panel { padding: 18px !important; }
.card { padding: 16px !important; }

button, .gr-button {
  border-radius: 10px !important;
}

.primary-btn button, .primary-btn {
  background: linear-gradient(180deg, #61adff, #4d98f0) !important;
  color: white !important;
  border: none !important;
}

.danger-btn button, .danger-btn {
  background: linear-gradient(180deg, #ff5e57, #f85149) !important;
  color: white !important;
  border: none !important;
}

.secondary-btn button, .secondary-btn {
  background: #1f2632 !important;
  color: var(--text-primary) !important;
  border: 1px solid var(--border-color) !important;
}

.tree-container {
  font-family: "JetBrains Mono", "SFMono-Regular", Consolas, monospace;
  font-size: 13px;
  line-height: 1.9;
  margin-top: 14px;
}
.tree-item {
  display: flex;
  align-items: center;
  gap: 7px;
  padding: 2px 8px;
  border-radius: 6px;
  color: var(--text-primary);
}
.tree-item.selected { background: rgba(88, 166, 255, 0.20); }
.tree-icon { width: 14px; text-align: center; font-size: 11px; }
.tree-icon.done { color: var(--accent-success); }
.tree-icon.partial { color: var(--accent-primary); }
.tree-indent { margin-left: 16px; }
.tree-muted { color: var(--text-muted); }
.legend { color: var(--text-muted); font-size: 11px; margin-top: 12px; }

.stepper-shell {
  padding: 12px 8px 2px;
}
.stepper-nodes {
  display: flex;
  align-items: flex-start;
  gap: 0;
  width: 100%;
}
.stepper-node {
  display: flex;
  flex-direction: column;
  align-items: center;
  flex: 1;
}
.node-row {
  width: 100%;
  display: flex;
  align-items: center;
}
.node-circle {
  width: 36px;
  height: 36px;
  border-radius: 999px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-weight: 700;
  font-size: 12px;
  background: transparent;
  border: 2px solid var(--text-muted);
  color: var(--text-primary);
  flex-shrink: 0;
}
.node-circle.done { background: var(--accent-success); border-color: var(--accent-success); color: #fff; }
.node-circle.running { background: var(--accent-primary); border-color: var(--accent-primary); color: #fff; animation: pulse 1.5s ease-in-out infinite; }
.connector {
  flex: 1;
  height: 3px;
  margin: 0 4px;
  border-radius: 999px;
  background: var(--text-muted);
  opacity: 0.65;
}
.connector.done { background: var(--accent-success); opacity: 1; }
.connector.running { background: var(--accent-primary); opacity: 1; }
.node-label { font-size: 12px; font-weight: 700; margin-top: 10px; }
.node-count { font-size: 11px; color: var(--text-muted); margin-top: 2px; }

@keyframes pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.55; }
}

.phase-card {
  padding: 16px !important;
  border-left-width: 3px !important;
  border-left-style: solid !important;
  border-left-color: var(--text-muted) !important;
}
.phase-card.running {
  border-left-color: var(--accent-primary) !important;
  box-shadow: 0 0 0 1px rgba(88,166,255,0.22), 0 10px 30px rgba(0,0,0,0.18) !important;
}
.phase-card.done { border-left-color: var(--accent-success) !important; }
.phase-card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 10px;
}
.phase-card-title { font-size: 15px; font-weight: 700; }
.phase-card-badge {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 11px;
  padding: 3px 9px;
  border-radius: 999px;
  background: rgba(88,166,255,0.15);
  color: var(--accent-primary);
}
.phase-card-badge.muted {
  background: rgba(139,148,158,0.14);
  color: var(--text-muted);
}
.phase-stats { font-size: 13px; color: var(--text-primary); margin-bottom: 12px; }
.phase-progress {
  height: 6px;
  background: #0a0f17;
  border-radius: 999px;
  overflow: hidden;
  margin-bottom: 14px;
}
.phase-progress-fill {
  height: 100%;
  border-radius: 999px;
  background: var(--accent-primary);
}
.phase-progress-fill.empty { width: 0 !important; }
.phase-options {
  color: var(--text-muted);
  font-size: 12px;
}

.info-label {
  color: var(--text-muted);
  font-size: 13px;
}

.job-monitor-header {
  display: flex;
  align-items: center;
  gap: 8px;
  font-weight: 700;
  margin-bottom: 10px;
}
.status-dot {
  width: 8px;
  height: 8px;
  border-radius: 999px;
  background: var(--accent-primary);
  animation: pulse 1.5s ease-in-out infinite;
}
.job-monitor-progress {
  font-size: 12px;
  color: var(--text-primary);
  margin-bottom: 8px;
}
.job-monitor-bar {
  height: 8px;
  background: #0a0f17;
  border-radius: 999px;
  overflow: hidden;
  margin-bottom: 10px;
}
.job-monitor-bar-fill {
  width: 66.7%;
  height: 100%;
  background: var(--accent-primary);
}

.console-code textarea, .console-code pre {
  font-size: 12px !important;
}

hr {
  border: none;
  border-top: 1px solid var(--border-color);
  margin: 16px 0;
}
"""


def tree_html():
    return """
    <div class="tree-container">
      <div class="tree-item"><span class="tree-icon">📁</span><span>/ Photos</span></div>
      <div class="tree-item tree-indent"><span class="tree-icon">📁</span><span>+-- D300</span></div>
      <div class="tree-item tree-indent" style="margin-left:32px;"><span class="tree-icon">📁</span><span>+-- 28-70mm</span></div>
      <div class="tree-item tree-indent selected" style="margin-left:48px;"><span class="tree-icon done">✓</span><span>+-- 2015</span></div>
      <div class="tree-item tree-indent"><span class="tree-icon">📁</span><span>+-- D90</span></div>
      <div class="tree-item tree-indent" style="margin-left:32px;"><span class="tree-icon">📁</span><span>+-- 10.5mm</span></div>
      <div class="tree-item tree-indent" style="margin-left:48px;"><span class="tree-icon partial">◐</span><span>+-- 2013</span></div>
      <div class="legend"><strong>Legend:</strong> ✓ all done · ◐ partial · ✗ failed · ○ not started</div>
    </div>
    """


def stepper_html():
    return """
    <div class="stepper-shell">
      <div class="stepper-nodes">
        <div class="stepper-node">
          <div class="node-row"><div class="node-circle done">1</div><div class="connector done"></div></div>
          <div class="node-label">INDEX</div><div class="node-count">48/48</div>
        </div>
        <div class="stepper-node">
          <div class="node-row"><div class="node-circle done">2</div><div class="connector done"></div></div>
          <div class="node-label">META</div><div class="node-count">48/48</div>
        </div>
        <div class="stepper-node">
          <div class="node-row"><div class="node-circle running">3</div><div class="connector running"></div></div>
          <div class="node-label">SCORE</div><div class="node-count">32/48</div>
        </div>
        <div class="stepper-node">
          <div class="node-row"><div class="node-circle">4</div><div class="connector"></div></div>
          <div class="node-label">CULL</div><div class="node-count">0/48</div>
        </div>
        <div class="stepper-node">
          <div class="node-row"><div class="node-circle">5</div></div>
          <div class="node-label">KEYWORDS</div><div class="node-count">0/48</div>
        </div>
      </div>
    </div>
    """


def phase_card_html(title: str, badge: str, processed: str, progress: float, running: bool = False):
    badge_cls = "phase-card-badge" if running else "phase-card-badge muted"
    fill_cls = "phase-progress-fill"
    return f"""
    <div class="phase-card-header">
      <div class="phase-card-title">{title}</div>
      <div class="{badge_cls}">{badge}</div>
    </div>
    <div class="phase-stats">{processed} images processed</div>
    <div class="phase-progress"><div class="{fill_cls}" style="width:{progress:.1f}%;"></div></div>
    """


def job_monitor_html():
    return """
    <div class="job-monitor-header"><span class="status-dot"></span><span>Active Job: Scoring</span></div>
    <div class="job-monitor-progress">32/48 (66.7%)</div>
    <div class="job-monitor-bar"><div class="job-monitor-bar-fill"></div></div>
    """


HEAD = """
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
"""

with gr.Blocks(title="Vexlum WebUI") as demo:
    with gr.Column(elem_id="app-shell"):
        gr.HTML("<div id='title'>Vexlum WebUI</div>")

        with gr.Tabs(elem_classes=["tabs"]):
            with gr.Tab("Pipeline"):
                with gr.Row(equal_height=False):
                    with gr.Column(scale=1, min_width=320, elem_classes=["panel"]):
                        gr.Button("Refresh", elem_classes=["secondary-btn"])
                        gr.HTML(tree_html())
                        gr.HTML("<hr>")
                        gr.Markdown("<div class='info-label'><strong>Selected Folder:</strong> <code>D300/28-70mm/2015</code> &nbsp; 48 images</div>")
                        gr.Button("Open in Gallery", elem_classes=["secondary-btn"])

                    with gr.Column(scale=3):
                        with gr.Group(elem_classes=["panel"]):
                            gr.HTML(stepper_html())

                        with gr.Row():
                            gr.Button("Run All Pending", elem_classes=["primary-btn"])
                            gr.Button("Stop All", elem_classes=["danger-btn"])

                        with gr.Row(equal_height=True):
                            with gr.Column(elem_classes=["phase-card", "running"]):
                                gr.HTML(phase_card_html("Scoring", "Running", "32/48", 66.7, running=True))
                                gr.Button("Run Scoring", elem_classes=["secondary-btn"])
                                with gr.Accordion("Options", open=False):
                                    gr.Checkbox(label="Force Re-score")
                                    gr.Checkbox(label="Prefer existing cache", value=True)

                            with gr.Column(elem_classes=["phase-card"]):
                                gr.HTML(phase_card_html("Culling", "Not Started", "0/48", 0.0))
                                gr.Button("Run Culling", elem_classes=["secondary-btn"])
                                with gr.Accordion("Options", open=False):
                                    gr.Checkbox(label="Force Re-run")

                            with gr.Column(elem_classes=["phase-card"]):
                                gr.HTML(phase_card_html("Keywords", "Not Started", "0/48", 0.0))
                                gr.Button("Run Keywords", elem_classes=["secondary-btn"])
                                with gr.Accordion("Options", open=False):
                                    gr.Checkbox(label="Overwrite existing tags")
                                    gr.Checkbox(label="Generate captions")

                        with gr.Accordion("Tag Propagation", open=False, elem_classes=["panel"]):
                            gr.Markdown("<div class='info-label'>Propagate keywords from tagged images to untagged neighbors using visual similarity.</div>")
                            gr.Button("Propagate Tags from Similar Images", elem_classes=["secondary-btn"])
                            gr.Checkbox(label="Dry Run", value=True)

                        with gr.Group(elem_classes=["panel"]):
                            gr.HTML(job_monitor_html())
                            with gr.Accordion("Console Output", open=True):
                                gr.Code(
                                    value="[2025-03-06 14:32:01] Processing IMG_4521.NEF...\n"
                                          "[2025-03-06 14:32:03] Score: 0.82 (tech: 0.79, aes: 0.85)\n"
                                          "[2025-03-06 14:32:04] Processing IMG_4522.NEF...",
                                    language="shell",
                                    interactive=False,
                                    elem_classes=["console-code"],
                                )

            with gr.Tab("Gallery"):
                with gr.Group(elem_classes=["panel"]):
                    gr.Markdown("## Gallery\nThis tab remains unmodified.")

            with gr.Tab("Settings"):
                with gr.Group(elem_classes=["panel"]):
                    gr.Markdown("## Settings\nThis tab corresponds to the previous Configurations tab.")

if __name__ == "__main__":
    demo.launch(
        server_name="127.0.0.1",
        server_port=7869,
        css=CUSTOM_CSS,
        head=HEAD,
    )

# fmt: off
# noqa
# ruff: noqa
# Pipeline UI Mockup v2 — Electron-style, linter-exempt.
# Follows https://www.gradio.app/guides/custom-CSS-and-JS
#
#   css=  → launch()           (not gr.HTML("<style>"))
#   head= → launch()           (Google Fonts)
#   js=   → launch()           (page-load init; guide says Blocks.launch in Gradio 6)
#   elem_id / elem_classes     (stable selectors, never Gradio internals)

import gradio as gr

# ── Fonts ─────────────────────────────────────────────────────────────────────
HEAD = """
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Segoe+UI:wght@400;600&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
"""

# ── CSS ───────────────────────────────────────────────────────────────────────
# Mirrors the Electron HTML mockup's VSCode-inspired palette.
# All selectors use elem_id (#) or elem_classes (.) we define; no Gradio internals.
CSS = """
:root {
  --e-blue:    #007acc;
  --e-blue-h:  #0098ff;
  --e-green:   #4caf50;
  --e-red:     #f44336;
  --e-queued:  #888888;

  --e-bg:      #1e1e1e;
  --e-panel:   #252526;
  --e-surface: #333333;
  --e-input:   #3c3c3c;
  --e-line:    #444444;
  --e-line-l:  #555555;

  --e-ink:     rgba(255,255,255,0.87);
  --e-muted:   #cccccc;
  --e-dim:     #888888;
  --e-r:       4px;
}

/* ── Global reset ─────────────────────────────────────────── */
html, body, .gradio-container {
  margin: 0 !important; padding: 0 !important;
  background: var(--e-bg) !important;
  color: var(--e-ink) !important;
  font-family: "Segoe UI", Tahoma, Geneva, Verdana, sans-serif !important;
  min-height: 100vh !important;
}
.gradio-container { max-width: 100% !important; }

/* ── App shell ─────────────────────────────────────────────── */
#app-shell {
  display: flex;
  flex-direction: column;
  height: 100vh;
}

/* ── Topbar ────────────────────────────────────────────────── */
#topbar {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 10px 20px;
  background: var(--e-surface);
  border-bottom: 1px solid var(--e-line);
  flex-shrink: 0;
}
#topbar .brand  { font-weight: 600; font-size: 1.05rem; white-space: nowrap; }
#topbar .fmeta  { font-size: 0.85rem; color: var(--e-dim); }
#topbar .conn   { margin-left: auto; font-size: 0.82rem; color: var(--e-green);
                  display: flex; align-items: center; gap: 5px; white-space: nowrap; }

/* ── Tab bar (in topbar) ───────────────────────────────────── */
/* elem_classes=["tab-bar"] on gr.Tabs, which Gradio renders inside the topbar row */
.tab-bar {
  margin-left: 20px;
}
.tab-bar .tab-nav {
  gap: 4px !important; background: transparent !important;
  border: none !important; padding: 0 !important;
  flex-wrap: nowrap !important;
}
.tab-bar .tab-nav button {
  background: transparent !important; border: none !important;
  border-radius: var(--e-r) !important;
  color: var(--e-muted) !important; font-size: 0.88rem !important;
  padding: 5px 11px !important; margin: 0 !important; box-shadow: none !important;
  white-space: nowrap !important;
}
.tab-bar .tab-nav button:hover:not(.selected) { background: var(--e-input) !important; }
.tab-bar .tab-nav button.selected {
  background: var(--e-blue) !important; color: #fff !important;
}

/* ── Body layout ───────────────────────────────────────────── */
#body-row {
  display: flex;
  flex: 1;
  overflow: hidden;
}

/* ── Sidebar ────────────────────────────────────────────────── */
#sidebar {
  width: 300px;
  min-width: 300px;
  background: var(--e-panel);
  border-right: 1px solid var(--e-line);
  padding: 12px;
  display: flex;
  flex-direction: column;
  gap: 14px;
  overflow-y: auto;
}
#sidebar h2 {
  margin: 0 0 8px;
  font-size: 0.92rem;
  font-weight: 600;
  color: var(--e-ink);
}

/* Sidebar buttons */
.sb-btn-row { display: flex; gap: 8px; margin-bottom: 10px; }
.sb-btn button {
  background: var(--e-input) !important; color: var(--e-ink) !important;
  border: 1px solid var(--e-line-l) !important;
  border-radius: var(--e-r) !important;
  font-size: 0.83rem !important; padding: 5px 11px !important;
}
.sb-btn button:hover { background: #4a4a4a !important; }

.sb-divider { border: none; border-top: 1px solid var(--e-line); margin: 2px 0; }

/* Folder tree */
.tree-root {
  list-style: none; padding: 0; margin: 0;
  font-size: 0.83rem; color: var(--e-muted);
}
.tree-row {
  display: flex; align-items: center; gap: 8px;
  padding: 4px 8px; border-radius: var(--e-r); cursor: pointer;
}
.tree-row:hover { background: var(--e-surface); }
.tree-row.sel   { background: var(--e-blue); color: #fff; }
.tree-row.sel .st-badge { color: #fff !important; }
.tree-i1 { padding-left: 20px; }
.tree-i2 { padding-left: 36px; }
.tree-i3 { padding-left: 52px; }

/* Status badges inside tree */
.st-badge  { font-family: "JetBrains Mono", monospace; font-size: 0.78rem; font-weight: 700; }
.st-done   { color: var(--e-green); }
.st-part   { color: #5bc0de; }
.st-fail   { color: var(--e-red); }
.st-empty  { color: var(--e-dim); }

/* Selected folder summary */
#sel-summary { font-size: 0.83rem; color: var(--e-muted); line-height: 1.5; }
#sel-summary strong { color: var(--e-ink); display: block; }

.sb-gallery-btn button {
  background: var(--e-green) !important; color: #fff !important;
  border: none !important; border-radius: var(--e-r) !important;
  font-weight: 600 !important; font-size: 0.85rem !important;
  width: 100% !important; margin-top: 8px !important;
  border-left: 4px solid rgba(255,255,255,0.3) !important;
}

/* Legend grid */
.legend-grid {
  display: grid; grid-template-columns: 1fr 1fr;
  gap: 6px; font-size: 0.82rem; color: var(--e-muted);
}

/* ── Dashboard ──────────────────────────────────────────────── */
#dashboard {
  flex: 1;
  padding: 18px 20px;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 18px;
  background: var(--e-bg);
}

/* ── Generic panel ──────────────────────────────────────────── */
.e-panel {
  background: var(--e-panel) !important;
  border: 1px solid var(--e-line) !important;
  border-radius: var(--e-r) !important;
  overflow: hidden !important;
}
.e-panel-hdr {
  padding: 11px 16px;
  border-bottom: 1px solid var(--e-line);
  background: #2a2a2a;
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.e-panel-hdr h3 { margin: 0; font-size: 0.95rem; font-weight: 600; }
.e-panel-hdr .hdr-meta { font-size: 0.82rem; color: var(--e-dim); }
.e-panel-body { padding: 16px; }

/* ── Stepper ────────────────────────────────────────────────── */
.stepper {
  display: flex; align-items: center;
  justify-content: space-between;
  gap: 8px; margin: 6px 0 24px;
}
.step {
  display: flex; flex-direction: column;
  align-items: center; gap: 6px; flex: 1;
}
.step-dot {
  width: 28px; height: 28px; border-radius: 50%;
  background: var(--e-surface);
  border: 2px solid var(--e-line-l);
  display: flex; align-items: center; justify-content: center;
  font-size: 0.8rem; font-weight: 700;
  color: var(--e-dim); position: relative; z-index: 2;
}
.step-label { font-size: 0.78rem; font-weight: 600; color: var(--e-muted); text-transform: uppercase; }
.step-count { font-size: 0.73rem; color: var(--e-dim); }

.step.done .step-dot  { border-color: var(--e-green); color: var(--e-green);
                         background: rgba(76,175,80,0.1); }
.step.running .step-dot { border-color: var(--e-blue); color: var(--e-blue);
                           background: rgba(0,122,204,0.1);
                           box-shadow: 0 0 0 4px rgba(0,122,204,0.2);
                           animation: blink 1.5s ease-in-out infinite; }
.connector {
  height: 2px; background: var(--e-line-l);
  flex: 1; margin-top: -50px; position: relative; z-index: 1;
}
.connector.done    { background: var(--e-green); }
.connector.running { background: linear-gradient(90deg, var(--e-green), var(--e-blue)); }

@keyframes blink { 0%,100%{opacity:1;} 50%{opacity:0.5;} }

/* ── Stepper action row ─────────────────────────────────────── */
.action-row { display: flex; gap: 10px; margin-top: 6px; }

.btn-primary button {
  background: var(--e-blue) !important; color: #fff !important;
  border: none !important; border-radius: var(--e-r) !important;
  font-size: 0.85rem !important; padding: 6px 14px !important;
}
.btn-primary button:hover { background: var(--e-blue-h) !important; }

.btn-stop button {
  background: transparent !important; color: var(--e-red) !important;
  border: 1px solid var(--e-red) !important; border-radius: var(--e-r) !important;
  font-size: 0.85rem !important; padding: 6px 14px !important;
}
.btn-stop button:hover { background: rgba(244,67,54,0.1) !important; }

.btn-ghost button {
  background: var(--e-input) !important; color: var(--e-ink) !important;
  border: 1px solid var(--e-line-l) !important; border-radius: var(--e-r) !important;
  font-size: 0.85rem !important; padding: 5px 12px !important;
}
.btn-ghost button:hover { background: #4a4a4a !important; }

/* ── Phase cards ────────────────────────────────────────────── */
.phase-grid { display: grid; grid-template-columns: repeat(3,1fr); gap: 14px; }

.phase-card {
  background: var(--e-surface) !important;
  border: 1px solid var(--e-line) !important;
  border-left: 4px solid var(--e-queued) !important;
  border-radius: var(--e-r) !important;
  padding: 14px !important;
  display: flex; flex-direction: column; gap: 10px;
}
.phase-card.running {
  border-color: var(--e-blue) !important;
  border-left-color: var(--e-blue) !important;
}

.pc-head {
  display: flex; justify-content: space-between; align-items: center;
}
.pc-title {
  display: flex; align-items: center; gap: 8px;
  font-weight: 600; font-size: 0.92rem;
}
.pc-icon {
  width: 24px; height: 24px; background: var(--e-input);
  border-radius: 4px;
  display: flex; align-items: center; justify-content: center;
  font-size: 0.78rem; font-weight: 700; color: var(--e-muted);
}
.phase-card.running .pc-icon {
  background: var(--e-blue); color: #fff;
}
.pc-status {
  font-size: 0.73rem; padding: 2px 7px;
  border-radius: 4px; background: var(--e-input);
  color: var(--e-muted); text-transform: uppercase;
  white-space: nowrap;
}
.phase-card.running .pc-status {
  background: rgba(0,122,204,0.2); color: #61baff;
}
.pc-stats { font-size: 0.82rem; color: var(--e-muted); }

.pc-bar  { height: 6px; background: var(--e-bg);
           border-radius: 3px; overflow: hidden; border: 1px solid var(--e-line); }
.pc-fill { height: 100%; background: var(--e-dim); transition: width 0.4s ease; }
.phase-card.running .pc-fill { background: var(--e-blue); }

/* ── Console panel ──────────────────────────────────────────── */
.console-hdr-row {
  display: flex; align-items: center; gap: 10px;
}
.console-box {
  background: #1e1e1e;
  border: 1px solid var(--e-line);
  border-radius: var(--e-r);
  padding: 14px;
  font-family: "JetBrains Mono", "Consolas", monospace;
  font-size: 0.82rem; color: #d4d4d4;
  line-height: 1.55; max-height: 200px; overflow-y: auto;
}
.cl { margin: 0; }
.ct { color: var(--e-dim); }
.ci { color: #4fc1ff; }
.cs { color: #b5cea8; }
.ce { color: #f44336; }
.c-footer { font-size: 0.78rem; color: var(--e-dim); margin-top: 8px; }

/* ── Tag propagation ────────────────────────────────────────── */
.tp-panel {
  background: var(--e-panel) !important;
  border: 1px solid var(--e-line) !important;
  border-radius: var(--e-r) !important;
  overflow: hidden !important;
}

/* ── Toast ──────────────────────────────────────────────────── */
#toast {
  position: fixed; bottom: 20px; right: 20px;
  background: #2a2a2a; border: 1px solid var(--e-line-l);
  border-radius: var(--e-r); padding: 9px 14px;
  font-size: 12.5px; color: var(--e-ink);
  box-shadow: 0 4px 14px rgba(0,0,0,0.5);
  opacity: 0; transform: translateY(6px);
  transition: opacity 0.18s, transform 0.18s;
  pointer-events: none; z-index: 9999;
}
#toast.show { opacity: 1; transform: translateY(0); }

/* ── Hide path storage textbox ──────────────────────────────── */
#selected-path { display: none !important; }
"""

# ── JS — runs at page load (passed to launch() per Gradio 6 guide) ────────────
JS_INIT = """
() => {
  /* Toast helper */
  function toast(msg, ms) {
    ms = ms || 2000;
    let el = document.getElementById('toast');
    if (!el) { el = document.createElement('div'); el.id = 'toast'; document.body.appendChild(el); }
    el.textContent = msg;
    el.classList.add('show');
    clearTimeout(el._t);
    el._t = setTimeout(function() { el.classList.remove('show'); }, ms);
  }
  window._toast = toast;

  /* Tree click — delegate on document */
  document.addEventListener('click', function(e) {
    var row = e.target.closest('.tree-row');
    if (!row) return;
    document.querySelectorAll('.tree-row.sel').forEach(function(r) { r.classList.remove('sel'); });
    row.classList.add('sel');
    var spans = row.querySelectorAll('span');
    var name = spans.length > 1 ? spans[spans.length-1].textContent.trim() : '?';
    var sum = document.getElementById('sel-summary');
    if (sum) sum.innerHTML = '<strong>' + name + '</strong>48 images';
    /* Push to hidden Gradio textbox */
    var tb = document.querySelector('#selected-path textarea');
    if (tb) { tb.value = name; tb.dispatchEvent(new Event('input', {bubbles:true})); }
    toast('📁  ' + name);
  });

  /* Simulated progress tick */
  var pct = 66.7;
  var ticker = null;

  function startTick() {
    if (ticker) return;
    ticker = setInterval(function() {
      pct = Math.min(pct + 1.3, 100);
      var n = Math.round(pct / 100 * 48);
      /* Phase card */
      document.querySelectorAll('.phase-card.running .pc-fill').forEach(function(el) {
        el.style.width = pct + '%';
      });
      document.querySelectorAll('.phase-card.running .pc-stats').forEach(function(el) {
        el.textContent = n + ' / 48 images processed';
      });
      /* Stepper */
      var sc = document.querySelectorAll('.step-count')[2];
      if (sc) sc.textContent = n + ' / 48';
      /* Console append */
      var box = document.querySelector('.console-box');
      if (box) {
        var p = document.createElement('p');
        p.className = 'cl';
        var t = new Date().toLocaleTimeString('en-GB');
        p.innerHTML = '<span class="ct">[' + t + ']</span> <span class="cs">SUCCESS</span> scored IMG_' + (1832+n) + '.NEF  score=' + (0.5 + Math.random()*0.45).toFixed(2);
        box.appendChild(p);
        var as = document.querySelector('#autoscroll-cb input');
        if (!as || as.checked) box.scrollTop = box.scrollHeight;
      }
      if (pct >= 100) {
        clearInterval(ticker); ticker = null;
        toast('✅  Scoring complete — 48/48', 3200);
        /* done state */
        document.querySelectorAll('.phase-card.running').forEach(function(el) {
          el.classList.remove('running');
          el.style.borderLeftColor = '#4caf50';
        });
        var dot = document.querySelector('.step.running .step-dot');
        var step = document.querySelector('.step.running');
        if (dot) { dot.parentElement.classList.remove('running'); dot.parentElement.classList.add('done'); }
      }
    }, 750);
  }

  function stopTick() {
    clearInterval(ticker); ticker = null;
    toast('⏹  Stopped');
  }

  window._startTick = startTick;
  window._stopTick  = stopTick;

  /* Console clear */
  document.addEventListener('click', function(e) {
    if (e.target.id === 'console-clear') {
      var box = document.querySelector('.console-box');
      if (box) box.innerHTML = '';
      toast('Console cleared');
    }
  });

  /* Keyboard shortcuts */
  document.addEventListener('keydown', function(e) {
    var tag = document.activeElement && document.activeElement.tagName;
    if (tag === 'INPUT' || tag === 'TEXTAREA') return;
    if (e.key === 'r' && !e.ctrlKey && !e.metaKey) {
      document.querySelector('#btn-run-all button') && document.querySelector('#btn-run-all button').click();
    }
    if (e.key === 'Escape') {
      document.querySelector('#btn-stop button') && document.querySelector('#btn-stop button').click();
    }
  });

  toast('💡  r = Run All  ·  Esc = Stop', 3200);
}
"""

JS_RUN  = "(inputs, outputs) => { window._startTick && window._startTick(); return []; }"
JS_STOP = "(inputs, outputs) => { window._stopTick  && window._stopTick();  return []; }"


# ── HTML helpers ──────────────────────────────────────────────────────────────

def _topbar_html() -> str:
    return """
<div id="topbar">
  <div class="brand">Vexlum WebUI</div>
  <div class="fmeta">/Photos/D300/28-70mm/2015 — 48 images</div>
  <div class="conn">● Connected</div>
</div>"""


def _tree_html() -> str:
    return """
<ul class="tree-root">
  <li class="tree-row"><span class="st-badge st-empty">+</span><span>Photos</span></li>
  <li class="tree-row tree-i1"><span class="st-badge st-empty">+</span><span>D300</span></li>
  <li class="tree-row tree-i2"><span class="st-badge st-empty">+</span><span>28-70mm</span></li>
  <li class="tree-row tree-i3 sel"><span class="st-badge st-part">P</span><span>2015</span></li>
  <li class="tree-row tree-i1"><span class="st-badge st-empty">+</span><span>D90</span></li>
  <li class="tree-row tree-i2"><span class="st-badge st-empty">+</span><span>10.5mm</span></li>
  <li class="tree-row tree-i3"><span class="st-badge st-done">D</span><span>2013</span></li>
</ul>"""


def _legend_html() -> str:
    return """
<div class="legend-grid">
  <span><strong class="st-badge st-done">D</strong> Done</span>
  <span><strong class="st-badge st-part">P</strong> Running</span>
  <span><strong class="st-badge st-fail">F</strong> Failed</span>
  <span><strong class="st-badge st-empty">N</strong> Not started</span>
</div>"""


def _stepper_html() -> str:
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
</div>"""


def _phase_card(icon: str, title: str, status: str, n: int, total: int,
                pct: float, running: bool = False, queued: bool = False) -> str:
    card_cls = "phase-card running" if running else "phase-card queued" if queued else "phase-card"
    return f"""
<div class="{card_cls}">
  <div class="pc-head">
    <div class="pc-title">
      <div class="pc-icon">{icon}</div>
      {title}
    </div>
    <div class="pc-status">{status}</div>
  </div>
  <div class="pc-stats">{n} / {total} images processed</div>
  <div class="pc-bar"><div class="pc-fill" style="width:{pct:.1f}%"></div></div>
</div>"""


def _console_html() -> str:
    return """
<div class="console-box">
  <p class="cl"><span class="ct">[10:12:21]</span> <span class="ci">INFO</span> model loaded: mobilenet_v2 + aesthetic head</p>
  <p class="cl"><span class="ct">[10:12:22]</span> <span class="ci">INFO</span> scanning 48 candidate files from selected folder</p>
  <p class="cl"><span class="ct">[10:12:24]</span> <span class="cs">SUCCESS</span> scored IMG_1832.NEF  score=0.82</p>
  <p class="cl"><span class="ct">[10:12:25]</span> <span class="cs">SUCCESS</span> scored IMG_1833.NEF  score=0.77</p>
  <p class="cl"><span class="ct">[10:12:25]</span> <span class="ci">INFO</span> updating DB IMAGE_PHASE_STATUS row_id=8941</p>
  <p class="cl"><span class="ct">[10:12:28]</span> <span class="cs">SUCCESS</span> scored IMG_1834.NEF  score=0.69</p>
</div>
<p class="c-footer">Monitor rotates to Culling → Keywords automatically when they become active.</p>"""


# ── Layout ────────────────────────────────────────────────────────────────────
with gr.Blocks(title="Vexlum WebUI", css=CSS, head=HEAD, js=JS_INIT) as demo:
    # Hidden textbox for tree → Python state (guide pattern: elem_id targeting from JS)
    selected_path = gr.Textbox(value="2015", elem_id="selected-path", visible=False)

    with gr.Column(elem_id="app-shell"):

        # Topbar (brand + folder meta + connection status)
        with gr.Row(elem_id="topbar-row"):
            gr.HTML(_topbar_html())
            # Tabs live in the topbar visually (styled with .tab-bar to float alongside)
            with gr.Tabs(elem_classes=["tab-bar"]):

                # ── Pipeline tab ──────────────────────────────────────────
                with gr.Tab("Pipeline"):
                    with gr.Row(elem_id="body-row", equal_height=False):

                        # Sidebar
                        with gr.Column(elem_id="sidebar", scale=0, min_width=300):
                            gr.HTML("<h2>Folders</h2>")
                            with gr.Row(elem_classes=["sb-btn-row"]):
                                gr.Button("Refresh",  elem_classes=["sb-btn"])
                                gr.Button("Collapse", elem_classes=["sb-btn"])
                            gr.HTML(_tree_html())
                            gr.HTML("<hr class='sb-divider'>")
                            gr.HTML("<h2>Selected Folder</h2>")
                            gr.HTML("<div id='sel-summary'><strong>D300 / 28-70mm / 2015</strong>48 images</div>")
                            gr.Button("Back to Gallery", elem_classes=["sb-gallery-btn"])
                            gr.HTML("<hr class='sb-divider'>")
                            gr.HTML("<h2>Legend</h2>")
                            gr.HTML(_legend_html())

                        # Dashboard
                        with gr.Column(elem_id="dashboard", scale=1):

                            # Panel A — Pipeline progress + actions
                            with gr.Group(elem_classes=["e-panel"]):
                                gr.HTML("""
<div class="e-panel-hdr">
  <h3>Pipeline Progress</h3>
  <span class="hdr-meta">Active: Scoring Mode</span>
</div>""")
                                with gr.Column(elem_classes=["e-panel-body"]):
                                    gr.HTML(_stepper_html())
                                    with gr.Row(elem_classes=["action-row"]):
                                        run_btn  = gr.Button("Run All Pending", elem_classes=["btn-primary"], elem_id="btn-run-all")
                                        stop_btn = gr.Button("Stop All",        elem_classes=["btn-stop"],    elem_id="btn-stop")

                            # Panel B — Phase cards
                            with gr.Group(elem_classes=["e-panel"]):
                                with gr.Column(elem_classes=["e-panel-body"]):
                                    with gr.Row(equal_height=True):
                                        with gr.Column(elem_classes=["phase-card", "running"]):
                                            gr.HTML(_phase_card("S", "Scoring", "Running",    32, 48, 66.7, running=True))
                                            gr.Button("Pause Scoring", elem_classes=["btn-primary"])
                                            with gr.Accordion("Options", open=False):
                                                gr.Checkbox(label="Force re-score existing")
                                                gr.Checkbox(label="Check metadata before scoring")

                                        with gr.Column(elem_classes=["phase-card", "queued"]):
                                            gr.HTML(_phase_card("C", "Culling",  "Queued",     0,  48, 0.0,  queued=True))
                                            gr.Button("Run Culling",  elem_classes=["btn-ghost"])
                                            with gr.Accordion("Options", open=False):
                                                gr.Checkbox(label="Force re-run")

                                        with gr.Column(elem_classes=["phase-card", "queued"]):
                                            gr.HTML(_phase_card("K", "Keywords", "Queued",     0,  48, 0.0,  queued=True))
                                            gr.Button("Run Keywords", elem_classes=["btn-ghost"])
                                            with gr.Accordion("Options", open=False):
                                                gr.Checkbox(label="Overwrite existing tags")
                                                gr.Checkbox(label="Generate captions")

                            # Panel C — Active job monitor / console
                            with gr.Group(elem_classes=["e-panel"]):
                                gr.HTML("""
<div class="e-panel-hdr">
  <h3>Active Job Monitor (Scoring)</h3>
  <div class="console-hdr-row">
    <label id="autoscroll-cb" style="display:flex;align-items:center;gap:6px;font-size:0.82rem;color:#888;cursor:pointer;">
      <input type="checkbox" checked> Auto-scroll
    </label>
    <button id="console-clear" style="background:#3c3c3c;border:1px solid #555;color:#ccc;border-radius:4px;padding:2px 9px;font-size:0.78rem;cursor:pointer;">Clear</button>
  </div>
</div>""")
                                with gr.Column(elem_classes=["e-panel-body"]):
                                    gr.HTML(_console_html())

                            # Tag propagation (utility, below console)
                            with gr.Accordion("Tag Propagation", open=False, elem_classes=["tp-panel"]):
                                gr.HTML("<div style='padding:14px 16px;'>")
                                gr.HTML("<div class='e-panel-hdr' style='margin:-14px -16px 14px;'><h3>Tag Propagation</h3></div>")
                                gr.HTML("<p style='font-size:0.83rem;color:#888;margin:0 0 10px;'>Propagate keywords to untagged neighbors via visual similarity.</p>")
                                with gr.Row():
                                    gr.Button("Preview",         elem_classes=["btn-ghost"])
                                    gr.Button("Run Propagation", elem_classes=["btn-ghost"])
                                    gr.Checkbox(label="Dry Run", value=True)
                                gr.HTML("</div>")

                # ── Gallery tab ───────────────────────────────────────────
                with gr.Tab("Gallery"):
                    with gr.Group(elem_classes=["e-panel"]):
                        gr.HTML("<div class='e-panel-hdr'><h3>Gallery</h3></div>")
                        gr.Markdown("This tab remains unmodified.", elem_classes=["e-panel-body"])

                # ── Settings tab ──────────────────────────────────────────
                with gr.Tab("Settings"):
                    with gr.Group(elem_classes=["e-panel"]):
                        gr.HTML("<div class='e-panel-hdr'><h3>Settings</h3></div>")
                        gr.Markdown("Settings tab.", elem_classes=["e-panel-body"])

    # Event wiring — js= runs client-side before Python (guide pattern)
    run_btn.click(fn=lambda: None, js=JS_RUN)
    stop_btn.click(fn=lambda: None, js=JS_STOP)


if __name__ == "__main__":
    demo.launch(server_name="127.0.0.1", server_port=7871)

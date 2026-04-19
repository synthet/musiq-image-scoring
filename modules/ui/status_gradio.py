"""
Minimal operator status page for /app.

Architecture (no-blink):
  - build_status_demo() returns a gr.Blocks with ONE static gr.HTML skeleton.
  - A polling <script> injected via gr.Blocks(head=...) calls /api/status/data
    every 2 s and updates individual <div> innerHTML in-place.
  - No gr.Timer, no Gradio component updates after initial render → zero flicker.

render_status_data() is called by the FastAPI endpoint to produce JSON sections.
"""
import html
import threading
from datetime import datetime
from pathlib import Path

import gradio as gr

from modules.ui.tabs.pipeline import get_runner_activity_snapshot

# ── Design tokens (matched to React frontend src/styles/layout.css + tokens.css) ──

_BG = "#1e1e1e"
_BG_DARKER = "#121212"
_BG_CARD = "#1a1a1a"
_BG_LIGHT = "#252526"
_BG_CONSOLE = "#0d0d0d"
_BORDER = "#333333"
_BORDER_DIM = "#2a2a2a"
_TEXT = "#e0e0e0"
_TEXT_DIM = "#aaaaaa"
_TEXT_MID = "#888"
_TEXT_FAINT = "#555"
_ACCENT = "#007acc"
_SUCCESS = "#4caf50"
_RUNNING = "#4a9eff"
_WARN = "#f0a500"
_ERROR = "#e05050"
_FONT = "'Segoe UI', Tahoma, Geneva, Verdana, sans-serif"
_MONO = "'Cascadia Code', 'Consolas', 'Courier New', monospace"

# ── Gradio dark-theme CSS override ───────────────────────────────────────────

_DARK_CSS = f"""
html, body {{
    height: 100% !important;
    overflow: hidden !important;
    background: {_BG} !important;
    color: {_TEXT} !important;
    font-family: {_FONT} !important;
}}
/* Lock every Gradio wrapper so only our inner content div scrolls */
.gradio-container, .app, .main, .wrap, .contain, .svelte-1ipelgc, .svelte-182fdeq {{
    height: 100% !important;
    max-height: 100% !important;
    overflow: hidden !important;
    background: {_BG} !important;
    color: {_TEXT} !important;
    font-family: {_FONT} !important;
    max-width: 100% !important;
    padding: 0 !important;
    margin: 0 !important;
}}
.block, .form, .gap, .padded {{
    background: transparent !important;
    border: none !important;
    box-shadow: none !important;
    padding: 0 !important;
    gap: 0 !important;
    overflow: hidden !important;
    height: 100% !important;
}}
footer, .footer, .svelte-footer {{
    display: none !important;
}}
"""

# ── Polling script injected into <head> ──────────────────────────────────────

_POLL_HEAD = """
<script>
(function () {
  var INTERVAL = 2000;
  var ENDPOINT = '/api/status/data';
  var SECTIONS = ['runners', 'threads', 'profiling', 'jobs', 'diagnostics', 'log'];

  // Save open/closed state of all <details> inside el, keyed by summary text.
  function saveDetails(el) {
    var state = {};
    el.querySelectorAll('details').forEach(function (d, i) {
      var s = d.querySelector('summary');
      var key = s ? s.textContent.trim() : String(i);
      state[key] = d.open;
    });
    return state;
  }

  // Re-apply saved open/closed state after innerHTML replacement.
  function restoreDetails(el, state) {
    el.querySelectorAll('details').forEach(function (d, i) {
      var s = d.querySelector('summary');
      var key = s ? s.textContent.trim() : String(i);
      if (key in state) d.open = state[key];
    });
  }

  function applyData(d) {
    var ts = document.getElementById('s-timestamp');
    if (ts) ts.textContent = 'Updated ' + d.ts;
    SECTIONS.forEach(function (k) {
      var el = document.getElementById('s-' + k);
      if (!el || d[k] === undefined) return;
      var saved = saveDetails(el);
      el.innerHTML = d[k];
      restoreDetails(el, saved);
    });
  }

  function doRefresh() {
    fetch(ENDPOINT)
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (d) { if (d) applyData(d); })
      .catch(function () {});
  }

  function waitAndStart() {
    if (document.getElementById('status-page')) {
      doRefresh();
      setInterval(doRefresh, INTERVAL);
    } else {
      setTimeout(waitAndStart, 300);
    }
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', function () { setTimeout(waitAndStart, 400); });
  } else {
    setTimeout(waitAndStart, 400);
  }
})();
</script>
"""

# ── Static HTML skeleton (rendered once, sections updated in-place by JS) ────

def _skeleton_html() -> str:
    top_bar = (
        f"<div style='height:40px;background:{_BG_LIGHT};border-bottom:1px solid {_BORDER};"
        f"display:flex;align-items:center;padding:0 16px;gap:12px;flex-shrink:0;'>"
        f"<span style='font-weight:600;font-size:0.9em;color:{_TEXT}'>Image Scoring — Status</span>"
        f"<span id='s-timestamp' style='color:{_TEXT_FAINT};font-size:0.78em;margin-left:auto'>"
        f"Connecting…</span></div>"
    )
    loading = f"<div style='color:{_TEXT_FAINT};font-style:italic;font-size:0.85em;padding:6px 0'>Loading…</div>"
    sections = "".join(
        f"<div id='s-{k}' style='margin-bottom:10px'>{loading}</div>"
        for k in ["runners", "threads", "profiling", "jobs", "diagnostics", "log"]
    )
    content = (
        f"<div style='padding:14px;overflow-y:auto;height:calc(100vh - 40px);box-sizing:border-box'>"
        f"{sections}</div>"
    )
    return (
        f"<div id='status-page' style='font-family:{_FONT};background:{_BG};color:{_TEXT};"
        f"height:100vh;overflow:hidden;display:flex;flex-direction:column;'>"
        f"{top_bar}{content}</div>"
    )


# ── HTML helpers ──────────────────────────────────────────────────────────────

def _th(label: str) -> str:
    return (
        f"<th style='padding:6px 10px;border-bottom:1px solid {_BORDER};color:{_TEXT_MID};"
        f"font-weight:600;text-align:left;font-size:0.75em;text-transform:uppercase;"
        f"letter-spacing:0.04em;white-space:nowrap'>{label}</th>"
    )


def _td(content: str, color: str = "") -> str:
    style = f"padding:5px 10px;border-bottom:1px solid {_BORDER_DIM};font-size:0.82em;"
    if color:
        style += f"color:{color};"
    return f"<td style='{style}'>{content}</td>"


def _table(headers: list, rows: list) -> str:
    head = "<tr>" + "".join(_th(h) for h in headers) + "</tr>"
    body = "".join("<tr>" + "".join(_td(c) for c in row) + "</tr>" for row in rows)
    return (
        f"<div style='overflow-x:auto'><table style='border-collapse:collapse;width:100%;"
        f"font-size:0.85em'><thead>{head}</thead><tbody>{body}</tbody></table></div>"
    )


def _section(title: str, body: str, open: bool = True) -> str:
    tag = "open" if open else ""
    summary_style = (
        f"font-weight:600;font-size:0.78em;text-transform:uppercase;letter-spacing:0.05em;"
        f"color:{_TEXT_MID};cursor:pointer;padding:6px 0;list-style:none;"
        f"display:flex;align-items:center;gap:6px;user-select:none"
    )
    card_style = (
        f"background:{_BG_CARD};border:1px solid {_BORDER};border-radius:8px;"
        f"padding:12px 14px;margin-top:6px"
    )
    return (
        f"<details {tag}><summary style='{summary_style}'>▸ {title}</summary>"
        f"<div style='{card_style}'>{body}</div></details>"
    )


def _status_badge(status: str) -> str:
    color = {
        "running": _RUNNING, "done": _SUCCESS, "completed": _SUCCESS,
        "failed": _ERROR, "error": _ERROR,
        "queued": _WARN, "not_started": _TEXT_FAINT,
    }.get(status.lower().replace(" ", "_"), _TEXT_MID)
    return (
        f"<span style='font-size:0.72em;font-weight:600;color:{color};"
        f"text-transform:uppercase;letter-spacing:0.05em'>"
        f"{html.escape(status.upper())}</span>"
    )


# ── Section renderers ─────────────────────────────────────────────────────────

def _render_runners(scoring_runner, tagging_runner, selection_runner, orchestrator, clustering_runner=None) -> str:
    snap = get_runner_activity_snapshot(scoring_runner, tagging_runner, selection_runner, clustering_runner)

    cards = []
    for r in snap["runners"]:
        pct = int(r["current"] / r["total"] * 100) if r["total"] else 0
        status_str = "running" if r["running"] else "idle"
        status_color = _RUNNING if r["running"] else _TEXT_FAINT
        progress_bar = ""
        if r["running"] and r["total"]:
            progress_bar = (
                f"<div style='background:#333;border-radius:4px;height:4px;overflow:hidden;margin-top:8px'>"
                f"<div style='background:{_RUNNING};width:{pct}%;height:100%;transition:width 0.3s'></div>"
                f"</div>"
                f"<div style='font-size:0.72em;color:{_TEXT_FAINT};margin-top:3px'>"
                f"{r['current']} / {r['total']} ({pct}%)</div>"
            )
        msg_html = ""
        if r["running"] and r["message"]:
            msg_html = f"<div style='font-size:0.78em;color:{_TEXT_DIM};margin-top:4px'>{html.escape(r['message'])}</div>"

        card = (
            f"<div style='background:{_BG_CARD};border:1px solid {_BORDER};border-radius:8px;padding:12px 14px'>"
            f"<div style='display:flex;justify-content:space-between;align-items:center'>"
            f"<span style='font-weight:600;font-size:0.9em'>{html.escape(r['name'])}</span>"
            f"<span style='font-size:0.72em;font-weight:600;color:{status_color};"
            f"text-transform:uppercase;letter-spacing:0.05em'>{status_str}</span>"
            f"</div>{progress_bar}{msg_html}</div>"
        )
        cards.append(card)

    grid = (
        f"<div style='display:grid;grid-template-columns:repeat(auto-fill,minmax(180px,1fr));"
        f"gap:10px;margin-bottom:10px'>" + "".join(cards) + "</div>"
    )

    orch = orchestrator.get_status()
    orch_active = orch.get("active", False)
    orch_job = orch.get("job_id") or "—"
    orch_phase = html.escape(str(orch.get("current_phase") or "—"))
    orch_folder = html.escape(str(orch.get("folder_path") or "—"))
    pending = html.escape(", ".join(orch.get("pending_phases") or []) or "—")
    orch_color = _RUNNING if orch_active else _TEXT_FAINT
    orch_row = (
        f"<div style='font-size:0.8em;color:{_TEXT_DIM};margin-top:4px;"
        f"border-top:1px solid {_BORDER_DIM};padding-top:8px'>"
        f"<span style='color:{orch_color};font-weight:600'>"
        f"{'● Orchestrator active' if orch_active else '○ Orchestrator idle'}</span>"
        f" &nbsp; job=<b>{orch_job}</b>"
        f" &nbsp; phase=<b>{orch_phase}</b>"
        f" &nbsp; pending=<b>{pending}</b>"
        f"<br><span style='color:{_TEXT_FAINT}'>{orch_folder}</span>"
        f"</div>"
    )

    return grid + orch_row


def _render_threads() -> str:
    threads = sorted(threading.enumerate(), key=lambda t: t.name)
    rows = [
        [
            html.escape(t.name),
            str(t.ident),
            "✓" if t.daemon else "—",
            "✓" if t.is_alive() else "✗",
        ]
        for t in threads
    ]
    table = _table(["Name", "Ident", "Daemon", "Alive"], rows)
    return _section(f"Threads ({len(threads)})", table)


def _render_profiling() -> str:
    from modules.profiling import get_tracker, get_loop_monitor

    tracker = get_tracker()
    monitor = get_loop_monitor()

    if tracker is None:
        return _section("Event loop &amp; HTTP", "<em style='color:#555'>Profiling not initialized</em>")

    stats = tracker.get_stats()

    if monitor:
        lag = monitor.get_stats()
        lag_ms = lag["current_lag_ms"]
        lag_color = _ERROR if lag_ms >= 1000 else (_WARN if lag_ms >= 200 else _SUCCESS)
        loop_line = (
            f"<div style='margin-bottom:8px'>"
            f"<span style='color:{lag_color};font-weight:600'>loop lag {lag_ms}ms</span>"
            f" &nbsp; peak {lag['peak_lag_ms']}ms"
            f" &nbsp; avg {lag['avg_lag_ms']}ms"
            f" &nbsp; p95 {lag['p95_lag_ms']}ms"
            f" &nbsp; warnings {lag['total_warnings']}"
            f"</div>"
        )
    else:
        loop_line = f"<div style='color:{_TEXT_FAINT}'>Loop monitor not running</div>"

    req_line = (
        f"<div style='font-size:0.82em;color:{_TEXT_DIM};margin-bottom:8px'>"
        f"total <b style='color:{_TEXT}'>{stats['total_requests']}</b>"
        f" &nbsp; in-flight <b style='color:{_TEXT}'>{stats['in_flight']}</b>"
        f" &nbsp; peak concurrent <b style='color:{_TEXT}'>{stats['peak_concurrent']}</b>"
        f" &nbsp; slow <b style='color:{_WARN}'>{stats['total_slow']}</b>"
        f" &nbsp; errors <b style='color:{_ERROR}'>{stats['total_errors']}</b>"
        f"</div>"
    )

    in_flight = tracker.get_in_flight()
    if in_flight:
        flight_rows = [[r["method"], html.escape(r["path"]), str(r["duration_ms"]), str(r["started_ago_s"])] for r in in_flight]
        flight_table = (
            f"<div style='margin-bottom:6px;font-size:0.78em;color:{_TEXT_MID};font-weight:600;"
            f"text-transform:uppercase;letter-spacing:0.04em'>In-flight</div>"
            + _table(["Method", "Path", "ms", "Ago s"], flight_rows)
        )
    else:
        flight_table = f"<div style='font-size:0.82em;color:{_TEXT_FAINT}'>No in-flight requests</div>"

    slow = tracker.get_slow_history(limit=5)
    if slow:
        slow_rows = [[r["method"], html.escape(r["path"]), str(r["duration_ms"]), str(r.get("status_code", ""))] for r in slow]
        slow_table = (
            f"<div style='margin-top:10px;margin-bottom:6px;font-size:0.78em;color:{_TEXT_MID};"
            f"font-weight:600;text-transform:uppercase;letter-spacing:0.04em'>Recent slow</div>"
            + _table(["Method", "Path", "ms", "Status"], slow_rows)
        )
    else:
        slow_table = ""

    body = loop_line + req_line + flight_table + slow_table
    return _section("Event loop &amp; HTTP profiling", body)


def _render_recent_jobs() -> str:
    try:
        from modules import db
        jobs = db.get_jobs(limit=10) or []
    except Exception as exc:
        body = f"<em style='color:{_TEXT_FAINT}'>DB unavailable: {html.escape(str(exc))}</em>"
        return _section("Recent jobs", body)

    if not jobs:
        return _section("Recent jobs (last 10)", f"<em style='color:{_TEXT_FAINT}'>No jobs found</em>")

    terminal = {"completed", "failed", "canceled", "cancelled", "interrupted"}
    rows = []
    for j in jobs:
        jid = j.get("id", "")
        link = (
            f"<a href='/ui/runs/{jid}' style='color:#4fc1ff'>View</a>"
            if j.get("status") in terminal
            else "—"
        )
        rows.append(
            [
                str(jid),
                html.escape(str(j.get("job_type") or "—")),
                html.escape(str(j.get("status") or "—")),
                html.escape(str(j.get("enqueued_at") or j.get("created_at") or "—")),
                link,
            ]
        )
    return _section("Recent jobs (last 10)", _table(["ID", "Type", "Status", "Enqueued", "Report"], rows), open=False)


def _render_diagnostics() -> str:
    from modules.diagnostics import get_diagnostics
    try:
        diag = get_diagnostics()
        
        # System
        sys_rows = [
            ["OS", f"{diag['system']['os']} {diag['system']['os_release']}"],
            ["Python", diag['system']['python_version'].split('\n')[0]],
            ["CPU", str(diag['system']['cpu_count'])],
        ]
        if "memory_total_gb" in diag["system"]:
            sys_rows.append(["Memory", f"{diag['system']['memory_available_gb']} / {diag['system']['memory_total_gb']} GB ({diag['system']['memory_percent']}%)"])
            
        # Database
        db_rows = [
            ["Type", diag['database']['type']],
            ["Path", html.escape(diag['database']['path'])],
            ["Reachable", "✓" if diag['database']['reachable'] else "✗"],
            ["Size", f"{diag['database']['size_mb']} MB"],
        ]
        
        # Models
        model_rows = [
            ["GPU", "✓" if diag['models']['gpu_available'] else "✗"],
            ["Frameworks", ", ".join(diag['models']['frameworks'])],
        ]
        if "torch_gpu_name" in diag["models"]:
            model_rows.append(["Device", diag['models']['torch_gpu_name']])
            
        # Filesystem
        fs_rows = [
            ["Free Space", f"{diag['filesystem']['free_space_gb']} GB"],
        ]
        
        body = (
            "<div style='display:grid;grid-template-columns:repeat(auto-fill,minmax(250px,1fr));gap:15px'>"
            f"<div><div style='font-size:0.75em;font-weight:600;color:{_TEXT_MID};margin-bottom:5px'>SYSTEM</div>{_table(['Key', 'Value'], sys_rows)}</div>"
            f"<div><div style='font-size:0.75em;font-weight:600;color:{_TEXT_MID};margin-bottom:5px'>DATABASE</div>{_table(['Key', 'Value'], db_rows)}</div>"
            f"<div><div style='font-size:0.75em;font-weight:600;color:{_TEXT_MID};margin-bottom:5px'>MODELS</div>{_table(['Key', 'Value'], model_rows)}</div>"
            f"<div><div style='font-size:0.75em;font-weight:600;color:{_TEXT_MID};margin-bottom:5px'>FILESYSTEM</div>{_table(['Key', 'Value'], fs_rows)}</div>"
            "</div>"
        )
        return _section("Diagnostics", body, open=False)
    except Exception as exc:
        return _section("Diagnostics", f"<em style='color:{_ERROR}'>Error: {html.escape(str(exc))}</em>")


_LOG_SECTION_MAX = 40


def _colorize_log_line(stripped: str) -> str:
    low = stripped.lower()
    if " error" in low or "error:" in low:
        color = _ERROR
    elif " warning" in low or " warn" in low:
        color = _WARN
    else:
        color = "#cccccc"
    return (
        f"<div style='color:{color};margin-bottom:1px;line-height:1.4'>"
        f"{html.escape(stripped)}</div>"
    )


def _render_log_subsection(
    *,
    summary_label: str,
    resolved_path: Path,
    max_lines: int,
) -> str:
    """One nested <details> block for a log file path."""
    from modules.ui.log_views import read_log_tail

    path_str = html.escape(str(resolved_path))
    if not resolved_path.exists():
        # Log dir may exist (e.g. get_debug_log_path makedirs) but file not created yet — same UX as empty file
        if resolved_path.parent.exists():
            inner = f"<em style='color:{_TEXT_FAINT}'>No lines yet — {path_str}</em>"
        else:
            inner = f"<em style='color:{_TEXT_FAINT}'>Not found — {path_str}</em>"
        return (
            f"<details open style='margin-bottom:8px'>"
            f"<summary style='font-size:0.78em;font-weight:600;color:{_TEXT_MID};cursor:pointer;padding:4px 0'>"
            f"{html.escape(summary_label)}</summary>"
            f"<div style='margin-top:6px'>{inner}</div></details>"
        )

    tail_info = read_log_tail(resolved_path, max_lines)
    if tail_info.get("error"):
        err = f"<em style='color:{_ERROR}'>Read error: {html.escape(str(tail_info['error']))}</em>"
        return (
            f"<details open style='margin-bottom:8px'>"
            f"<summary style='font-size:0.78em;font-weight:600;color:{_TEXT_MID};cursor:pointer;padding:4px 0'>"
            f"{html.escape(summary_label)}</summary>"
            f"<div style='margin-top:6px'>{err}</div></details>"
        )

    tail_lines = tail_info.get("lines") or []
    if not tail_lines:
        inner = f"<em style='color:{_TEXT_FAINT}'>No lines yet — {path_str}</em>"
        return (
            f"<details open style='margin-bottom:8px'>"
            f"<summary style='font-size:0.78em;font-weight:600;color:{_TEXT_MID};cursor:pointer;padding:4px 0'>"
            f"{html.escape(summary_label)}</summary>"
            f"<div style='margin-top:6px'>{inner}</div></details>"
        )

    colored = "".join(_colorize_log_line(line) for line in tail_lines)
    header_bar = (
        f"<div style='display:flex;justify-content:space-between;align-items:center;"
        f"padding-bottom:6px;margin-bottom:6px;border-bottom:1px solid {_BORDER_DIM}'>"
        f"<span style='font-size:0.72em;color:{_TEXT_FAINT};word-break:break-all'>{path_str}</span>"
        f"<span style='font-size:0.72em;color:{_TEXT_FAINT};white-space:nowrap'>last {len(tail_lines)} lines</span>"
        f"</div>"
    )
    console = (
        f"<div style='font-family:{_MONO};font-size:0.78em;background:{_BG_CONSOLE};"
        f"padding:8px 10px;border-radius:4px;max-height:280px;overflow-y:auto;line-height:1.5'>"
        f"{colored}</div>"
    )
    return (
        f"<details open style='margin-bottom:8px'>"
        f"<summary style='font-size:0.78em;font-weight:600;color:{_TEXT_MID};cursor:pointer;padding:4px 0'>"
        f"{html.escape(summary_label)}</summary>"
        f"<div style='margin-top:6px'>{header_bar}{console}</div></details>"
    )


def _render_log() -> str:
    from modules.ui.log_views import resolve_debug_log_path, resolve_webui_log_path

    app_path = resolve_webui_log_path()
    debug_path = resolve_debug_log_path()

    body = (
        _render_log_subsection(
            summary_label="Application (webui.log)",
            resolved_path=app_path,
            max_lines=_LOG_SECTION_MAX,
        )
        + _render_log_subsection(
            summary_label="Debug (debug.log)",
            resolved_path=debug_path,
            max_lines=_LOG_SECTION_MAX,
        )
    )
    return _section("Log", body, open=True)


# ── Public API ────────────────────────────────────────────────────────────────

def render_status_data(
    scoring_runner, tagging_runner, selection_runner, orchestrator, *, clustering_runner=None
) -> dict:
    """Return JSON-serialisable dict consumed by /api/status/data endpoint."""
    return {
        "ts": datetime.now().strftime("%H:%M:%S"),
        "runners": _render_runners(scoring_runner, tagging_runner, selection_runner, orchestrator, clustering_runner),
        "threads": _render_threads(),
        "profiling": _render_profiling(),
        "jobs": _render_recent_jobs(),
        "diagnostics": _render_diagnostics(),
        "log": _render_log(),
    }


def build_status_demo(
    runner, tagging_runner, selection_runner, orchestrator, *, clustering_runner=None
) -> gr.Blocks:
    """Build and return the operator status Gradio Blocks app.

    The Blocks contain a single static HTML skeleton.  All live updates
    are handled client-side by the polling script injected via head=.
    """
    with gr.Blocks(
        title="Image Scoring — Status",
        css=_DARK_CSS,
        head=_POLL_HEAD,
    ) as demo:
        gr.HTML(value=_skeleton_html())

    return demo

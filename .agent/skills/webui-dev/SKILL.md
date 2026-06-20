---
name: webui-dev
description: Development workflow, running commands, and debugging patterns for the Gradio WebUI.
---

# WebUI Development Workflow

## Quick Reference

| Command | Purpose |
|---------|---------|
| `python webui.py` | Start the WebUI (Gradio) |
| `run_webui.bat` | Windows wrapper for starting WebUI |
| `run_webui_docker.bat` | Start WebUI in Docker |
| `python -m pytest tests/` | Run test suite |

## Architecture

- **Entry Point**: `webui.py` - Sets up the Gradio interface and event handlers.
- **UI Modules**: `modules/ui/` - Contains component definitions and UI logic.
- **Backend Logic**: `modules/scoring.py`, `modules/db.py` - Core application logic.

## Key Patterns

### Gradio Components
The UI is built using `gradio` blocks.
- **Blocks**: `with gr.Blocks() as demo:`
- **Events**: `btn.click(fn=handler, inputs=[...], outputs=[...])`

### Database Access
The WebUI interacts with the database via `modules/db.py`.
- **Connection**: Managed internally by `db` module.
- **Queries**: Use functions in `db` module to fetch/update data.

## Debugging

- **Console Logs**: Check the terminal running `webui.py` for errors.
- **Gradio Debug**: Use `debug=True` in `launch()` for detailed traceback.
- **MCP Tools**: **`is-be-mcp`** (stdio — `search` / `dispatch`, including **`browser.*`** Playwright actions). Optional **`is-be-live`** SSE (`execute_code` when enabled). Gallery: **`is-ui-mcp`**. Legacy debug profiles: **`is-be-diag`**, **`is-be-jobs`**, etc.

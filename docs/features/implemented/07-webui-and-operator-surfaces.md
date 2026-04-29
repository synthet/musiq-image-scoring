# WebUI and operator surfaces

**Purpose:** Ship a single **FastAPI** process that serves the React **operator UI**, minimal **Gradio** status surfaces, REST **API**, optional **MCP**, and static assets.

**User-visible behavior:** Primary product navigation under `/ui/` (Vite build); lightweight operator/debug/status pages under `/app` (Gradio blocks); OpenAPI at `/docs` and `/openapi.json`.

**Primary code paths:** `webui.py` (app composition, static mounts, WebSocket), `modules/ui/*` (Gradio status), `frontend/` (React SPA build output served as static files).

**Main HTTP paths (non-exhaustive):**

- **SPA:** `/ui/`, static router for built assets
- **Gradio:** `/app` (and Gradio internal routes)
- **API:** all `/api/*` routes from `create_api_router()`; **LLM-oriented discovery:** `GET /api/schema`
- **Health / ops:** `GET /api/health`, `GET /api/status`, `GET /api/diagnostics`, `GET /api/debug/requests`, `GET /api/debug/loop-lag`
- **Optional MCP:** enabled with `ENABLE_MCP_SERVER` — see [08-mcp-and-agents.md](08-mcp-and-agents.md)

**Related docs:** [GRADIO_SERVING_DECISION](../../reports/GRADIO_SERVING_DECISION.md) · [ARCHITECTURE.md](../../ARCHITECTURE.md) · [DEVELOPMENT.md](../../DEVELOPMENT.md)

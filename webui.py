import os
import platform
import warnings
import logging
from logging.handlers import RotatingFileHandler
import json
import faulthandler
import signal
import sys
import urllib.parse
from contextlib import asynccontextmanager
import gradio as gr
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
import uvicorn
from modules.ui import app as app_module
from modules.events import event_manager
from modules.command_dispatcher import command_dispatcher

# Suppress TensorFlow logging (C++ level)
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '3'
# Suppress TensorFlow Python-level deprecation warnings (e.g. tf.losses.* → tf.compat.v1.losses.*)
os.environ.setdefault('TF_ENABLE_DEPRECATION_WARNINGS', '0')
warnings.filterwarnings("ignore", category=DeprecationWarning, module=r"tensorflow|keras")
warnings.filterwarnings("ignore", message=r".*tf\.losses\..*is deprecated.*")

# Suppress Gradio 6.0 deprecation warnings
warnings.filterwarnings("ignore", message="The 'css' parameter in the Blocks constructor")
warnings.filterwarnings("ignore", message="The 'head' parameter in the Blocks constructor")

_LOG_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"

_DEFAULT_LOG_MAX_BYTES = 10 * 1024 * 1024
_DEFAULT_LOG_BACKUP_COUNT = 5


def _webui_rotation_from_config(app_config: dict) -> tuple[int, int]:
    """Return (max_bytes, backup_count) for RotatingFileHandler from system.* keys."""
    system = (app_config or {}).get("system") or {}
    raw_max = system.get("log_max_bytes", _DEFAULT_LOG_MAX_BYTES)
    raw_n = system.get("log_backup_count", _DEFAULT_LOG_BACKUP_COUNT)
    try:
        max_bytes = int(raw_max)
    except (TypeError, ValueError):
        max_bytes = _DEFAULT_LOG_MAX_BYTES
    try:
        backup_count = int(raw_n)
    except (TypeError, ValueError):
        backup_count = _DEFAULT_LOG_BACKUP_COUNT
    max_bytes = max(1024, max_bytes)
    backup_count = max(0, min(backup_count, 50))
    return max_bytes, backup_count


def _make_webui_rotating_handler(
    app_log_path: str, log_level: int, max_bytes: int, backup_count: int
) -> RotatingFileHandler:
    fh = RotatingFileHandler(
        app_log_path,
        mode="a",
        maxBytes=max_bytes,
        backupCount=backup_count,
        encoding="utf-8",
    )
    fh.setLevel(log_level)
    fh.setFormatter(logging.Formatter(_LOG_FORMAT))
    return fh


def _ensure_webui_file_handler(
    app_log_path: str, log_level: int, max_bytes: int, backup_count: int
) -> None:
    """Attach project webui.log handler even if logging.basicConfig was already a no-op.

    Library modules (e.g. modules.pipeline) may call basicConfig at import time; then
    webui.main()'s basicConfig skips adding handlers and application logs never hit disk.
    """
    root = logging.getLogger()
    try:
        abs_target = os.path.normcase(os.path.abspath(app_log_path))
    except OSError:
        abs_target = None
    for h in root.handlers:
        if isinstance(h, logging.FileHandler):
            try:
                existing = os.path.normcase(os.path.abspath(h.baseFilename))
                if abs_target and existing == abs_target:
                    return
            except (AttributeError, OSError, ValueError, TypeError):
                continue
    root.addHandler(_make_webui_rotating_handler(app_log_path, log_level, max_bytes, backup_count))


# Custom logging filter to suppress Gradio queue polling messages
class SuppressGradioQueueFilter(logging.Filter):
    def filter(self, record):
        # Suppress logs for Gradio queue polling endpoints
        message = record.getMessage()
        if '/gradio_api/queue/data' in message or '/gradio_api/queue/join' in message:
            return False
        return True

def main():
    def _env_flag(name: str, default: bool = False) -> bool:
        value = os.environ.get(name)
        if value is None:
            return default
        return value.strip().lower() in {"1", "true", "yes", "on"}

    # Load config (config.json + environment.json) for debug mode and bind defaults
    app_config: dict = {}
    try:
        from modules import config
        app_config = config.load_config()
        debug_mode = app_config.get('debug', False)

        # Configure logging — project-root webui.log (stable regardless of process cwd)
        log_level = logging.DEBUG if debug_mode else logging.INFO
        app_log_path = str(config.BASE_DIR / "webui.log")
        max_bytes, backup_count = _webui_rotation_from_config(app_config)
        logging.basicConfig(
            level=log_level,
            format=_LOG_FORMAT,
            handlers=[
                logging.StreamHandler(),
                _make_webui_rotating_handler(app_log_path, log_level, max_bytes, backup_count),
            ],
        )
        _ensure_webui_file_handler(app_log_path, log_level, max_bytes, backup_count)
        logging.getLogger().setLevel(log_level)

        if debug_mode:
            print("[DEBUG] Debug mode enabled. Performance metrics will be logged to webui.log")
            logging.getLogger("image_scoring.performance").setLevel(logging.DEBUG)
    except Exception as e:
        print(f"Error configuring logging: {e}")
        debug_mode = False

    # Dump all Python thread stacks to stderr (fatal errors + optional signal).
    faulthandler.enable(all_threads=True)
    if getattr(signal, "SIGUSR1", None) is not None:

        def _thread_dump_on_sigusr1(_signum, _frame):
            print("\n=== Python thread dump (SIGUSR1) ===", file=sys.stderr, flush=True)
            faulthandler.dump_traceback(file=sys.stderr, all_threads=True)
            print("=== end thread dump ===\n", file=sys.stderr, flush=True)

        signal.signal(signal.SIGUSR1, _thread_dump_on_sigusr1)
        print("Thread dump: send SIGUSR1 to dump stacks (e.g. kill -USR1 <pid> in WSL/Linux).")

    # Cache platform check
    is_windows = platform.system() == "Windows"
    # WEBUI_* env wins over config webui_host / webui_port (see environment.example.json)
    _host_env = (os.environ.get("WEBUI_HOST") or "").strip()
    _port_env = (os.environ.get("WEBUI_PORT") or "").strip()
    server_host = _host_env or str(app_config.get("webui_host", "127.0.0.1")).strip() or "127.0.0.1"
    _port_str = _port_env or str(app_config.get("webui_port", 7860)).strip() or "7860"
    server_port = int(_port_str)
    display_host = "127.0.0.1" if server_host == "0.0.0.0" else server_host

    # MCP Server Integration (optional - for Cursor debugging)
    # Bind to localhost by default; set WEBUI_HOST=0.0.0.0 to expose remotely.
    mcp_enabled = _env_flag('ENABLE_MCP_SERVER', default=True)
    mcp_execute_enabled = _env_flag('ENABLE_MCP_EXECUTE_CODE', default=False)
    mcp_available = False
    try:
        from modules import mcp_server
        mcp_available = True
    except ImportError:
        pass

    print(f"MCP Server: enabled={mcp_enabled} available={mcp_available} execute_code={mcp_execute_enabled}")
    if mcp_enabled and not mcp_available:
        print("MCP Server: not available (missing dependency). Install with: pip install mcp")
    if server_host not in {"127.0.0.1", "localhost"} and mcp_execute_enabled:
        print("Warning: ENABLE_MCP_EXECUTE_CODE is enabled while WEBUI_HOST exposes the server beyond localhost.")
    
    mcp_mount_error: str | None = None

    @asynccontextmanager
    async def lifespan(app):
        import asyncio
        loop = asyncio.get_running_loop()
        event_manager.set_loop(loop)
        print("EventManager: Event loop attached.")

        # Reconcile stale running jobs from previous crash
        try:
            from modules import db
            logger = logging.getLogger(__name__)
            stale_jobs = db.list_stale_running_image_phase_rows(min_age_seconds=600, limit=1000)
            if stale_jobs.get("rows"):
                logger.info("Found %d stale running image phases; reconciling...", len(stale_jobs["rows"]))
                for row in stale_jobs["rows"]:
                    job_id = row.get("job_id")
                    if job_id:
                        try:
                            db.reconcile_stale_running_phases_for_jobs([job_id])
                        except Exception as e:
                            logger.error("Failed to reconcile job %s: %s", job_id, e)
        except Exception as e:
            logger.error("Startup reconciliation failed: %s", e)

        # Start event loop health monitor
        from modules.profiling import get_loop_monitor
        monitor = get_loop_monitor()
        if monitor:
            await monitor.start()

        yield

        if monitor:
            await monitor.stop()

    # Create Main FastAPI App with comprehensive OpenAPI documentation
    app = FastAPI(
        lifespan=lifespan,
        title="Image Scoring WebUI API",
        description="""
        REST API for the Image Scoring WebUI application.
        
        This API provides programmatic access to image quality assessment and tagging operations.
        
        ## Features
        
        - **Image Scoring**: Multi-model AI quality assessment (SPAQ, AVA, KonIQ, PaQ2PiQ, LIQE)
        - **Image Tagging**: Automatic keyword extraction using CLIP
        - **Caption Generation**: BLIP-based image captioning
        - **Job Management**: Start, stop, and monitor batch operations
        - **Status Monitoring**: Real-time progress tracking
        
        ## Authentication
        
        Currently, the API does not require authentication. Consider adding authentication
        for production deployments.
        
        ## Base URL
        
        All endpoints are prefixed with `/api`. The base URL is:
        - Development: `http://127.0.0.1:7860/api`
        - Production: `http://your-server:7860/api`
        
        ## OpenAPI Schema
        
        The complete OpenAPI schema is available at:
        - JSON: `/openapi.json`
        - YAML: `/openapi.yaml`
        - Interactive Docs: `/docs` (Swagger UI)
        - Alternative Docs: `/redoc` (ReDoc)
        
        ## LLM Agent Usage
        
        LLM agents can use this API by:
        1. Reading the OpenAPI schema from `/openapi.json`
        2. Using the schema to understand available endpoints and request/response formats
        3. Making HTTP requests to trigger operations and monitor status
        
        All endpoints return JSON responses following REST conventions.
        """,
        version="1.0.0",
        contact={
            "name": "Image Scoring WebUI",
            "url": "https://github.com/your-repo/image-scoring"
        },
        license_info={
            "name": "MIT",
        },
        openapi_tags=[
            {
                "name": "Image Scoring API",
                "description": "Endpoints for image quality assessment and scoring operations."
            },
            {
                "name": "Tagging API",
                "description": "Endpoints for image tagging and keyword extraction."
            },
            {
                "name": "General API",
                "description": "General endpoints for health checks, status, and job management."
            }
        ]
    )
    
    # Add CORS middleware to allow requests from the Electron/Vite frontend
    # Note: allow_origins=["*"] with allow_credentials=True is invalid in Starlette/FastAPI
    origins = [
        "http://127.0.0.1:7860",
        "http://localhost:7860",
        "http://127.0.0.1:5173",  # Vite dev server (React SPA)
        "http://localhost:5173",
        "http://127.0.0.1:4173",  # Vite preview
        "http://localhost:4173",
        "http://127.0.0.1:5174",  # Alternate Vite dev port
        "http://localhost:5174",
    ]
    
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Request profiling and event loop health monitoring
    from modules.profiling import setup_profiling
    setup_profiling(app)

    @app.get("/mcp-status")
    def mcp_status():
        return {
            "enabled": mcp_enabled,
            "available": mcp_available,
            "execute_code_enabled": mcp_execute_enabled,
            "mount_error": mcp_mount_error,
            "expected_sse_url": f"http://{display_host}:{server_port}/mcp/sse",
            "server_host": server_host,
            "server_port": server_port,
        }
    
    # Create UI and initialize engines (Gradio App)
    import modules.clustering as clustering
    clustering_runner = clustering.ClusteringRunner()
    (
        demo,
        runner,
        tagging_runner,
        selection_runner,
        orchestrator,
        pipeline_components,
        gallery_components,
        settings_components,
        main_tabs,
        indexing_runner,
        metadata_runner,
        maintenance_runner,
    ) = app_module.create_ui(clustering_runner=clustering_runner)

    # Setup MCP server if enabled
    mcp_sse_app = None
    if mcp_available and mcp_enabled:
        mcp_server.set_runners(
            runner, tagging_runner, clustering_runner, selection_runner, 
            orchestrator, bird_species_runner=app_module._bird_species_runner,
            indexing_runner=indexing_runner, metadata_runner=metadata_runner,
            maintenance_runner=maintenance_runner
        )
        mcp_server.set_gradio_context(
            demo=demo,
            pipeline_components=pipeline_components,
            gallery_components=gallery_components,
            settings_components=settings_components,
            main_tabs=main_tabs,
            runner=runner,
            tagging_runner=tagging_runner,
            orchestrator=orchestrator,
        )
        try:

            # Expose MCP over HTTP/SSE so Cursor can connect via:
            #   http://localhost:7860/mcp/sse
            # NOTE: we mount *after* Gradio is mounted; gr.mount_gradio_app()
            # may wrap/replace the FastAPI app instance.
            # Use mount_path="/" since FastAPI will mount this app at /mcp, making the full path /mcp/sse
            mcp_sse_app = mcp_server.create_mcp_sse_app(mount_path="/")
        except Exception as e:
            mcp_mount_error = str(e)
            print(f"MCP Server: Failed to mount SSE endpoint: {e}")
    
    # Define allowed paths from config
    system_config = config.get_config_section('system')
    config_allowed = system_config.get('allowed_paths', [])
    
    allowed_paths = []
    if config_allowed:
        allowed_paths.extend(config_allowed)
        # Always ensure current dir and thumbnails are allowed
        allowed_paths.append(os.path.abspath("."))
        allowed_paths.append(str(config.BASE_DIR / "thumbnails"))
    else:
        # Fallback to dynamic defaults if config is empty
        allowed_paths = config.get_default_allowed_paths()
        
    print(f"Starting WebUI on {platform.system()}...")

    # Initialize API key authentication if configured
    from modules.ui.security import _init_api_auth
    _init_api_auth()

    # Configure server endpoints using the FastAPI app directly
    app_module.setup_server_endpoints(
        app, runner, tagging_runner, clustering_runner, selection_runner, 
        orchestrator, indexing_runner=indexing_runner, metadata_runner=metadata_runner,
        maintenance_runner=maintenance_runner
    )
    command_dispatcher.set_runners(
        scoring_runner=runner,
        tagging_runner=tagging_runner,
        clustering_runner=clustering_runner,
    )
    
    # Mount MCP SSE endpoints (if enabled) onto the final app instance.
    # MUST be mounted BEFORE Gradio to avoid being shadowed by Gradio's catch-all route at /
    if mcp_sse_app is not None:
        app.mount("/mcp", mcp_sse_app)
        print("MCP Server: SSE endpoint mounted at /mcp/sse")
        try:
            has_mcp_mount = any(getattr(r, "path", None) == "/mcp" for r in app.routes)
            print(f"MCP Server: mount_registered={has_mcp_mount}")
        except Exception:
            pass
    
    # WebSocket Endpoint for Real-time Events
    @app.websocket("/ws/updates")
    async def websocket_endpoint(websocket: WebSocket):
        origin = websocket.headers.get("origin", "")
        allowed_hosts = {websocket.url.hostname, "localhost", "127.0.0.1"}
        if origin:
            origin_hostname = urllib.parse.urlparse(origin).hostname
            if origin_hostname not in allowed_hosts:
                await websocket.close(code=1008)
                return
        await event_manager.connect(websocket)
        try:
            while True:
                # Keep connection alive and listen for any incoming messages (though we mainly push)
                data = await websocket.receive_text()
                try:
                    message = json.loads(data)
                except json.JSONDecodeError:
                    await event_manager.send_to(
                        websocket,
                        {
                            "type": "command_response",
                            "request_id": None,
                            "success": False,
                            "data": {},
                            "error": "Malformed JSON payload",
                        },
                    )
                    continue
                await command_dispatcher.handle(websocket, message)
        except WebSocketDisconnect:
            event_manager.disconnect(websocket)
        except Exception as e:
            logging.error(f"WebSocket error: {e}")
            event_manager.disconnect(websocket)

    _webui_root = os.path.dirname(os.path.abspath(__file__))
    _favicon_png = os.path.join(_webui_root, "static", "favicon.png")
    _favicon_ico = os.path.join(_webui_root, "static", "favicon.ico")

    @app.get("/favicon.png")
    @app.get("/favicon.ico")
    async def serve_root_favicon():
        """Serve app favicon at site root (avoids Gradio default + broken /ui/*/relative icon URLs)."""
        if os.path.isfile(_favicon_png):
            return FileResponse(_favicon_png, media_type="image/png")
        if os.path.isfile(_favicon_ico):
            return FileResponse(_favicon_ico, media_type="image/x-icon")
        raise HTTPException(status_code=404, detail="favicon not found")

    # Mount Gradio App onto FastAPI at /app (legacy fallback)
    app = gr.mount_gradio_app(app, demo, path="/app", allowed_paths=allowed_paths, favicon_path="static/favicon.png")

    # Serve React SPA build (static/app/) — must be mounted AFTER /api routes
    # SPA files are built via: cd frontend && npm run build  (outputs to static/app/)
    _spa_dir = os.path.join(os.path.dirname(__file__), "static", "app")
    if os.path.isdir(_spa_dir):
        _spa_root = os.path.abspath(_spa_dir)
        # Avoid stale index.html: without this, browsers may keep an old shell that references
        # a removed hashed JS bundle after `npm run build`. Hashed assets stay long-cacheable.
        _spa_html_headers = {"Cache-Control": "no-cache"}
        _spa_asset_headers = {"Cache-Control": "public, max-age=31536000, immutable"}

        @app.get("/ui/{full_path:path}")
        async def serve_spa(full_path: str):
            """Serve React SPA for all /ui/* paths (client-side routing)."""
            # Resolve under spa root only (block path traversal)
            candidate = os.path.abspath(os.path.join(_spa_root, full_path))
            if candidate != _spa_root and not candidate.startswith(_spa_root + os.sep):
                return FileResponse(os.path.join(_spa_root, "index.html"), headers=_spa_html_headers)
            if os.path.isfile(candidate):
                rel = os.path.relpath(candidate, _spa_root).replace("\\", "/")
                if rel.startswith("assets/"):
                    return FileResponse(candidate, headers=_spa_asset_headers)
                return FileResponse(candidate, headers=_spa_html_headers)
            return FileResponse(os.path.join(_spa_root, "index.html"), headers=_spa_html_headers)

        @app.get("/")
        async def root_redirect():
            from fastapi.responses import RedirectResponse
            return RedirectResponse(url="/ui/", status_code=302)

        print(f"React SPA: served at http://{display_host}:{server_port}/ui/")
    else:
        @app.get("/")
        async def root_redirect():
            from fastapi.responses import RedirectResponse
            return RedirectResponse(url="/app", status_code=302)

        print(f"React SPA: build not found at {_spa_dir}. Run: cd frontend && npm run build")
    
    # Apply logging filter to suppress repetitive Gradio queue polling messages


    # Apply logging filter to suppress repetitive Gradio queue polling messages
    logging.getLogger("uvicorn.access").addFilter(SuppressGradioQueueFilter())
    
    # Create lock file
    import json
    import atexit
    
    lock_file = "webui.lock"
    try:
        with open(lock_file, "w") as f:
            json.dump({"pid": os.getpid(), "port": server_port}, f)
    except Exception as e:
        print(f"Warning: Could not create lock file: {e}")
        
    def remove_lock():
        try:
            if os.path.exists(lock_file):
                os.remove(lock_file)
        except:
            pass
            
    atexit.register(remove_lock)

    # Launch using Uvicorn
    # Note: inbrowser=False is default for uvicorn, handled by user opening browser
    print(f"Launching Uvicorn server at http://{display_host}:{server_port}")

    open_ui = (os.environ.get("WEBUI_OPEN_UI") or "").strip().lower()
    if open_ui in ("browser", "electron"):
        from modules.webui_open import schedule_webui_open

        schedule_webui_open("127.0.0.1", server_port, open_ui)
        print(f"WEBUI_OPEN_UI={open_ui}: will open when the server is ready.")

    try:
        uvicorn.run(app, host=server_host, port=server_port, log_level="info")
    finally:
        remove_lock()

if __name__ == "__main__":
    main()


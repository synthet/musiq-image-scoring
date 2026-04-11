"""Main application orchestrator for the WebUI.

Initializes DB, runners, and the PipelineOrchestrator, then builds the
operator status Gradio app mounted at /app.  The primary product UI is
the React SPA at /ui (built from frontend/).

create_ui() returns the same 9-tuple as before so webui.py and MCP
wiring remain unchanged; pipeline_components, gallery_components, and
settings_components are empty dicts and main_tabs is None.
"""
import logging
import os
import platform
from pathlib import Path

logger = logging.getLogger(__name__)

from modules import scoring, db, tagging, config, thumbnails, utils, pipeline_orchestrator
from modules.selection_runner import SelectionRunner
from modules.indexing_runner import IndexingRunner
from modules.metadata_runner import MetadataRunner
from modules.maintenance_runner import MaintenanceRunner
from modules import phase_executors
from modules.ui import status_gradio

# Cache platform check
IS_WINDOWS = platform.system() == "Windows"

# Module-level reference to BirdSpeciesRunner so setup_server_endpoints can access it
_bird_species_runner = None


def _init_webui_engines(clustering_runner=None):
    """Initialize DB, config, runners, and orchestrator. Returns (app_config, runner, tagging_runner, selection_runner, orchestrator)."""
    global _bird_species_runner
    db.init_db()
    app_config = config.load_config()

    runner = scoring.ScoringRunner()
    tagging_runner = tagging.TaggingRunner()
    selection_runner = SelectionRunner()
    indexing_runner = IndexingRunner()
    metadata_runner = MetadataRunner()
    maintenance_runner = MaintenanceRunner()

    from modules.bird_species import BirdSpeciesRunner
    _bird_species_runner = BirdSpeciesRunner()

    orchestrator = pipeline_orchestrator.PipelineOrchestrator(
        scoring_runner=runner,
        tagging_runner=tagging_runner,
        selection_runner=selection_runner,
        indexing_runner=indexing_runner,
        metadata_runner=metadata_runner,
        maintenance_runner=maintenance_runner,
        enable_background_tick=True,
    )
    recovery_info = orchestrator.recover_interrupted_jobs()
    try:
        n_orphan = db.reconcile_stale_running_phases_for_terminal_jobs(limit=5000)
        recovery_info["reconciled_terminal_job_phase_rows"] = n_orphan
    except Exception:
        logger.exception("reconcile_stale_running_phases_for_terminal_jobs on startup failed")
    app_config["job_recovery"] = recovery_info

    phase_executors.register_all(
        scoring_runner=runner,
        tagging_runner=tagging_runner,
        selection_runner=selection_runner,
        indexing_runner=indexing_runner,
        metadata_runner=metadata_runner,
    )

    return app_config, runner, tagging_runner, selection_runner, orchestrator, indexing_runner, metadata_runner, maintenance_runner


def create_ui(clustering_runner=None):
    """Build the operator status WebUI. Returns a 9-tuple compatible with webui.py."""
    app_config, runner, tagging_runner, selection_runner, orchestrator, indexing_runner, metadata_runner, maintenance_runner = _init_webui_engines(
        clustering_runner=clustering_runner
    )

    demo = status_gradio.build_status_demo(
        runner,
        tagging_runner,
        selection_runner,
        orchestrator,
        clustering_runner=clustering_runner,
    )

    return (
        demo,
        runner,
        tagging_runner,
        selection_runner,
        orchestrator,
        {},   # pipeline_components
        {},   # gallery_components
        {},   # settings_components
        None, # main_tabs
        indexing_runner,
        metadata_runner,
        maintenance_runner,
    )


# Security helpers — re-exported from lightweight module so existing imports
# (e.g. ``from modules.ui.app import _check_rate_limit``) keep working.
from modules.ui.security import (          # noqa: F401
    _check_rate_limit,
    _validate_file_path,
    _SQL_FORBIDDEN_PATTERNS,
)


def setup_server_endpoints(fastapi_app, scoring_runner=None, tagging_runner=None, clustering_runner=None, selection_runner=None, orchestrator=None, indexing_runner=None, metadata_runner=None, maintenance_runner=None):
    """Configures FastAPI endpoints for the Gradio app."""

    from modules import api, api_db
    api.set_runners(
        scoring_runner, tagging_runner, clustering_runner, selection_runner, 
        orchestrator, bird_species_runner=_bird_species_runner,
        indexing_runner=indexing_runner, metadata_runner=metadata_runner,
        maintenance_runner=maintenance_runner,
    )
    api_router = api.create_api_router()
    fastapi_app.include_router(api_router)
    fastapi_app.include_router(api.create_public_api_router())
    fastapi_app.include_router(api_db.router)

    @fastapi_app.on_event("shutdown")
    async def _shutdown_dispatcher():
        import asyncio

        await asyncio.to_thread(api.graceful_shutdown_processing, "fastapi_shutdown")

    @fastapi_app.get("/api/status/data", tags=["Status"])
    async def status_data_endpoint():
        """Live status data consumed by the /app operator page (threads, profiling, runners, log)."""
        import asyncio
        from modules.ui.status_gradio import render_status_data
        return await asyncio.to_thread(
            render_status_data,
            scoring_runner, tagging_runner, selection_runner, orchestrator,
            clustering_runner=clustering_runner,
        )

    @fastapi_app.get("/api/status/logs", tags=["Status"])
    async def status_logs_endpoint():
        """Log sections only (webui.log + debug.log HTML) for the React SPA /ui/logs page."""
        import asyncio
        from datetime import datetime
        from modules.ui.status_gradio import _render_log

        log_html = await asyncio.to_thread(_render_log)
        return {"ts": datetime.now().strftime("%H:%M:%S"), "log": log_html}

    @fastapi_app.get("/manifest.json")
    async def manifest_endpoint():
        """Serve a minimal web app manifest to prevent 404 errors."""
        from fastapi.responses import JSONResponse
        return JSONResponse({
            "name": "Image Scoring WebUI",
            "short_name": "Image Scoring",
            "start_url": "/ui/",
            "display": "standalone",
            "theme_color": "#000000",
            "background_color": "#ffffff"
        })

    @fastapi_app.get("/api/raw-preview")
    async def raw_preview_endpoint(path: str):
        import urllib.parse
        from fastapi.responses import Response
        from fastapi import HTTPException
        import io

        try:
            file_path = urllib.parse.unquote(path)
            file_path = utils.resolve_file_path(file_path) or utils.convert_path_to_local(file_path)
            file_path = _validate_file_path(file_path)

            if not os.path.exists(file_path):
                raise HTTPException(status_code=404, detail="File not found")

            ext = Path(file_path).suffix.lower()
            if ext not in ['.nef', '.cr2', '.dng', '.arw', '.orf', '.nrw', '.cr3', '.rw2']:
                raise HTTPException(status_code=400, detail="Unsupported format")

            img = thumbnails.extract_embedded_jpeg(file_path, min_size=1000)
            if img is None:
                raise HTTPException(status_code=500, detail="Extraction failed")

            jpeg_bytes = io.BytesIO()
            img.save(jpeg_bytes, format='JPEG', quality=90)
            jpeg_bytes.seek(0)

            return Response(
                content=jpeg_bytes.read(),
                media_type="image/jpeg",
                headers={"Cache-Control": "public, max-age=3600"}
            )
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @fastapi_app.post("/api/query")
    async def query_endpoint(payload: dict):
        """Executes a read-only SQL query against the database."""
        from fastapi import HTTPException

        query = payload.get("query")
        parameters = payload.get("parameters", {})

        if not query or not query.strip().upper().startswith("SELECT"):
            raise HTTPException(status_code=400, detail="Only SELECT queries are allowed")
        if _SQL_FORBIDDEN_PATTERNS.search(query):
            raise HTTPException(status_code=400, detail="Query contains forbidden keywords")
        if ";" in query:
            raise HTTPException(status_code=400, detail="Multi-statement queries not allowed")

        try:
            conn = db.get_db()
            conn.row_factory = lambda c, r: dict(zip([col[0] for col in c.description], r))
            c = conn.cursor()
            c.execute(query, parameters)
            rows = c.fetchall()
            conn.close()
            return rows
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @fastapi_app.get("/source-image")
    async def source_image_endpoint(path: str):
        """Serves full-resolution source images. For RAW files generates JPEG preview on-the-fly."""
        import urllib.parse
        from fastapi.responses import Response, FileResponse
        from fastapi import HTTPException
        import io

        try:
            file_path = urllib.parse.unquote(path)
            resolved = utils.resolve_file_path(file_path)
            file_path = resolved if resolved else utils.convert_path_to_local(file_path)
            file_path = _validate_file_path(file_path)

            if not os.path.exists(file_path):
                raise HTTPException(status_code=404, detail="File not found")

            ext = Path(file_path).suffix.lower()
            is_raw = ext in ['.nef', '.cr2', '.dng', '.arw', '.orf', '.nrw', '.cr3', '.rw2']

            if is_raw:
                img = thumbnails.extract_embedded_jpeg(file_path, min_size=1000)
                if img and img.width > 1000:
                    jpeg_bytes = io.BytesIO()
                    img.save(jpeg_bytes, format='JPEG', quality=95)
                    jpeg_bytes.seek(0)
                    return Response(content=jpeg_bytes.read(), media_type="image/jpeg",
                                    headers={"Cache-Control": "public, max-age=3600"})
                preview_path = thumbnails.generate_preview(file_path)
                if preview_path and os.path.exists(preview_path):
                    return FileResponse(preview_path, media_type="image/jpeg",
                                        headers={"Cache-Control": "public, max-age=3600"})
                if img:
                    jpeg_bytes = io.BytesIO()
                    img.save(jpeg_bytes, format='JPEG', quality=95)
                    jpeg_bytes.seek(0)
                    return Response(content=jpeg_bytes.read(), media_type="image/jpeg",
                                    headers={"Cache-Control": "public, max-age=3600"})
                raise HTTPException(status_code=500, detail="Failed to generate RAW preview")
            else:
                media_types = {
                    '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg', '.png': 'image/png',
                    '.gif': 'image/gif', '.webp': 'image/webp', '.bmp': 'image/bmp',
                    '.tiff': 'image/tiff', '.tif': 'image/tiff',
                }
                return FileResponse(file_path, media_type=media_types.get(ext, 'image/jpeg'),
                                    headers={"Cache-Control": "public, max-age=3600"})
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

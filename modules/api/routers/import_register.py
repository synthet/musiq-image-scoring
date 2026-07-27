"""API routes: import_register (extracted from modules.api)."""

from __future__ import annotations

import json
import logging
import os
import platform

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from modules import db
from modules.api_models import (
    ImportRegisterRequest,
)

logger = logging.getLogger(__name__)


import sys


def _api_module():
    return sys.modules["modules.api"]



def create_import_register_router() -> APIRouter:
    router = APIRouter()
    # ========== Import Register Endpoints ==========

    _IMPORT_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".nef", ".arw", ".cr2", ".dng", ".heic", ".webp", ".tiff", ".tif", ".raw", ".orf", ".rw2"}

    def _resolve_import_path(raw_path: str) -> str:
        """Convert Windows path to WSL if needed, validate directory exists."""
        from modules import utils
        folder_path = raw_path
        try:
            if platform.system() == "Linux" and (":" in folder_path or "\\" in folder_path) and hasattr(utils, "convert_path_to_wsl"):
                folder_path = utils.convert_path_to_wsl(folder_path)
        except Exception:
            pass
        if not os.path.isdir(folder_path):
            raise HTTPException(status_code=400, detail=f"Path is not a directory or not found: {raw_path}")
        return folder_path

    def _import_folder_iter(folder_path: str):
        """Generator that yields progress/done/error dicts during folder import.

        Yields:
            {"type": "init", "total_files": int, "folder_path": str}
            {"type": "progress", "processed": int, "total": int, "added": int, "skipped": int, "current_file": str}
            {"type": "done", "success": bool, "added": int, "skipped": int, "total": int, "errors": list}
            {"type": "error", "message": str}
        """
        from modules.exif_extractor import extract_exif
        from modules.indexing_runner import INDEXING_VERSION
        from modules.phases import PhaseCode, PhaseStatus
        from modules.version import APP_VERSION

        def _ensure_import_indexing_phase_done(image_id: int) -> None:
            """Backfill indexing (Discovery) done when import skips an already-registered image."""
            st = db.get_image_phase_status(image_id, PhaseCode.INDEXING)
            if st and st.get("status") == PhaseStatus.RUNNING:
                return
            if st and st.get("status") == PhaseStatus.DONE:
                return
            db.set_image_phase_status(
                image_id,
                PhaseCode.INDEXING,
                PhaseStatus.DONE,
                app_version=APP_VERSION,
                executor_version=INDEXING_VERSION,
            )

        folder_id = db.get_or_create_folder(folder_path)
        if not folder_id:
            yield {"type": "error", "message": "Failed to get or create folder"}
            return

        entries = os.listdir(folder_path)
        file_entries = [e for e in entries if os.path.isfile(os.path.join(folder_path, e))]
        total_files = len(file_entries)

        yield {"type": "init", "total_files": total_files, "folder_path": folder_path}

        added = 0
        skipped = 0
        processed = 0
        errors = []

        for name in file_entries:
            fp = os.path.join(folder_path, name)
            ext = os.path.splitext(name)[1].lower()

            if ext not in _IMPORT_IMAGE_EXTENSIONS:
                processed += 1
                if processed % 5 == 0 or processed == total_files:
                    yield {
                        "type": "progress",
                        "processed": processed,
                        "total": total_files,
                        "added": added,
                        "skipped": skipped,
                        "current_file": os.path.basename(name),
                    }
                continue

            file_name = os.path.basename(name)
            file_type = ext.lstrip(".") or "unknown"

            try:
                existing_by_path = db.find_image_id_by_path(fp)
                if existing_by_path:
                    _ensure_import_indexing_phase_done(int(existing_by_path))
                    skipped += 1
                else:
                    image_uuid = None
                    try:
                        exif_data = extract_exif(fp)
                        if exif_data:
                            uid = exif_data.get("image_unique_id")
                            if uid and isinstance(uid, str) and uid.strip():
                                image_uuid = uid.strip()
                                existing_by_uuid = db.find_image_id_by_uuid(image_uuid)
                                if existing_by_uuid:
                                    _ensure_import_indexing_phase_done(int(existing_by_uuid))
                                    skipped += 1
                                    image_uuid = "ALREADY_IN_DB"
                    except Exception:
                        pass

                    if image_uuid != "ALREADY_IN_DB":
                        if db.is_image_in_deleted_blocklist(fp, file_name, image_uuid):
                            skipped += 1
                            image_uuid = "ALREADY_IN_DB"
                    if image_uuid != "ALREADY_IN_DB":
                        image_id, was_new = db.register_image_for_import(fp, file_name, file_type, folder_id, image_uuid)
                        if image_id:
                            if was_new:
                                added += 1
                                db.set_image_phase_status(
                                    image_id,
                                    PhaseCode.INDEXING,
                                    PhaseStatus.DONE,
                                    app_version=APP_VERSION,
                                    executor_version=INDEXING_VERSION,
                                )
                            else:
                                _ensure_import_indexing_phase_done(int(image_id))
                                skipped += 1
                        else:
                            errors.append(f"{file_name}: insert failed")
            except Exception as e:
                errors.append(f"{file_name}: {e!s}")

            processed += 1

            if processed % 5 == 0 or processed == total_files:
                yield {
                    "type": "progress",
                    "processed": processed,
                    "total": total_files,
                    "added": added,
                    "skipped": skipped,
                    "current_file": file_name,
                }

        yield {
            "type": "done",
            "success": True,
            "added": added,
            "skipped": skipped,
            "total": total_files,
            "errors": errors[:50],
        }

    @router.post(
        "/import/register",
        summary="Register images from folder",
        description="""
        Scans a folder for image files and registers them in the database.
        Returns a single JSON response when complete.
        Broadcasts real-time progress via WebSocket (event types:
        import_started, import_progress, import_completed).
        For streaming NDJSON progress, use /import/register/stream instead.
        """
    )
    async def import_register(request: ImportRegisterRequest):
        """Non-streaming image registration with WebSocket progress broadcasts."""
        from modules.events import event_manager
        from modules.ui.security import _check_rate_limit

        _check_rate_limit("import_register")
        folder_path = _resolve_import_path(request.folder_path)

        result = None
        for msg in _import_folder_iter(folder_path):
            msg_type = msg["type"]
            if msg_type == "init":
                event_manager.broadcast_threadsafe("import_started", {
                    "folder_path": msg["folder_path"],
                    "total_files": msg["total_files"],
                })
            elif msg_type == "progress":
                event_manager.broadcast_threadsafe("import_progress", {
                    "processed": msg["processed"],
                    "total": msg["total"],
                    "added": msg["added"],
                    "skipped": msg["skipped"],
                    "current_file": msg["current_file"],
                })
            elif msg_type == "done":
                result = msg
            elif msg_type == "error":
                event_manager.broadcast_threadsafe("import_completed", {
                    "added": 0, "skipped": 0, "total": 0, "errors": [msg["message"]],
                })
                raise HTTPException(status_code=500, detail=msg["message"])

        # Broadcast completion
        event_manager.broadcast_threadsafe("import_completed", {
            "added": result["added"],
            "skipped": result["skipped"],
            "total": result["total"],
            "errors": result["errors"],
        })

        errors = result["errors"]
        return {
            "success": len(errors) == 0 or result["added"] > 0,
            "message": f"Import complete: {result['added']} added, {result['skipped']} skipped"
                       + (f", {len(errors)} errors" if errors else ""),
            "data": {
                "added": result["added"],
                "skipped": result["skipped"],
                "errors": errors,
            },
        }

    @router.post(
        "/import/register/stream",
        summary="Register images from folder with streaming progress",
        description="""
        Returns a stream of JSON objects (NDJSON) providing real-time progress
        updates during the folder scan and registration process.
        For a single JSON response, use /import/register instead.
        """
    )
    async def import_register_stream(request: ImportRegisterRequest):
        """Streaming version of image registration (NDJSON)."""
        from modules.ui.security import _check_rate_limit

        _check_rate_limit("import_register")
        folder_path = _resolve_import_path(request.folder_path)

        async def progress_generator():
            try:
                for msg in _import_folder_iter(folder_path):
                    yield json.dumps(msg) + "\n"
            except Exception as e:
                yield json.dumps({"type": "error", "message": f"Unexpected error during scan: {e!s}"}) + "\n"

        return StreamingResponse(progress_generator(), media_type="application/x-ndjson")


    return router

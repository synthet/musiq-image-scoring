"""API routes: electron images and export (extracted from electron.py)."""

from __future__ import annotations

import os

from fastapi import APIRouter, Body, HTTPException, Query
from fastapi.responses import FileResponse

from modules import db
from modules.api.routers.electron_helpers import (
    api_module,
    logger,
)
from modules.api_models import ApiResponse, ExportRequest, ImageUpdateRequest


def create_electron_images_router() -> APIRouter:
    router = APIRouter()

    @router.patch(
        "/images/{image_id}",
        summary="Update image metadata",
        description="""
        Updates writable metadata fields for an image: rating, label, title, description,
        and keywords. All fields are optional — only provided fields are updated.

        When `write_sidecar=true` (default), metadata is also written to the XMP sidecar
        file and embedded tags via the tagging runner, keeping file metadata in sync with
        the database.

        **IPC contract:** Column names match the `images` table schema; do not rename
        without also updating `electron/db.ts`.
        """
    )
    async def update_image(image_id: int, request: ImageUpdateRequest = Body(...)):
        from modules.ui.security import _check_rate_limit
        _check_rate_limit("image_update")

        conn = db.get_db()
        try:
            c = conn.cursor()
            c.execute(
                "SELECT file_path, keywords, title, description, rating, label FROM images WHERE id = ?",
                (image_id,)
            )
            row = c.fetchone()
            if not row:
                raise HTTPException(status_code=404, detail=f"Image not found: id={image_id}")
            file_path = row[0]
            current_keywords = db.get_resolved_image_keywords(
                image_id, legacy_fallback=row[1] or ""
            )
            current_title = row[2] or ""
            current_desc = row[3] or ""
            current_rating = row[4] or 0
            current_label = row[5] or ""
        finally:
            conn.close()

        new_keywords = request.keywords if request.keywords is not None else current_keywords
        new_title = request.title if request.title is not None else current_title
        new_desc = request.description if request.description is not None else current_desc
        new_rating = request.rating if request.rating is not None else current_rating
        new_label = request.label if request.label is not None else current_label

        # Pick-status mirror: when caller sets pick_status without an explicit
        # rating/label, project the pick onto Adobe-compatible rating + label so
        # Lightroom and existing gallery filters see it.
        if request.pick_status is not None:
            if request.pick_status == 1:
                if request.rating is None:
                    new_rating = 4
                if request.label is None:
                    new_label = "Green"
            elif request.pick_status == -1:
                if request.rating is None:
                    new_rating = 1
                if request.label is None:
                    new_label = "Red"
            else:  # 0
                if request.rating is None:
                    new_rating = 0
                if request.label is None:
                    new_label = ""

        try:
            success = db.update_image_metadata(file_path, new_keywords, new_title, new_desc, new_rating, new_label)
            if not success:
                raise HTTPException(status_code=500, detail="Database update failed")

            if request.pick_status is not None:
                db.update_image_pick_status(image_id, request.pick_status)

            sidecar_ok = True
            if request.write_sidecar and api_module()._tagging_runner is not None:
                kw_list = [k.strip() for k in new_keywords.split(',') if k.strip()]
                sidecar_ok = api_module()._tagging_runner.write_metadata(file_path, kw_list, new_title, new_desc, new_rating, new_label)

            return ApiResponse(
                success=True,
                message=f"Updated image {image_id}",
                data={
                    "image_id": image_id,
                    "sidecar_written": sidecar_ok,
                    "pick_status": request.pick_status,
                    "rating": new_rating,
                    "label": new_label,
                },
            )
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @router.delete(
        "/images/{image_id}",
        summary="Delete image record from database",
        description="""
        Removes an image record from the database and cleans up related rows
        (culling picks, resolved paths, stack membership). The image file on disk is
        NOT deleted by default.

        Pass `delete_file=true` to also delete the source image file and its thumbnail
        from disk. Use with caution — this is irreversible.
        """
    )
    async def delete_image(image_id: int, delete_file: bool = Query(False, description="Also delete image file from disk.")):
        from modules.ui.security import _check_rate_limit
        _check_rate_limit("image_delete")

        conn = db.get_db()
        try:
            c = conn.cursor()
            c.execute("SELECT file_path, thumbnail_path FROM images WHERE id = ?", (image_id,))
            row = c.fetchone()
            if not row:
                raise HTTPException(status_code=404, detail=f"Image not found: id={image_id}")
            file_path = row[0]
            thumbnail_path = row[1]
        finally:
            conn.close()

        try:
            success, msg = db.delete_image(file_path, delete_related=True)
            if not success:
                raise HTTPException(status_code=500, detail=msg)

            deleted_files = []
            if delete_file:
                for path in [file_path, thumbnail_path]:
                    if path and os.path.exists(path):
                        try:
                            os.remove(path)
                            deleted_files.append(path)
                        except OSError as exc:
                            logger.warning("Could not delete file %s: %s", path, exc)

            return ApiResponse(
                success=True,
                message=msg,
                data={"image_id": image_id, "deleted_files": deleted_files}
            )
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @router.post(
        "/gallery/export",
        summary="Export gallery images to file",
        description="""
        Exports the image database (or a filtered subset) to JSON, CSV, or XLSX.
        The response is a file download. Filters mirror those available in the Gallery tab.

        **Formats:** `json` | `csv` | `xlsx`

        The file is written to `<app_root>/output/export_<timestamp>.<ext>` and served
        as an attachment.
        """
    )
    async def export_gallery(request: ExportRequest = Body(...)):
        import datetime

        from modules.ui.security import _check_rate_limit
        _check_rate_limit("gallery_export")

        fmt = (request.format or "json").lower()
        if fmt not in ("json", "csv", "xlsx"):
            raise HTTPException(status_code=400, detail=f"Unsupported format: {fmt!r}. Use json, csv, or xlsx.")

        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        output_dir = os.path.join(os.getcwd(), "output")
        os.makedirs(output_dir, exist_ok=True)
        output_path = os.path.join(output_dir, f"export_{timestamp}.{fmt}")

        date_range = None
        if request.date_from or request.date_to:
            date_range = (request.date_from, request.date_to)

        try:
            if fmt == "json":
                success, msg = db.export_db_to_json(output_path)
            elif fmt == "csv":
                success, msg = db.export_db_to_csv(
                    output_path,
                    columns=request.columns,
                    rating_filter=request.rating,
                    label_filter=request.label,
                    keyword_filter=request.keyword,
                    folder_path=request.folder_path,
                    min_score_general=request.min_score_general,
                    min_score_aesthetic=request.min_score_aesthetic,
                    min_score_technical=request.min_score_technical,
                    date_range=date_range,
                )
            else:  # xlsx
                success, msg = db.export_db_to_excel(
                    output_path,
                    columns=request.columns,
                    rating_filter=request.rating,
                    label_filter=request.label,
                    keyword_filter=request.keyword,
                    folder_path=request.folder_path,
                    min_score_general=request.min_score_general,
                    min_score_aesthetic=request.min_score_aesthetic,
                    min_score_technical=request.min_score_technical,
                    date_range=date_range,
                )

            if not success:
                raise HTTPException(status_code=500, detail=msg)

            media_types = {"json": "application/json", "csv": "text/csv", "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"}
            return FileResponse(
                output_path,
                media_type=media_types[fmt],
                filename=os.path.basename(output_path),
            )
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))
    return router

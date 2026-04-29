"""FastAPI router for serving source images from local disk paths."""

from __future__ import annotations

import io
import os
import urllib.parse
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse, Response

from modules import thumbnails, utils
from modules.ui.security import _validate_file_path

RAW_EXTENSIONS = {".nef", ".cr2", ".dng", ".arw", ".orf", ".nrw", ".cr3", ".rw2"}
IMAGE_MEDIA_TYPES = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".gif": "image/gif",
    ".webp": "image/webp",
    ".bmp": "image/bmp",
    ".tiff": "image/tiff",
    ".tif": "image/tiff",
}

SOURCE_IMAGE_RESPONSES = {
    200: {
        "description": "Image bytes for RAW previews (JPEG) or direct non-RAW files.",
        "content": {
            "image/jpeg": {},
            "image/png": {},
            "image/gif": {},
            "image/webp": {},
            "image/bmp": {},
            "image/tiff": {},
        },
    },
    400: {"description": "Invalid path or request parameters."},
    403: {"description": "Requested path is outside configured allowed roots."},
    404: {"description": "File not found."},
    422: {"description": "Validation failure (for example, missing `path` query parameter)."},
    500: {"description": "RAW preview extraction/generation failure."},
}

router = APIRouter()


@router.get(
    "/source-image",
    tags=["General API"],
    summary="Get full-resolution source image or RAW preview",
    response_class=Response,
    responses=SOURCE_IMAGE_RESPONSES,
)
async def source_image_endpoint(
    path: Annotated[
        str,
        Query(
            ...,
            description=(
                "URL-encoded absolute file path. RAW formats (.nef/.cr2/.dng/.arw/.orf/.nrw/.cr3/.rw2) "
                "return JPEG previews; non-RAW files are streamed in their native media type when supported."
            ),
            min_length=1,
        ),
    ],
):
    """Serve source image content for fullscreen and zoom workflows."""
    file_path = urllib.parse.unquote(path)
    resolved = utils.resolve_file_path(file_path)
    file_path = resolved if resolved else utils.convert_path_to_local(file_path)
    file_path = _validate_file_path(file_path)

    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="File not found")

    ext = Path(file_path).suffix.lower()
    is_raw = ext in RAW_EXTENSIONS
    cache_headers = {"Cache-Control": "public, max-age=3600"}

    if is_raw:
        img = thumbnails.extract_embedded_jpeg(file_path, min_size=1000)
        if img:
            from PIL import ImageOps
            img = ImageOps.exif_transpose(img)
            
            if img.width > 1000:
                jpeg_bytes = io.BytesIO()
                img.save(jpeg_bytes, format="JPEG", quality=95)
                jpeg_bytes.seek(0)
                return Response(content=jpeg_bytes.read(), media_type="image/jpeg", headers=cache_headers)

        preview_path = thumbnails.generate_preview(file_path)
        if preview_path and os.path.exists(preview_path):
            return FileResponse(preview_path, media_type="image/jpeg", headers=cache_headers)

        if img:
            jpeg_bytes = io.BytesIO()
            img.save(jpeg_bytes, format="JPEG", quality=95)
            jpeg_bytes.seek(0)
            return Response(content=jpeg_bytes.read(), media_type="image/jpeg", headers=cache_headers)

        raise HTTPException(status_code=500, detail="Failed to generate RAW preview")

    media_type = IMAGE_MEDIA_TYPES.get(ext, "image/jpeg")
    return FileResponse(file_path, media_type=media_type, headers=cache_headers)

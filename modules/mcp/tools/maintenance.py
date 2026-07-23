"""MCP tool implementations — maintenance (extracted from modules.mcp_server)."""

from __future__ import annotations

import json
import logging
import os
import re
import subprocess
import time
from typing import Any, Optional

from modules import config, db
from modules.mcp import tool_support as ts

logger = logging.getLogger(__name__)

def export_debug_bundle(output_path: Optional[str] = None) -> dict:
    """Write a redacted support zip (config, environment, doctor JSON, log tails). Same content as ``scripts/export_debug_bundle.py``."""
    from pathlib import Path

    from modules.debug_bundle_export import write_redacted_debug_bundle

    op = Path(os.path.expanduser(output_path)).resolve() if output_path and str(output_path).strip() else None
    if op is not None:
        if op.suffix.lower() != ".zip":
            return {"error": "output_path must end with .zip", "success": False}
        op.parent.mkdir(parents=True, exist_ok=True)

    return write_redacted_debug_bundle(output_zip=op)


def rebase_file_paths(old_root: str, new_root: str, dry_run: bool = True) -> dict:
    """Batch update image file paths by replacing a root prefix.
    Example: rebase D:\\Photos to Z:\\Archive."""
    old_root = os.path.normpath(old_root)
    new_root = os.path.normpath(new_root)

    with db.connection() as conn:
        c = conn.cursor()
        try:
            # First find how many would be affected
            pattern = old_root + "%"
            c.execute("SELECT COUNT(*) FROM images WHERE file_path LIKE ?", (pattern,))
            count = c.fetchone()[0]

            if dry_run:
                return {
                    "dry_run": True,
                    "affected_count": count,
                    "message": f"Would update {count} paths from {old_root} to {new_root}"
                }

            if count == 0:
                return {"success": True, "count": 0, "message": "No matching paths found"}

            # Update paths - using a simple replace logic
            # This is complex in SQL depending on the DB engine, so we'll do it in a transaction
            c.execute("SELECT id, file_path, folder_id FROM images WHERE file_path LIKE ?", (pattern,))
            rows = c.fetchall()

            folder_cache = {}
            affected_folders = set()

            for image_id, old_path, old_fid in rows:
                new_path = old_path.replace(old_root, new_root, 1)
                db.update_image_field(image_id, "file_path", new_path)
                
                # Update folder_id to match the new path
                new_dir = os.path.normpath(os.path.dirname(new_path))
                if new_dir not in folder_cache:
                    folder_cache[new_dir] = db.get_or_create_folder(new_dir)
                new_fid = folder_cache[new_dir]
                
                if new_fid != old_fid:
                    db.update_image_field(image_id, "folder_id", new_fid)
                    if old_fid:
                        affected_folders.add(old_fid)
                    if new_fid:
                        affected_folders.add(new_fid)

            # Invalidate aggregates for all affected folders
            for fid in affected_folders:
                try:
                    db.invalidate_folder_phase_aggregates(folder_id=fid)
                except Exception:
                    pass

            conn.commit()
            return {"success": True, "updated_count": count}
        except Exception as e:
            return {"error": str(e)}


def set_image_metadata(file_path: str, rating: Optional[int] = None, label: Optional[str] = None) -> dict:
    """Update metadata for a specific image in the database.
    Optionally updates sidecar files if background runners are active."""
    from modules import mcp_server as _ms

    details = db.get_image_details(file_path)
    if not details:
        return {"error": f"Image {file_path} not found in database"}

    image_id = details["id"]
    updates = {}
    if rating is not None:
        updates["rating"] = rating
    if label is not None:
        updates["label"] = label

    if not updates:
        return {"message": "No updates specified"}

    try:
        for field, value in updates.items():
            db.update_image_field(image_id, field, value)

        # Notify gallery if context exists
        if _ms._gradio_context:
            msg = f"Updated {file_path}: {updates}"
            logger.info(f"MCP metadata update: {msg}")

        return {"success": True, "image_id": image_id, "updates": updates}
    except Exception as e:
        return {"error": str(e)}


def prune_missing_files(dry_run: bool = True) -> dict:
    """Remove database records for images whose files no longer exist on disk."""
    from modules import utils
    try:
        rows = db.get_connector().query("SELECT id, file_path FROM images")
        to_prune = []  # List of (id, path)

        for row in rows:
            # Robust row access: handle both dict and RowWrapper (which might iterate as tuples)
            if hasattr(row, 'get'):
                image_id = row.get("id")
                file_path = row.get("file_path")
            elif isinstance(row, (list, tuple)) and len(row) >= 2:
                # Fallback for raw tuples
                image_id, file_path = row[0], row[1]
            else:
                try:
                    image_id = row["id"]
                    file_path = row["file_path"]
                except Exception:
                    continue

            if not file_path:
                to_prune.append((image_id, file_path))
                continue
            
            # Ensure file_path is a string (defensive)
            if isinstance(file_path, (list, tuple)) and len(file_path) > 0:
                file_path = file_path[0]
            
            # Use resolve_file_path for consistent resolution across the app
            resolved = utils.resolve_file_path(file_path, image_id)
            if not resolved:
                to_prune.append((image_id, file_path))

        if dry_run:
            return {
                "dry_run": True,
                "to_prune_count": len(to_prune),
                "examples": [p for _, p in to_prune][:10]
            }

        if not to_prune:
            return {"success": True, "pruned_count": 0}

        # Batch delete using the existing delete_image which handles relations
        count = 0
        for mid, mpath in to_prune:
            if mpath:
                db.delete_image(mpath)
            else:
                # If path is null, delete by ID directly
                db.get_connector().execute("DELETE FROM images WHERE id = ?", (mid,))
            count += 1

        return {"success": True, "pruned_count": count}
    except Exception as e:
        return {"error": str(e)}


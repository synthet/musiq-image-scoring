"""Scope path and preview helpers for electron API routes."""

from __future__ import annotations

import os
import platform
from typing import Any

from fastapi import HTTPException


def normalize_scope_path_input(raw: str) -> str:
    """Trim and strip trailing slashes; keep Windows drive roots (e.g. D:\\) as directory paths."""
    s = (raw or "").strip()
    while len(s) > 1 and s[-1] in "/\\":
        prev = s[:-1]
        if len(prev) == 2 and prev[1] == ":":
            break
        s = prev
    return s


def scope_resolve_path(raw_path: str) -> str:
    """Map user path to an existing filesystem path for this OS (WSL /mnt/..., Windows, typos in slashes)."""
    from modules import utils

    path = normalize_scope_path_input(raw_path)
    if not path:
        raise HTTPException(status_code=400, detail="Empty path")
    local_path, tried = utils.resolve_scope_input_path(path)
    if not local_path:
        sysname = platform.system()
        sl = path.replace("\\", "/")
        extra = ""
        if sysname == "Linux" and sl.startswith("/mnt/"):
            segs = [x for x in sl.split("/") if x]
            if len(segs) >= 2 and segs[0] == "mnt":
                drv = segs[1]
                mroot = f"/mnt/{drv}"
                if not os.path.exists(mroot):
                    extra = (
                        f" {mroot}/ is not mounted here (WSL automount disabled, container without a host bind, "
                        "or this process is not WSL). Run the WebUI where that path exists, or bind-mount the folder."
                    )
        if utils.is_docker_runtime():
            extra += (
                " Docker: only bind-mounted paths exist inside the container (besides `.:/app`). "
                "`webui.volumes` uses ${PHOTOS_BIND_SOURCE:-/mnt/d/Photos}:/mnt/d/Photos — if `/mnt/d` is missing here, "
                "you are likely on Docker Desktop for Windows: set PHOTOS_BIND_SOURCE to a Windows path in `.env` "
                "(e.g. PHOTOS_BIND_SOURCE=D:/Photos), then `docker compose up -d --force-recreate webui`. "
                "Using /mnt/d/... as the compose host source only works when the Docker engine runs inside WSL."
            )
        uniq_try = []
        for t in tried:
            if t not in uniq_try:
                uniq_try.append(t)
        preview = ", ".join(repr(t) for t in uniq_try[:5])
        if len(uniq_try) > 5:
            preview += ", …"
        raise HTTPException(
            status_code=400,
            detail=(
                f"Path not found: {raw_path}. Checked: {preview or '(no variants)'}. "
                f"This server runs on {sysname}: use a path visible to that process "
                f"(native Windows: D:\\Photos\\...; WSL/Linux: /mnt/d/Photos/... when drives are mounted)."
                f"{extra}"
            ),
        )
    return local_path


def scope_count_images_on_disk(local_path: str, recursive: bool) -> tuple[int, int]:
    """Count images and folders on disk. Returns (image_count, folder_count)."""
    from modules.indexing_policy import (
        discovery_extensions,
        path_is_indexing_excluded,
        prune_indexing_excluded_walk_dirs,
    )

    exts = discovery_extensions()
    if not os.path.isdir(local_path):
        return (0, 0)
    img_count = 0
    folder_count = 0
    if recursive:
        for root, dirs, files in os.walk(local_path):
            prune_indexing_excluded_walk_dirs(root, dirs)
            folder_count += 1
            for f in files:
                fp = os.path.join(root, f)
                if path_is_indexing_excluded(fp):
                    continue
                if os.path.splitext(f)[1].lower() in exts:
                    img_count += 1
    else:
        folder_count = 1
        for f in os.listdir(local_path):
            fp = os.path.join(local_path, f)
            if os.path.isfile(fp) and os.path.splitext(f)[1].lower() in exts:
                img_count += 1
    return (img_count, folder_count)


def compute_scope_preview_for_resolved_paths(
    resolved_paths: list[str],
    recursive: bool,
) -> dict[str, Any]:
    """Aggregate scope preview for paths already resolved via ``scope_resolve_path``."""
    from modules import db
    from modules.phases import PhaseCode

    total_images = 0
    folder_count = 0
    stage_done: dict[str, int] = {}
    stage_failed: dict[str, int] = {}
    stage_skipped: dict[str, int] = {}
    stage_total: dict[str, int] = {}
    phase_codes = [p.value for p in PhaseCode]

    stage_running: dict[str, int] = {}
    stage_queued: dict[str, int] = {}
    for local_path in resolved_paths:
        summary = db.get_folder_phase_summary(local_path, force_refresh=True)
        db_img_count = (summary[0].get("total_count", 0) if summary else 0)
        if summary and db_img_count > 0:
            folder_count += 1
            img_count = summary[0].get("total_count", 0) if summary else 0
            total_images += img_count
            for row in summary:
                code = row.get("code", "")
                stage_total[code] = stage_total.get(code, 0) + row.get("total_count", 0)
                stage_done[code] = stage_done.get(code, 0) + row.get("done_count", 0)
                stage_failed[code] = stage_failed.get(code, 0) + row.get("failed_count", 0)
                stage_skipped[code] = stage_skipped.get(code, 0) + row.get("skipped_count", 0)
                stage_running[code] = stage_running.get(code, 0) + int(row.get("running_count") or 0)
                stage_queued[code] = stage_queued.get(code, 0) + int(row.get("queued_count") or 0)
        else:
            img_count, n_folders = scope_count_images_on_disk(local_path, recursive)
            if img_count > 0 or n_folders > 0:
                folder_count += n_folders
                total_images += img_count
                for code in phase_codes:
                    stage_total[code] = stage_total.get(code, 0) + img_count
                    stage_done[code] = stage_done.get(code, 0)
                    stage_failed[code] = stage_failed.get(code, 0)
                    stage_skipped[code] = stage_skipped.get(code, 0)

    stage_statuses: dict[str, str] = {}
    stage_counts: dict[str, Any] = {}
    for code in phase_codes:
        total = stage_total.get(code, 0)
        done = stage_done.get(code, 0)
        failed = stage_failed.get(code, 0)
        skipped = stage_skipped.get(code, 0)
        running = stage_running.get(code, 0)
        queued = stage_queued.get(code, 0)
        if total == 0:
            status = "not_started"
        elif running > 0:
            status = "running"
        elif queued > 0:
            status = "queued"
        elif failed > 0:
            status = "failed"
        elif done == total or (done + skipped) == total and failed == 0:
            status = "done"
        elif done > 0 or skipped > 0:
            status = "partial"
        else:
            status = "not_started"
        stage_statuses[code] = status
        stage_counts[code] = {
            "done": done,
            "failed": failed,
            "skipped": skipped,
            "total": total,
            "running": running,
            "queued": queued,
        }

    return {
        "image_count": total_images,
        "folder_count": folder_count,
        "stage_statuses": stage_statuses,
        "stage_counts": stage_counts,
    }


def build_scope_tree_sync(include_phase_status: bool = True):
    """Sync implementation run in thread pool to avoid blocking event loop."""
    from modules import db, utils
    from modules.ui_tree import build_tree_dict

    raw_folders = db.get_all_folders()
    folders = []
    for p in raw_folders:
        local_p = utils.convert_path_to_local(p) if hasattr(utils, "convert_path_to_local") else p
        if not local_p:
            continue
        norm = os.path.normpath(local_p)
        basename = os.path.basename(norm).lower()
        if basename in [".tmp.drivedownload", ".tmp.driveupload", "keywords_output", "."]:
            continue
        folders.append(local_p)
    folders = list(set(folders))
    tree_dict = build_tree_dict(folders)

    dc_map = db.get_folder_direct_image_counts_by_local_path_norm()

    def rollup_image_counts(node: dict) -> int:
        pkey = os.path.normpath(node.get("path") or "")
        meta = dc_map.get(pkey) or {}
        direct = int(meta.get("direct_count") or 0)
        children = node.get("children") or []
        under = sum(rollup_image_counts(ch) for ch in children)
        total = direct + under
        node["image_count"] = total
        return total

    for root in tree_dict:
        rollup_image_counts(root)

    if not include_phase_status:
        return tree_dict

    bulk_cache = db.get_all_folder_phase_summaries_bulk()

    def enrich(nodes: list[dict]) -> list[dict]:
        result = []
        for node in nodes:
            path = node.get("path", "")
            if path:
                summary = bulk_cache.get(os.path.normpath(path))
                if summary:
                    node["phase_statuses"] = {
                        row["code"]: row.get("status", "not_started") for row in summary
                    }
            if "children" in node:
                node["children"] = enrich(node["children"])
            result.append(node)
        return result

    return enrich(tree_dict)

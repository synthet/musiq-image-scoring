#!/usr/bin/env python3
"""Fix electron router: hoist models, Body(...) on POST bodies, api_models import."""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PATH = ROOT / "modules" / "api" / "routers" / "electron.py"

POST_BODY_HANDLERS = [
    "delete_empty_folder_cache_route",
    "update_image",
    "export_gallery",
    "preview_validation_repair",
    "auto_drive_runs",
    "start_runs_drive",
    "submit_run",
    "scope_preview",
    "reorder_queue",
]


def hoist_models(text: str) -> str:
    """Move nested BaseModel classes to module level (before create_electron_router)."""
    factory_match = re.search(r"\ndef create_electron_router\(\)", text)
    if not factory_match:
        raise SystemExit("create_electron_router not found")
    # Exclude the original ``def create_electron_router`` line from ``before``;
    # ``new_factory`` re-adds the header once.
    factory_def_start = factory_match.start() + 1
    factory_body_start = text.find("\n", factory_def_start) + 1

    return_end = text.rfind("\n    return router\n")
    if return_end < 0:
        raise SystemExit("return router not found")

    factory_body = text[factory_body_start:return_end]
    extracted: list[str] = []
    remaining: list[str] = []
    lines = factory_body.splitlines(keepends=True)
    i = 0
    while i < len(lines):
        line = lines[i]
        if re.match(r"    class \w+\(BaseModel\)", line):
            block: list[str] = []
            while i < len(lines):
                block.append(lines[i][4:] if lines[i].startswith("    ") else lines[i])
                i += 1
                if i < len(lines) and (
                    re.match(r"    class \w+\(BaseModel\)", lines[i])
                    or lines[i].startswith("    @router")
                    or lines[i].startswith("    def ")
                    or lines[i].startswith("    async def ")
                ):
                    break
            extracted.extend(block)
            if extracted and not extracted[-1].endswith("\n"):
                extracted.append("\n")
            extracted.append("\n")
            continue
        remaining.append(line)
        i += 1

    if not extracted:
        return text

    # Drop local DeleteFolderCacheRequest — use api_models
    extracted_text = "".join(extracted)
    extracted_text = re.sub(
        r"class DeleteFolderCacheRequest\(BaseModel\):.*?(?=\nclass |\Z)",
        "",
        extracted_text,
        count=1,
        flags=re.DOTALL,
    )

    before = text[:factory_def_start]
    after = text[return_end:]
    new_factory = "def create_electron_router() -> APIRouter:\n" + "".join(remaining)
    return before + "\n" + extracted_text + "\n" + new_factory + after


def add_delete_folder_cache_import(text: str) -> str:
    if "DeleteFolderCacheRequest" not in text:
        return text
    if "DeleteFolderCacheRequest," in text.split("from modules.api_models import")[1].split(")")[0]:
        return text
    return text.replace(
        "    CullingAnalyticsResponse,\n",
        "    CullingAnalyticsResponse,\n    DeleteFolderCacheRequest,\n",
    )


def add_body_to_post_handlers(text: str) -> str:
    for name in POST_BODY_HANDLERS:
        # request: ModelName) -> request: ModelName = Body(...))
        text = re.sub(
            rf"(async def {name}\([^)]*request: (\w+))\)",
            r"\1 = Body(...))",
            text,
        )
        # update_image uses request: ImageUpdateRequest without named request in some cases
    # update_image(image_id: int, request: ImageUpdateRequest)
    text = re.sub(
        r"(async def update_image\(image_id: int, request: ImageUpdateRequest)\)",
        r"\1 = Body(...))",
        text,
    )
    return text


def add_handler_registry(text: str) -> str:
    if "register_handlers" in text:
        return text
    insert = """
    from modules.api.handler_registry import register_handlers

    register_handlers(
        {
            "get_folder_tree": get_folder_tree,
            "get_folder_phase_status": get_folder_phase_status,
        }
    )

"""
    return text.replace("\n    return router\n", insert + "    return router\n", 1)


def main() -> None:
    text = PATH.read_text(encoding="utf-8")
    text = hoist_models(text)
    text = add_delete_folder_cache_import(text)
    text = add_body_to_post_handlers(text)
    text = add_handler_registry(text)
    PATH.write_text(text, encoding="utf-8")
    print("fixed electron.py")


if __name__ == "__main__":
    main()

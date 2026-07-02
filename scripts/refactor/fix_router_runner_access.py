#!/usr/bin/env python3
"""Fix router modules to read runners via modules.api (test monkeypatch compat)."""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ROUTERS = ROOT / "modules" / "api" / "routers"

RUNNER_ATTRS = [
    "_scoring_runner",
    "_tagging_runner",
    "_clustering_runner",
    "_selection_runner",
    "_bird_species_runner",
    "_indexing_runner",
    "_metadata_runner",
    "_maintenance_runner",
    "_orchestrator",
    "_job_dispatcher",
]

HELPER = """

import sys


def _api_module():
    return sys.modules["modules.api"]

"""


def main() -> None:
    for path in ROUTERS.glob("*.py"):
        if path.name in ("__init__.py", "public.py"):
            continue
        text = path.read_text(encoding="utf-8")
        if "_api_module" not in text:
            text = re.sub(
                r"(logger = logging\.getLogger\(__name__\)\n)",
                r"\1" + HELPER,
                text,
                count=1,
            )
        for attr in RUNNER_ATTRS:
            text = text.replace(f"state.{attr}", f"_api_module().{attr}")
        path.write_text(text, encoding="utf-8")
    print("fixed runner access in routers")


if __name__ == "__main__":
    main()

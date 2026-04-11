#!/usr/bin/env python3
"""Canonical backend API contract gate.

Fails when FastAPI routes in modules/api.py + modules/api_db.py drift from
`docs/reference/api/openapi.yaml`.
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
ROUTE_FILES = [ROOT / "modules" / "api.py", ROOT / "modules" / "api_db.py"]
OPENAPI_PATH = ROOT / "docs" / "reference" / "api" / "openapi.yaml"
ROUTE_PATTERN = re.compile(
    r"@router\.(get|post|put|patch|delete|head|options)\(\s*[\"']([^\"']+)[\"']"
)


def extract_routes(path: Path) -> set[str]:
    content = path.read_text(encoding="utf-8")
    return {f"{method.upper()} {route}" for method, route in ROUTE_PATTERN.findall(content)}


def load_openapi_routes(path: Path) -> set[str]:
    spec = yaml.safe_load(path.read_text(encoding="utf-8"))
    routes: set[str] = set()
    for openapi_path, methods in spec.get("paths", {}).items():
        for method in methods:
            if method in {"get", "post", "put", "patch", "delete", "head", "options"}:
                routes.add(f"{method.upper()} {openapi_path}")
    return routes


def main() -> int:
    code_routes = set().union(*(extract_routes(path) for path in ROUTE_FILES))
    openapi_routes = load_openapi_routes(OPENAPI_PATH)

    missing_from_spec = sorted(code_routes - openapi_routes)
    missing_from_code = sorted(openapi_routes - code_routes)

    print("[contract:check] API route parity")
    print(f"- routes_in_code: {len(code_routes)}")
    print(f"- routes_in_openapi: {len(openapi_routes)}")
    print(f"- missing_from_spec: {len(missing_from_spec)}")
    print(f"- missing_from_code: {len(missing_from_code)}")

    if missing_from_spec:
        print("\nRoutes missing from docs/reference/api/openapi.yaml:")
        for route in missing_from_spec:
            print(f"  - {route}")

    if missing_from_code:
        print("\nRoutes in docs/reference/api/openapi.yaml but missing from code:")
        for route in missing_from_code:
            print(f"  - {route}")

    if missing_from_spec or missing_from_code:
        print("\nFAIL: contract drift detected.")
        return 1

    print("\nPASS: API contract is in sync.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

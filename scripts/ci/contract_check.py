#!/usr/bin/env python3
"""Canonical backend API contract gate.

Builds the FastAPI app exactly the way ``scripts/export_openapi.py`` does and
compares its live route table against the committed OpenAPI artifacts. This
catches the case nothing else covers today: ``.github/workflows/validate-api-types.yml``
only proves ``electron/apiTypes.ts`` matches ``openapi.json`` — it never proves
``openapi.json`` still matches the code, so routes added to ``modules/api/routers/``
silently never reach **image-scoring-gallery**.

Routes are read from the app object rather than parsed out of decorators, so
nested ``APIRouter`` prefixes (``/api``, ``/public/api``) resolve correctly.

Artifacts:

* ``openapi.json`` (repo root) — **blocking**. Source of truth for
  ``npm run api:types:generate``; regenerate with ``python scripts/export_openapi.py``.
* ``docs/reference/api/openapi.yaml`` / ``openapi.json`` — **advisory**. Documentation
  copies with no generator wired up; reported but non-fatal unless ``--strict``.

Usage::

    python scripts/ci/contract_check.py             # gate on the root artifact
    python scripts/ci/contract_check.py --strict    # also gate on the docs copies
    python scripts/ci/contract_check.py --json      # machine-readable summary
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
EXPORT_SCRIPT = ROOT / "scripts" / "export_openapi.py"

HTTP_METHODS = frozenset(
    {"get", "post", "put", "patch", "delete", "head", "options"}
)

BLOCKING_ARTIFACTS = (Path("openapi.json"),)
ADVISORY_ARTIFACTS = (
    Path("docs/reference/api/openapi.yaml"),
    Path("docs/reference/api/openapi.json"),
)


def build_live_app():
    """Import ``scripts/export_openapi.py`` and build its app.

    ``scripts/`` is not a package, so the module is loaded by path instead of
    imported. Reusing ``build_app`` keeps the contract definition in one place —
    if the export script starts mounting another router, this gate follows.
    """
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    spec = importlib.util.spec_from_file_location("_export_openapi", EXPORT_SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {EXPORT_SCRIPT}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.build_app()


def live_operations() -> set[str]:
    """``{"GET /api/health", ...}`` for every documented operation.

    Read from ``app.openapi()`` rather than ``app.routes`` so the comparison is
    schema-to-schema: FastAPI's built-in ``/docs``, ``/redoc`` and ``/openapi.json``
    routes exist on the app but are deliberately absent from the generated schema,
    and would otherwise show up as permanent false drift.
    """
    return spec_operations(build_live_app().openapi())


def spec_operations(spec: dict) -> set[str]:
    ops: set[str] = set()
    for spec_path, methods in (spec.get("paths") or {}).items():
        if not isinstance(methods, dict):
            continue
        for method in methods:
            if method.lower() in HTTP_METHODS:
                ops.add(f"{method.upper()} {spec_path}")
    return ops


def artifact_operations(path: Path) -> set[str]:
    text = path.read_text(encoding="utf-8")
    # yaml.safe_load parses JSON too, but json.loads is stricter and much faster
    # on the ~400 KB root artifact.
    spec = yaml.safe_load(text) if path.suffix == ".yaml" else json.loads(text)
    return spec_operations(spec)


def compare(live: set[str], path: Path) -> dict:
    full = ROOT / path
    if not full.exists():
        return {"artifact": path.as_posix(), "missing_artifact": True}
    documented = artifact_operations(full)
    return {
        "artifact": path.as_posix(),
        "missing_artifact": False,
        "documented": len(documented),
        "undocumented": sorted(live - documented),
        "phantom": sorted(documented - live),
    }


def report(result: dict, blocking: bool) -> bool:
    """Print one artifact's result. Returns True when it counts as a failure."""
    label = "FAIL" if blocking else "warn"
    name = result["artifact"]
    if result.get("missing_artifact"):
        print(f"[{label}] {name}: artifact not found")
        return blocking

    undocumented = result["undocumented"]
    phantom = result["phantom"]
    status = "ok" if not undocumented and not phantom else label
    print(
        f"[{status}] {name}: {result['documented']} documented, "
        f"{len(undocumented)} undocumented, {len(phantom)} phantom"
    )
    for route in undocumented:
        print(f"    + in code, not in artifact: {route}")
    for route in phantom:
        print(f"    - in artifact, not in code: {route}")
    return blocking and bool(undocumented or phantom)


def main() -> int:
    parser = argparse.ArgumentParser(description="Backend API contract gate")
    parser.add_argument(
        "--strict",
        action="store_true",
        help="also fail on the advisory docs/reference/api/* copies",
    )
    parser.add_argument("--json", action="store_true", help="emit a JSON summary")
    args = parser.parse_args()

    try:
        live = live_operations()
    except Exception as exc:  # noqa: BLE001 — surface import failures as gate output
        print(f"FAIL: could not build the API app: {exc}", file=sys.stderr)
        return 1

    blocking = [compare(live, p) for p in BLOCKING_ARTIFACTS]
    advisory = [compare(live, p) for p in ADVISORY_ARTIFACTS]

    if args.json:
        print(
            json.dumps(
                {
                    "routes_in_code": len(live),
                    "blocking": blocking,
                    "advisory": advisory,
                    "strict": args.strict,
                },
                indent=2,
            )
        )
        failed = any(
            r.get("missing_artifact") or r["undocumented"] or r["phantom"]
            for r in blocking
        )
        if args.strict:
            failed = failed or any(
                r.get("missing_artifact") or r["undocumented"] or r["phantom"]
                for r in advisory
            )
        return 1 if failed else 0

    print("[contract:check] API route parity")
    print(f"- routes_in_code: {len(live)}")
    failed = False
    for result in blocking:
        failed |= report(result, blocking=True)
    for result in advisory:
        failed |= report(result, blocking=args.strict)

    if failed:
        print(
            "\nFAIL: contract drift detected. "
            "Regenerate with: python scripts/export_openapi.py "
            "&& npm run api:types:generate"
        )
        return 1
    print("\nPASS: API contract is in sync.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

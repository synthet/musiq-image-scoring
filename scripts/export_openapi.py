"""Export OpenAPI JSON schema without starting the full server.

Creates a minimal FastAPI app with just the API router (no Gradio, no lifespan)
and writes the OpenAPI schema to a JSON file.

Usage:
    python scripts/export_openapi.py              # writes to openapi.json in project root
    python scripts/export_openapi.py -o path.json  # writes to custom path

Re-run this script whenever endpoints or Pydantic models in modules/api.py change.
"""

import json
import sys
import argparse
from pathlib import Path

# Ensure project root is on sys.path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from fastapi import FastAPI
from modules.api import create_api_router, create_public_api_router
from modules.ui.source_image_api import router as source_image_router


def build_app() -> FastAPI:
    """Build a minimal FastAPI app with API and source-image routes for schema extraction."""
    app = FastAPI(
        title="Vexlum Scoring WebUI API",
        description="REST API for the Vexlum Scoring WebUI application.",
        version="1.0.0",
        openapi_tags=[
            {"name": "Vexlum Scoring API", "description": "Endpoints for image quality assessment and scoring operations."},
            {"name": "Public Image API", "description": "Read-only JSON endpoints for image records (/public/api)."},
            {"name": "Tagging API", "description": "Endpoints for image tagging and keyword extraction."},
            {"name": "General API", "description": "General endpoints for health checks, status, and job management."},
        ],
    )
    app.include_router(create_api_router())
    app.include_router(create_public_api_router())
    app.include_router(source_image_router)
    return app


def main():
    parser = argparse.ArgumentParser(description="Export OpenAPI schema to JSON")
    parser.add_argument("-o", "--output", default=str(ROOT / "openapi.json"),
                        help="Output file path (default: <project_root>/openapi.json)")
    args = parser.parse_args()

    app = build_app()
    schema = app.openapi()

    out = Path(args.output)
    out.write_text(json.dumps(schema, indent=2), encoding="utf-8")
    print(f"OpenAPI schema written to {out}  ({len(schema.get('paths', {}))} paths)")


if __name__ == "__main__":
    main()

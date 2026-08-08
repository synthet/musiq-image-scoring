"""Read-only access to the production database for the bird-crop study.

Why this does not reuse ``scripts.research.clip_culling.common``
---------------------------------------------------------------
``common`` pins the *app connector* to the E2E database at import time
(``os.environ.setdefault("POSTGRES_DB", "image_scoring_test")``). That is correct
for the culling spike, which writes embeddings, but wrong here: ``bird_bbox``
lives only in production, and the species step drives ``modules.bird_species``,
which goes through ``modules.db``. Importing ``common`` would silently retarget
that at E2E. So this study keeps its own connection and never pins the app
connector.

Every connection opened here is ``readonly=True``, so an accidental write raises
rather than touching a 66k-image production library.

Run in WSL with the app venv::

    source ~/.venvs/tf/bin/activate
    python -m scripts.research.bird_crop.geometry_eval --help
"""

from __future__ import annotations

import json
import logging
import os
import sys
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Generator, Optional, Sequence

PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

logger = logging.getLogger("bird_crop")

PROD_DB = "image_scoring"
PROD_PORT = 5432

#: Study artifacts. Committed, per the harness convention (see REFERENCES.md).
REPORTS_DIR = PROJECT_ROOT / "reports" / "bird-crop"
LABELS_DIR = REPORTS_DIR / "labels"
SHEETS_DIR = LABELS_DIR / "sheets"


def configure_logging(verbose: bool = False) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
    )


@contextmanager
def connection() -> Generator[Any, None, None]:
    """Yield a **read-only** psycopg2 connection to production."""
    import psycopg2

    conn = psycopg2.connect(
        host=os.environ.get("PROD_HOST", os.environ.get("POSTGRES_HOST", "127.0.0.1")),
        port=int(os.environ.get("PROD_PORT", PROD_PORT)),
        dbname=os.environ.get("PROD_DB", PROD_DB),
        user=os.environ.get("POSTGRES_USER", "postgres"),
        password=os.environ.get("POSTGRES_PASSWORD", "postgres"),
    )
    conn.set_session(readonly=True, autocommit=True)
    try:
        yield conn
    finally:
        conn.close()


def select(sql: str, params: Optional[Sequence[Any]] = None) -> list[dict]:
    """Run a SELECT against production and return a list of dicts."""
    from psycopg2.extras import RealDictCursor

    with connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(sql, params)
            return [dict(r) for r in cur.fetchall()]


def assert_prod() -> None:
    """Verify we are actually talking to the production library, not E2E.

    Guards the opposite direction from ``common.assert_e2e()``: the study is
    worthless if it silently runs against the 4-folder E2E subset, which has no
    ``bird_bbox`` data.
    """
    rows = select("SELECT current_database() AS db, COUNT(*) AS n FROM images", None)
    db_name, n = rows[0]["db"], rows[0]["n"]
    if db_name != PROD_DB:
        raise RuntimeError(
            f"SAFETY: connected to {db_name!r}, expected {PROD_DB!r}. "
            "This study reads production; set PROD_DB/PROD_PORT if that is intended."
        )
    boxed = select(
        "SELECT COUNT(*) AS n FROM images WHERE jsonb_exists(bird_bbox, 'x1')", None
    )[0]["n"]
    if boxed == 0:
        raise RuntimeError(
            f"{db_name!r} has {n} images but 0 with a bird_bbox; nothing to study. "
            "Run scripts/backfill_bird_bbox.py first."
        )
    logger.info("Read-only on %s: %d images, %d with a bird box.", db_name, n, boxed)


def write_json(name: str, payload: Any, *, subdir: str = "") -> Path:
    """Write JSON under ``reports/bird-crop/``."""
    out_dir = REPORTS_DIR / subdir if subdir else REPORTS_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / name
    with open(out, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, default=str)
    logger.info("Wrote %s (%d bytes)", out, out.stat().st_size)
    return out


def write_text(name: str, text: str, *, subdir: str = "") -> Path:
    """Write a markdown/text report under ``reports/bird-crop/``."""
    out_dir = REPORTS_DIR / subdir if subdir else REPORTS_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / name
    with open(out, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)
    logger.info("Wrote %s (%d bytes)", out, out.stat().st_size)
    return out

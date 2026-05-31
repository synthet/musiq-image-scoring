#!/usr/bin/env python3
"""Shared scaffolding for the OpenCLIP L/14 head spike harness (throwaway research).

Plan: ``C:\\Users\\dmnsy\\.cursor\\plans\\openclip_l14_head_spike_36b9b9aa.plan.md``.
References: ``scripts/research/clip_culling/REFERENCES.md``.

Write boundary
--------------
*All* reads and writes from experiment/persist code target the **E2E** Postgres
DB (container ``image-scoring-postgres-e2e``, database ``image_scoring_test`` on
host port 5433). Production ``image_scoring`` @5432 is touched **only** by the
seed step, and only with SELECTs. Importing this module pins the app connector
to E2E by setting ``POSTGRES_PORT``/``POSTGRES_DB`` *before* ``modules.db`` loads.

Run in WSL with the app venv::

    source ~/.venvs/tf/bin/activate
    python -m scripts.research.clip_culling.seed_e2e_subset --folders 62,44,45,676
"""

from __future__ import annotations

import json
import logging
import os
import sys
from pathlib import Path
from typing import Any, Optional

# ---------------------------------------------------------------------------
# Pin the app connector to the E2E DB *before* importing modules.db.
# ---------------------------------------------------------------------------
E2E_DB = "image_scoring_test"
E2E_PORT = "5433"
PROD_DB = "image_scoring"
PROD_PORT = 5432

os.environ.setdefault("POSTGRES_DB", E2E_DB)
os.environ.setdefault("POSTGRES_PORT", E2E_PORT)
os.environ.setdefault("POSTGRES_HOST", "127.0.0.1")

PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from modules import db, db_postgres  # noqa: E402
from modules import embedding_spaces as _es  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger("clip_culling")

# ---------------------------------------------------------------------------
# New embedding spaces registered for this spike (768-d -> image_embeddings_768).
# Distinct codes so OpenAI vs OpenCLIP L/14 never collide (tower-mismatch caveat).
# ---------------------------------------------------------------------------
SPACE_OPENAI_L14 = "openai_clip_vit_l14_image"
SPACE_OPENCLIP_L14 = "openclip_l14_laion2b_image"
SPACE_DINOV2 = "dinov2_reg_base_image"
SPACE_SIGLIP2 = "siglip2_base_image"
NEW_SPACES = {
    SPACE_OPENAI_L14: (768, "OpenAI CLIP ViT-L/14 image embedding (spike)"),
    SPACE_OPENCLIP_L14: (768, "OpenCLIP ViT-L/14 laion2b_s32b_b82k image embedding (spike)"),
    SPACE_DINOV2: (768, "DINOv2-with-registers base image embedding (spike)"),
    SPACE_SIGLIP2: (768, "SigLIP2 base patch16-224 image embedding (spike)"),
}

# Baseline spaces seeded from prod for correlation/diversity comparisons.
BASELINE_SPACES = ["mobilenet_v2_imagenet_gap", "clip_vit_b32_image", "bioclip_2_image"]

# Spaces compared in exp8 grouping-quality (768-d table except MobileNet/B32).
GROUPING_SPACES = [
    "mobilenet_v2_imagenet_gap",
    "clip_vit_b32_image",
    SPACE_OPENAI_L14,
    SPACE_OPENCLIP_L14,
    SPACE_DINOV2,
    SPACE_SIGLIP2,
]

# Paths --------------------------------------------------------------------
RESULTS_DIR = PROJECT_ROOT / "reports" / "clip-culling"
INPUT_SIZE_DIR = RESULTS_DIR / "input-size"
INPUT_SIZE_NPZ_DIR = INPUT_SIZE_DIR / "npz"
CACHE_DIR = Path(os.environ.get("CLIP_CULLING_CACHE", str(Path.home() / ".cache" / "clip_culling")))

# Embedding model keys for input-size sweep (NPZ cache filenames).
INPUT_SIZE_EMBEDDING_KEYS = [
    "mobilenet",
    "clip_b32",
    "openai_l14",
    "openclip_l14",
    "dinov2",
    "siglip2",
]

# Default long-edge grid (Phase 1).
DEFAULT_LONG_EDGES = (128, 224, 384, 512, 768)

# Extended IQA grids (Phase 2).
IQA_LONG_EDGES_STANDARD = (224, 384, 512, 768)
IQA_LONG_EDGES_HIGH = (768, 1024)  # TOPIQ / ARNIQA native cap
MUSIQ_LONG_EDGES = (224, 384, 512, 768)  # square pad via resolution_override
CAPTION_LONG_EDGES = (224, 384, 512, 768)

# Closed taxonomy for keyword eval (matches experiments.exp7_keywords).
KEYWORD_TAXONOMY = (
    "landscape", "portrait", "urban", "cityscape", "nature", "wildlife",
    "architecture", "macro", "street", "night", "black and white",
    "sunset", "sunrise", "beach", "forest", "mountain", "water",
    "flowers", "animals", "birds", "insect", "people", "abstract", "minimal",
    "aerial", "transportation",
)


# ---------------------------------------------------------------------------
# Safety guards
# ---------------------------------------------------------------------------
def assert_e2e() -> None:
    """Refuse to run experiment/persist code unless the app connector points at E2E.

    Guards against accidentally writing to production ``image_scoring`` @5432.
    """
    cfg = db_postgres.get_pg_config()
    dbname = cfg.get("dbname")
    port = int(cfg.get("port", 0))
    if dbname != E2E_DB:
        raise RuntimeError(
            f"SAFETY: app connector dbname={dbname!r} (port {port}); refusing to run. "
            f"Expected {E2E_DB!r} on port {E2E_PORT}. Set POSTGRES_DB/POSTGRES_PORT."
        )
    if db._get_db_engine() != "postgres":
        raise RuntimeError("SAFETY: database.engine is not 'postgres'.")
    logger.info("Safety OK: writes target E2E %s on port %s.", dbname, port)


def wait_for_db(retries: int = 8, delay: float = 3.0) -> None:
    """Retry the E2E connection pool init until it succeeds.

    The Dockerized E2E Postgres can briefly drop connections when the WSL2/Docker
    backend settles; a few retries make long-running jobs resilient to that.
    """
    import time

    last = None
    for attempt in range(1, retries + 1):
        try:
            db_postgres.reset_pool()
            db_postgres.init_pool()
            with db_postgres.PGConnectionManager() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT 1")
                    cur.fetchone()
            if attempt > 1:
                logger.info("DB reachable after %d attempt(s).", attempt)
            return
        except Exception as e:  # noqa: BLE001
            last = e
            logger.warning("DB connect attempt %d/%d failed: %s", attempt, retries, e)
            time.sleep(delay)
    raise RuntimeError(f"E2E DB unreachable after {retries} attempts: {last}")


def register_l14_spaces() -> None:
    """Register spike embedding spaces in E2E: SPACE_DIMS + embedding_spaces rows.

    SPACE_DIMS is patched in-process (no production source edit). embedding_spaces
    rows are upserted into the E2E DB. Idempotent.
    """
    assert_e2e()
    for code, (dim, _desc) in NEW_SPACES.items():
        _es.SPACE_DIMS[code] = dim
    with db_postgres.PGConnectionManager(commit=True) as conn:
        with conn.cursor() as cur:
            for code, (dim, desc) in NEW_SPACES.items():
                cur.execute(
                    "INSERT INTO embedding_spaces (code, dim, description, active) "
                    "VALUES (%s, %s, %s, 1) "
                    "ON CONFLICT (code) DO UPDATE SET dim=EXCLUDED.dim, "
                    "description=EXCLUDED.description, active=1",
                    (code, dim, desc),
                )
    _es.invalidate_default_embedding_space_cache()
    for code in NEW_SPACES:
        sid = _es.get_embedding_space_id(code)
        logger.info("Registered space %s -> embedding_spaces.id=%s (dim %d)", code, sid, NEW_SPACES[code][0])


# ---------------------------------------------------------------------------
# Production read-only connection (seed step only)
# ---------------------------------------------------------------------------
def prod_connection():
    """Open a *read-only* psycopg connection to production @5432.

    Sets the session to read-only so any accidental write raises.
    """
    import psycopg2

    conn = psycopg2.connect(
        host=os.environ.get("PROD_HOST", "127.0.0.1"),
        port=int(os.environ.get("PROD_PORT", PROD_PORT)),
        dbname=PROD_DB,
        user=os.environ.get("POSTGRES_USER", "postgres"),
        password=os.environ.get("POSTGRES_PASSWORD", "postgres"),
    )
    conn.set_session(readonly=True, autocommit=True)
    return conn


# ---------------------------------------------------------------------------
# Pixel access
# ---------------------------------------------------------------------------
_RAW_EXT = {".nef", ".nrw", ".cr2", ".cr3", ".arw", ".dng", ".orf", ".raf", ".rw2"}


def resolve_read_path(row: dict, *, source: str = "thumb") -> Optional[str]:
    """Resolve a readable pixel path for an image row (WSL).

    * ``thumb`` — thumbnail when present, else ``file_path`` (production-like).
    * ``file`` — ``file_path`` only (full decode / RAW path).
    """
    fp = row.get("file_path") if hasattr(row, "get") else None
    if source == "file":
        if fp and os.path.exists(fp):
            return fp
        return None
    from modules.thumbnails import get_thumb_wsl

    thumb = get_thumb_wsl(row)
    if thumb and os.path.exists(thumb):
        return thumb
    if fp and os.path.exists(fp):
        return fp
    return None


def load_pil(read_path: str):
    from modules.thumbnails import open_image_for_ml

    img = open_image_for_ml(read_path)
    return img.convert("RGB")


def load_pil_resized(read_path: str, long_edge: int | None):
    """Load RGB PIL and downscale so ``max(width, height) <= long_edge`` (LANCZOS).

    When *long_edge* is None, only convert to RGB (no resize).
    """
    from PIL import Image

    img = load_pil(read_path)
    if long_edge is None or long_edge <= 0:
        return img
    w, h = img.size
    m = max(w, h)
    if m <= long_edge:
        return img
    ratio = long_edge / m
    new_size = (max(1, int(w * ratio)), max(1, int(h * ratio)))
    return img.resize(new_size, Image.LANCZOS)


def npz_cache_path(
    model_key: str,
    source: str,
    long_edge: int,
    *,
    preprocess_size: int | None = None,
    track: str = "embedding",
) -> Path:
    """Path for cached artifacts (``track`` = embedding | iqa | caption | tagging)."""
    INPUT_SIZE_NPZ_DIR.mkdir(parents=True, exist_ok=True)
    suffix = f"_preprocess{preprocess_size}" if preprocess_size else ""
    return INPUT_SIZE_NPZ_DIR / f"{track}_{model_key}_{source}_{long_edge}{suffix}.npz"


def write_input_size_json(name: str, payload: Any) -> Path:
    """Write JSON under ``reports/clip-culling/input-size/``."""
    INPUT_SIZE_DIR.mkdir(parents=True, exist_ok=True)
    out = INPUT_SIZE_DIR / name
    with open(out, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, default=str)
    logger.info("Wrote %s (%d bytes)", out, out.stat().st_size)
    return out


# ---------------------------------------------------------------------------
# Results writer
# ---------------------------------------------------------------------------
def write_json(name: str, payload: Any) -> Path:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    out = RESULTS_DIR / name
    with open(out, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, default=str)
    logger.info("Wrote %s (%d bytes)", out, out.stat().st_size)
    return out


def read_json(name: str) -> Optional[Any]:
    p = RESULTS_DIR / name
    if not p.exists():
        return None
    with open(p, encoding="utf-8") as f:
        return json.load(f)

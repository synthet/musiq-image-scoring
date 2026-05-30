"""Registry consistency + embedder spec tests for the optional culling towers.

No DB, GPU, or ML deps required — these guard the registry mirror against drift
between ``embedding_spaces.SPACE_DIMS``, the Postgres seed SQL, migration 0029,
and the embedder loader registry.
"""

from __future__ import annotations

import re

from modules import embedding_extractors as ee
from modules import embedding_spaces as es

# The four optional culling towers wired in 2026-05-29 (all 768-d).
CULLING_SPACE_CODES = {
    es.OPENCLIP_L14_IMAGE_SPACE_CODE,
    es.OPENAI_CLIP_L14_IMAGE_SPACE_CODE,
    es.DINOV2_REG_BASE_IMAGE_SPACE_CODE,
    es.SIGLIP2_BASE_IMAGE_SPACE_CODE,
}


def test_culling_codes_registered_in_space_dims():
    for code in CULLING_SPACE_CODES:
        assert es.SPACE_DIMS.get(code) == 768, code


def test_embedder_registry_matches_space_dims():
    # Every supported embedder maps to a registered space of the right dim.
    assert set(ee.SUPPORTED_CULLING_SPACES) == CULLING_SPACE_CODES
    for code, spec in ee.SUPPORTED_CULLING_SPACES.items():
        assert spec.code == code
        assert spec.dim == es.SPACE_DIMS[code]
        assert spec.loader in {"open_clip", "timm", "hf_siglip2", "hf_dinov2"}


def test_open_clip_specs_have_pretrained():
    for code, spec in ee.SUPPORTED_CULLING_SPACES.items():
        if spec.loader == "open_clip":
            assert spec.pretrained, code


def test_is_supported_and_get_spec():
    assert ee.is_supported(es.OPENCLIP_L14_IMAGE_SPACE_CODE)
    assert not ee.is_supported("mobilenet_v2_imagenet_gap")
    assert ee.get_spec(es.SIGLIP2_BASE_IMAGE_SPACE_CODE).loader == "hf_siglip2"


def test_get_spec_unknown_raises():
    try:
        ee.get_spec("does_not_exist")
    except ValueError as exc:
        assert "does_not_exist" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("expected ValueError for unknown space")


def test_seed_sql_matches_registry():
    from modules import db_postgres

    seed_codes = set()
    for sql in db_postgres._SEED_EXTRA_EMBEDDING_SPACES_SQL:
        for code, dim in re.findall(r"SELECT '([a-z0-9_]+)',\s*(\d+)", sql):
            seed_codes.add(code)
            assert es.SPACE_DIMS.get(code) == int(dim), code
    assert CULLING_SPACE_CODES <= seed_codes


def test_migration_0029_matches_registry():
    # Parse the migration as text so the test needs no alembic dependency.
    from pathlib import Path

    src = (
        Path(__file__).resolve().parents[1]
        / "migrations"
        / "versions"
        / "0029_culling_embedding_spaces.py"
    ).read_text(encoding="utf-8")

    assert re.search(r'down_revision\s*=\s*"0028"', src)
    pairs = re.findall(r'"([a-z0-9_]+)",\s*(768),', src)
    codes = {code for code, _dim in pairs}
    assert codes == CULLING_SPACE_CODES
    for code, dim in pairs:
        assert es.SPACE_DIMS[code] == int(dim)

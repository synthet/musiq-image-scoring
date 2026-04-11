"""Sanity checks for deleted_images Alembic revision (no DB required)."""

from pathlib import Path


def test_0006_migration_chain_text():
    root = Path(__file__).resolve().parents[1]
    p = root / "migrations" / "versions" / "0006_deleted_images.py"
    text = p.read_text(encoding="utf-8")
    assert 'revision = "0006"' in text
    assert 'down_revision = "0005"' in text
    assert "CREATE TABLE IF NOT EXISTS deleted_images" in text
    assert "trg_record_deleted_image_fn" in text

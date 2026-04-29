"""Sanity checks for the canceled→cancelled normalization migration."""

from pathlib import Path


def test_0015_migration_chain_text():
    root = Path(__file__).resolve().parents[1]
    p = root / "migrations" / "versions" / "0015_normalize_canceled_status.py"
    text = p.read_text(encoding="utf-8")
    assert 'revision = "0015"' in text
    assert 'down_revision = "0014"' in text
    assert "UPDATE jobs SET status = 'cancelled' WHERE status = 'canceled'" in text
    assert (
        "UPDATE job_phases SET state = 'cancelled' WHERE state = 'canceled'"
        in text
    )

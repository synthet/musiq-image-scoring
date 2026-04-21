"""
Static checks: startup migration log markers appear in the order a single
_init_db_impl run will print (Phase 1 complete → Phase 2 → keyword/XMP backfill).

No database required.
"""

from pathlib import Path


def test_init_db_impl_log_marker_order():
    root = Path(__file__).resolve().parents[1]
    text = (root / "modules" / "db_legacy.py").read_text(encoding="utf-8")

    phase1_done = text.find('[Phase 1] OK - Complete (integrity + index hardening).')
    phase2_start = text.find('[Phase 2] Starting Keyword Normalization + IMAGE_XMP Backfill...')
    backfill_kw = text.find('  [2.1c] Backfilling keywords from images...')
    backfill_xmp = text.find('  [2.6] Backfilling IMAGE_XMP from images...')

    assert phase1_done != -1
    assert phase2_start != -1
    assert backfill_kw != -1
    assert backfill_xmp != -1

    assert phase1_done < phase2_start < backfill_kw < backfill_xmp, (
        "Expected Phase 1 completion, then Phase 2 header, then backfill helpers in source order"
    )

    step_15e = text.find('  [1.5e] Adding STACK_CACHE FK constraints...')
    step_15f = text.find('  [1.5f] Adding UQ_FOLDERS_PATH...')
    assert step_15e != -1 and step_15f != -1
    assert step_15e < step_15f < phase1_done, "Expected Phase 1 substeps 1.5e → 1.5f before Phase 1 OK"

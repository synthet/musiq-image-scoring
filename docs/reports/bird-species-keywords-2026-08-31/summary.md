# Work summary — bird keyword preservation & IPS exhausted state

**Date:** 2026-08-31  
**Context:** Images like `/ui/images/202239` showed the `birds` tag while `/ui/images/205475` did not, despite both having gone through bird-species classification (`species:*` and/or internal exhausted markers).

---

## Problem

1. **`birds` tag dropped on species writes** — `BirdSpeciesRunner` rebuilt keywords from stale legacy `images.keywords` instead of normalized `image_keywords`. `_sync_image_keywords` DELETE+re-inserts all tags, so missing `birds` in the CSV removed it from the DB.

2. **`birds:species-exhausted` exposed as a keyword** — Terminal “no BioCLIP match” state was stored and filtered as a user-facing keyword. It appeared in the Gallery presets and image inspector chips.

---

## Solution

| Area | Change |
|------|--------|
| Species keyword merge | `build_bird_species_keyword_csv()` resolves normalized keywords first, strips old `species:*`, always preserves `birds` |
| No-match terminal state | IPS only: `bird_species` / `skipped` / `skip_reason=no_species_match` — no keyword write |
| Pending-work SQL | `_sql_bird_species_exhausted_ips()` replaces keyword marker (legacy keyword OR’d during migration) |
| API display | `get_resolved_image_keywords(hide_internal=True)` hides legacy `birds:species-exhausted` |
| Gallery UI | “No species match” preset → `phase_status=bird_species:skipped:no_species_match` |
| Runner query | `get_images_with_keyword()` overlays normalized keyword CSV on rows |

---

## Files touched (main)

- `modules/bird_species_eligibility.py` — helpers, IPS predicate, IPS-only `mark_species_exhausted`
- `modules/bird_species.py` — use merge helper; no keyword write on no-match
- `modules/db_legacy.py` — resolved keywords overlay, display strip, phase filter `phase:status:skip_reason`
- `modules/db/__init__.py` — `is_image_bird_species_complete` uses IPS exhausted check
- `scripts/schedule_bird_species_bird_folders.py` — gap SQL uses IPS
- `scripts/maintenance/backfill_bird_species_eligibility.py` — `--migrate-exhausted-keywords`, `--restore-birds-tag`
- `frontend/src/pages/GalleryPage.tsx` — phase_status preset
- `docs/technical/BIRD_SPECIES_WALKTHROUGH.md` — eligibility table updated
- Tests: `test_bird_species.py`, `test_bird_species_eligibility.py`, `test_phase_incomplete_sql_bird_bbox.py`

---

## Operator backfill (existing DB)

Run in gpu-shell after deploy:

```powershell
scripts\batch\docker_gpu_run.bat scripts/maintenance/backfill_bird_species_eligibility.py --migrate-exhausted-keywords --dry-run
scripts\batch\docker_gpu_run.bat scripts/maintenance/backfill_bird_species_eligibility.py --migrate-exhausted-keywords
scripts\batch\docker_gpu_run.bat scripts/maintenance/backfill_bird_species_eligibility.py --restore-birds-tag --dry-run
scripts\batch\docker_gpu_run.bat scripts/maintenance/backfill_bird_species_eligibility.py --restore-birds-tag
```

**Verify:** `/ui/images/205475` shows `birds` + `species:*`; no `birds:species-exhausted` chip.

---

## Tests

20 targeted pytest cases passed:

```bash
python -m pytest tests/test_bird_species_eligibility.py tests/test_phase_incomplete_sql_bird_bbox.py \
  tests/test_bird_species.py::test_runner_writes_bioclip_species_confidence_maps \
  tests/test_bird_species.py::test_runner_preserves_birds_when_legacy_keywords_empty \
  tests/test_bird_species.py::test_runner_no_match_writes_ips_only -q
```

---

## Related docs

- [worklog.md](./worklog.md) — session detail
- [BIRD_SPECIES_WALKTHROUGH.md](../../technical/BIRD_SPECIES_WALKTHROUGH.md)

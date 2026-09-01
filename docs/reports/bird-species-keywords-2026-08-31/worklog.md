# Worklog — bird keyword preservation & IPS exhausted state

**Date:** 2026-08-31  
**Session:** Cursor agent  
**Trigger:** User reported `/ui/images/202239` has `birds` tag but `/ui/images/205475` does not; requested preserving `birds` alongside `species:*` / exhausted markers, then revised plan to hide `birds:species-exhausted` and use DB-level IPS flag instead.

Append-only session log (newest actions at top below header).

---

## Outcome

- Forward path preserves `birds` when BioCLIP writes `species:*` keywords.
- No-match path writes **only** `image_phase_status` (`skipped` / `no_species_match`); keywords untouched.
- Legacy `birds:species-exhausted` keyword hidden from API/UI and migratable off DB.
- Gallery “No species match” filters via `phase_status`, not keyword.

---

## [2026-08-31] Implementation

### Diagnosis

- `BirdSpeciesRunner._classify_one` merged from `row.get("keywords")` (legacy column).
- On Postgres, normalized `image_keywords` often had `birds` while `images.keywords` was empty/stale.
- `_sync_image_keywords` replaces all normalized rows from CSV → `birds` lost after species run.
- Known audit bucket `species_no_birds` in `scripts/analysis/analyze_phase_status.py` matched symptom.
- `birds:species-exhausted` duplicated IPS state already written as `skip_reason=no_species_match`.

### Code changes

1. **`modules/bird_species_eligibility.py`**
   - Added `BIRDS_DISCOVERY_KEYWORD`, `BIRD_SPECIES_NO_MATCH_SKIP_REASON`
   - `ensure_birds_discovery_keyword()`, `build_bird_species_keyword_csv()`, `strip_legacy_exhausted_keyword()`
   - `_sql_bird_species_exhausted_ips()` — IPS predicate for terminal no-match
   - `_sql_exhausted_marker()` — IPS OR legacy keyword (migration window)
   - `mark_species_exhausted()` — IPS-only; no `update_image_keywords_for_image`
   - `strip_legacy_exhausted_keyword_csv()` — migration helper

2. **`modules/bird_species.py`**
   - Success path: `build_bird_species_keyword_csv()`
   - No-match path: `mark_species_exhausted(image_id)` only

3. **`modules/db_legacy.py`**
   - `get_images_with_keyword()` — batch overlay via `get_batch_resolved_image_keywords`
   - `_strip_internal_keywords_for_display()` + `hide_internal` on `get_resolved_image_keywords`
   - `_parse_phase_status_filter()` extended to `phase:status:skip_reason`
   - `_add_image_quality_filters()` applies skip_reason when present

4. **`modules/db/__init__.py`**
   - `is_image_bird_species_complete` uses `_sql_bird_species_exhausted_ips`

5. **`scripts/schedule_bird_species_bird_folders.py`**
   - Gap SQL excludes IPS `no_species_match` instead of keyword marker

6. **`scripts/maintenance/backfill_bird_species_eligibility.py`**
   - `--migrate-exhausted-keywords` — IPS row + strip legacy keyword
   - `--restore-birds-tag` — re-add `birds` on species/exhausted images missing it

7. **`frontend/src/pages/GalleryPage.tsx`**
   - Removed keyword preset `birds:species-exhausted`
   - Added phase preset `bird_species:skipped:no_species_match`

8. **`docs/technical/BIRD_SPECIES_WALKTHROUGH.md`**
   - Eligibility table and gallery filter notes updated

### Tests added/updated

| File | Coverage |
|------|----------|
| `tests/test_bird_species_eligibility.py` | IPS SQL, merge helper, IPS-only exhausted, classify_image_row skip_reason |
| `tests/test_bird_species.py` | Stale legacy CSV + normalized birds; no-match no keyword write |
| `tests/test_phase_incomplete_sql_bird_bbox.py` | Assert `no_species_match` in incomplete SQL |

**Result:** 20 passed.

### Lint

- `ruff check` on touched Python modules — clean after removing unused import in `modules/db/__init__.py`.

### Not done in session

- Backfill not run against live DB (operator step).
- No GitHub issue claim / PR opened.
- Gallery Electron sibling repo unchanged (backend SPA only).

---

## [2026-08-31] Planning

- Initial plan: preserve `birds` via merge helper + backfill.
- User iteration: do not display `birds:species-exhausted`; prefer IPS table flag.
- Confirmed storage: `image_phase_status` only (no new `images` column).

---

## References

- [summary.md](./summary.md)
- `modules/bird_species_eligibility.py`
- `docs/technical/BIRD_SPECIES_WALKTHROUGH.md`

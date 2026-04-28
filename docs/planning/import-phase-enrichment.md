# Prompt: Import Phase Enrichment — close the data gaps that stall later phases

## Context

In [modules/db_legacy.py:3643](../../modules/db_legacy.py#L3643) `register_image_for_import()`, the Import/Indexing phase writes only `file_path, file_name, file_type, folder_id, image_uuid, created_at`. Everything else is deferred to Metadata/Scoring/Keywords, and each downstream phase independently re-opens the file.

Meanwhile [modules/db_legacy.py:7360](../../modules/db_legacy.py#L7360) `get_phase_incomplete_sql()` defines `indexing` as incomplete when `image_hash IS NULL` — the import phase is marked "done" without producing the hash it claims to produce.

Concrete example: `D:/Photos/Z8/180-600mm/2026/2026-04-09/DSC_9925.NEF` (image id 134849) — a Nikon NEF that after Import has no hash, no size, no dimensions, no capture time, no sidecar linkage, no preview. Every downstream phase has to re-stat, re-open, and re-probe the file.

## Goal

Capture at Import time the **cheap, file-local** data that later phases otherwise fetch one-at-a-time, so Metadata/Scoring/Keywords/Culling start with a populated row instead of a near-empty one.

## Required fields to populate at Import

Extend `register_image_for_import()` (and the indexing walker in [modules/indexing_runner.py:174](../../modules/indexing_runner.py#L174)) to fill these on first write, idempotently:

| Field | Source | Why it belongs at Import |
|---|---|---|
| `image_hash` (SHA-256 of bytes) | stream file | Indexing's own "done" criterion; dedupe/stack lookup |
| `file_size` | `os.stat` | Change detection; rescore triggers |
| `file_mtime` | `os.stat` | Change detection across re-imports |
| `width`, `height` | EXIF header or RAW metadata (no full decode) | Scoring/thumbnail sizing; avoids re-opening |
| `capture_time` | EXIF `DateTimeOriginal` (fallback: file mtime) | Culling, sorting, stack grouping |
| `camera_model`, `lens_model`, `iso`, `f_number`, `exposure_time`, `focal_length` | EXIF header | Filters/facets, stack hints, bird_species heuristics |
| `xmp_sidecar_path` | glob `{basename}.xmp` next to file | Metadata phase otherwise re-scans the directory per image |
| `has_embedded_preview` + preview offset/size (for RAW) | NEF/CR2 IFD scan | Thumbnail phase can skip full decode |
| `path_type` already handled via `register_image_path` / `resolve_windows_path` — keep | — | — |

## Non-goals (explicitly defer)

- Full RAW decode, color management, LIQE/MUSIQ/TOPIQ scoring — stays in Scoring phase.
- Thumbnail generation — stays in Metadata/Thumbnail phase (but preview offset lets it skip RAW decode).
- Writing XMP — stays in Metadata.
- Keyword extraction — stays in Keywords.

## Correctness constraints

1. **Idempotent.** Re-importing an unchanged file must be a no-op (hash + mtime + size match → skip).
2. **Schema-additive only.** New columns go through Alembic migration in `migrations/versions/`; PostgreSQL is the source of truth per [CLAUDE.md](../../CLAUDE.md). Do not rename existing columns.
3. **Phase status honesty.** After Import, `image_phase_status[indexing] = 'done'` must imply `get_phase_incomplete_sql('indexing')` returns false for that row. Today it can lie.
4. **Tolerate partial failure.** If EXIF read fails on one file (corrupt RAW, unknown vendor tag), write what we have, log, mark `indexing` as `partial` not `done`. Do not fail the whole folder.
5. **RAW vendor coverage.** At minimum: NEF, CR2/CR3, ARW, DNG, RAF. Use a single EXIF reader (prefer `exiftool` subprocess batch mode if already a dep, else `pyexiv2`/`exifread`) — one pass per file, not per field.
6. **Cost budget.** Target ≤ 50 ms/file on SSD for a 30 MB NEF (hash + EXIF header read, no full decode). Batch EXIF calls if the library supports it.

## Acceptance

- Re-running Import on a folder whose images already have `image_hash` set completes in O(stat) time per file, no re-hashing.
- After Import of `DSC_9925.NEF`, a single row read returns: hash, size, mtime, dimensions, capture_time, camera/lens/ISO/f/exp/focal, xmp_sidecar_path (if present), preview offset (if NEF).
- `get_phase_incomplete_sql('indexing')` returns zero rows for the just-imported folder.
- Metadata phase, when it then runs, reads the existing row instead of re-opening the file for the fields above; its per-image time drops measurably (add one before/after timing log line to confirm).
- New unit tests under `tests/` cover: (a) fresh NEF import populates all fields; (b) second import is no-op; (c) corrupt EXIF → `partial` not `failed`; (d) XMP sidecar side-by-side is detected.

## Out of scope for this PR

- Re-backfilling historical rows. Provide a separate `scripts/maintenance/backfill_import_enrichment.py` that walks existing images and fills blanks, but do not run it automatically.
- Electron `electron/db.ts` changes — only needed if a new column is surfaced to the UI; keep this PR backend-only.

## Deliverables

1. Alembic migration adding the new columns (nullable, no backfill).
2. `modules/import_enrichment.py` (new) — single function `enrich_on_import(file_path) -> dict` returning the field bag; no DB writes.
3. Wire it into `register_image_for_import()` and the indexing walker; update `get_phase_incomplete_sql('indexing')` to reflect the new contract.
4. Unit tests as above.
5. One-paragraph note in [docs/technical/PIPELINE_TERMINOLOGY.md](../technical/PIPELINE_TERMINOLOGY.md) describing what Import now guarantees.

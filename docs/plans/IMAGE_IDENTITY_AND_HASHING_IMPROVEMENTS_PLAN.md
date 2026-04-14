# Plan: Image identity, hashing, and indexing improvements

## Goals

- **Performance:** Reduce disk I/O on large RAWs (especially re-runs and future “partial payload” digests).
- **Semantics:** Make it explicit whether identity is **byte-level**, **content-payload-level** (e.g. embedded preview), or **metadata-derived** (`image_uuid`).
- **Migration:** Support evolving digest algorithms without breaking lookups or caches.

## Current state (baseline)

| Mechanism | What it is | When it exists |
|-----------|------------|----------------|
| `images.image_hash` | Full-file SHA-256 (`compute_file_hash` / `calculate_image_hash`) | After indexing computes it |
| `images.image_uuid` | `ImageUniqueID` or deterministic fingerprint from EXIF fields, else random | After metadata / `upsert_image` when metadata available |
| Indexing rerun optimization | `metadata.indexing_content_fp` (`size`, `mtime_ns`) + reuse stored `image_hash` when fingerprint matches | After at least one successful index that persisted fp |
| `get_image_details` | Now includes `image_hash` (needed for pipeline / callers) | — |

**Non-goals for this document:** Changing scoring models or UI copy unless an API contract requires it.

---

## Improvement themes

### A. Versioned content identity (`hash_version`)

**Problem:** A single `image_hash` column cannot represent both “full file SHA-256” and “preview-strip SHA-256” without ambiguity.

**Direction:**

1. Add **`hash_version`** (smallint or text enum, e.g. `full_file_sha256_v1`, `embedded_preview_sha256_v1`).
2. Treat identity for dedupe/lookup as **`(image_hash, hash_version)`** (or a single composite if you prefer one column).
3. Update **`get_image_by_hash`**, indexes, and any unique constraints to be version-aware.
4. API: `GET /api/images/by-hash/{hash}` gains optional **`hash_version`** query param (or path segment); document defaults for backward compatibility.

**Dependencies:** Alembic migration (Postgres); Firebird reference DDL in `modules/db.py` if still maintained for parity.

---

### B. Faster / metadata-stable digest (aligned with product direction)

**Problem:** Full-file hash changes on any in-container byte change; large RAWs are expensive to read end-to-end.

**Direction (ordered preference, same as architecture discussion):**

1. **TIFF-based RAW (NEF, CR2, CR3, DNG, …):** Hash **embedded JPEG / JFIF** segments when present and stable enough for your tolerance.
2. **Fallback:** Hash **raw image strips** (format-specific, higher engineering cost).
3. **Small raster formats (JPEG/PNG/WebP):** Either keep full-file for simplicity or optional “entropy scan only” strategy behind a flag.

**Implementation sketch:**

- New module e.g. `modules/image_identity_hash.py` with `compute_content_identity(path) -> (hex: str, version: str)`.
- **`indexing_runner`** calls this instead of raw `calculate_image_hash` when config selects the new strategy; persists **`hash_version`** alongside `image_hash`.
- **`indexing_content_fp` reuse:** Only reuse cached hash when **fingerprint matches and `hash_version` matches** the one stored for that row (add `hash_version` to row or to metadata next to fp if you want zero schema change in phase 1 — prefer column long term).

**Risks:** Preview-only hashing can theoretically collide (two files sharing the same embedded preview). Mitigate with documentation + optional secondary check (e.g. file size) where needed.

---

### C. Clarify `image_uuid` vs `image_hash` (no substitution)

**Use `image_hash` (+ version)** for: byte/payload dedupe, `by-hash` API, delete blocklist by content, clustering cache keys that must track “same stored digest.”

**Use `image_uuid`** for: logical identity when EXIF/`ImageUniqueID` is available, merge-on-import (`find_image_id_by_uuid`), blocklist by `(file_name, image_uuid)` where appropriate.

**Do not** replace indexing-time full-file/payload digest with UUID **before** metadata exists — UUID may be null or random (`uuid4`) until metadata is populated.

Optional doc-only improvement: short **developer-facing** section in `docs/technical/API_CONTRACT.md` or `DB_SCHEMA.md` summarizing the above table.

---

### D. Downstream touchpoints when `hash_version` lands

| Area | Change |
|------|--------|
| `modules/clustering.py` | Persisted feature cache keys: include `hash_version` (or a single composite id) so caches do not collide across versions. |
| `modules/mcp_server.py` | `search_images_by_hash`: accept optional version; document behavior when omitted. |
| `scripts/python/backfill_hashes.py` | Extend to backfill `hash_version` and optionally recompute with new algorithm. |
| Frontend types | `image_hash` + optional `hash_version` on relevant payloads if exposed in API. |

---

## Phased rollout (recommended)

### Phase 0 — Done / keep stable

- `get_image_details` includes **`image_hash`**.
- Indexing **rerun optimization** via `indexing_content_fp` + reuse of stored hash (same full-file semantics).

### Phase 1 — Schema + API contract

- Add **`hash_version`** column with default **`1`** or **`full_file_sha256_v1`** for all existing rows.
- Composite unique index / lookup strategy for `(image_hash, hash_version)`.
- Version-aware DB helpers and HTTP handlers; default version when query param omitted = legacy behavior.

### Phase 2 — Pluggable identity digest

- Implement `compute_content_identity` for at least one RAW family + JPEG/PNG safe default.
- Wire **`indexing_runner`** + config flag to select algorithm; write **`hash_version`** on insert/update.
- Extend **`indexing_content_fp` reuse** to require matching **`hash_version`** (column or metadata).

### Phase 3 — Backfill and cache migration

- Offline or job-based **backfill** for existing rows (optional per folder).
- Invalidate or version-suffix **clustering** (and any other) caches that key on hash alone.

### Phase 4 — Hardening

- Golden tests per camera/format for “metadata edit does not change v2 digest when preview unchanged” (where promised).
- Collision monitoring hooks (logging) if preview-only strategy is enabled widely.

---

## Success criteria

- New indexes do not regress **indexing throughput** on small JPEG folders (measure baseline vs preview path on large NEF samples).
- **No silent cross-version dedupe:** two different `hash_version` values never map to the same logical cache row unless explicitly migrated.
- **Backward compatible API:** existing clients using hash-only URLs continue to work with documented default version.

---

## Open decisions (capture before Phase 2)

1. **Enum vs integer** for `hash_version` (readability vs compact indexes).
2. **Whether preview hash is enabled by default** for RAW or opt-in per `config.json`.
3. **Single migration** vs gradual per-folder reindex strategy for production datasets.

---

## References (in-repo)

- `modules/utils.py` — `compute_file_hash` / `calculate_image_hash`
- `modules/db.py` — `generate_image_uuid`, `upsert_image`, `find_image_id_by_uuid`
- `modules/indexing_runner.py` — indexing flow, `indexing_content_fp`
- `modules/clustering.py` — cache keys using `image_hash`
- `scripts/python/backfill_hashes.py` — hash backfill

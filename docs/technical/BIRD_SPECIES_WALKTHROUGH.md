# Bird Species Classification — Walkthrough

End-to-end walkthrough of the **bird species classification** feature: how a `POST /api/bird-species/start` request flows through the job queue, the runner, and the BioCLIP 2 model, and where results land in the database.

---

## 1. What this feature does

Given a folder of images (or an explicit image selector), the runner:

1. **Queries only images that already have the `birds` keyword** — everything else is ignored automatically.
2. Runs each image through **BioCLIP 2**, a zero-shot biology foundation model.
3. Stores the **single highest-scoring** species (BioCLIP argmax) as a **`species:Common Name`** keyword (e.g. `species:American Robin`) using the existing `image_keywords` / `keywords_dim` tables — no schema changes. Pass `top_k > 1` to store multiple candidates instead.

This is a standalone, asynchronous job — it does not require images to be re-scored or re-tagged first, as long as they already carry the `birds` keyword from a prior tagging run.

---

## 2. Architecture overview

Two entry points converge at the job queue:

```
[React UI — New Run modal]
  Bird Species ID ☑ → POST /runs/submit  {"stages": ["bird_species"]}
                              │
POST /api/bird-species/start  │
        │                     │
        ▼─────────────────────▼
  api.py: request validated, selectors resolved
        │
        ▼
  api.py: BirdSpeciesStartRequest
        │  • validate input_path / selectors
        │  • resolve_selectors() if explicit IDs given
        │
        ▼
  db.enqueue_job(job_type="bird_species", queue_payload={...})
        │
        ▼  (async — JobDispatcher poll loop)
  JobDispatcher._tick()
        │  • dequeue_next_job()
        │  • route on job_type (lowercased) → bird_species
        │
        ▼
  BirdSpeciesRunner.start_batch()  → background thread
        │
        ├─ db.get_images_with_keyword(folder, "birds")
        │        SQL JOIN on image_keywords + keywords_dim
        │        ← only images with "birds" keyword returned
        │
        ├─ filter: skip images that already have "species:*" (if overwrite=False)
        │
        ├─ BioCLIPClassifier.classify(image, species_list)
        │        open_clip.encode_image()  ──┐
        │        open_clip.encode_text()   ──┤ cosine similarity → softmax
        │        (text embeddings cached        └─ probs per species
        │         per batch — computed once)
        │
        └─ db.update_image_fields_batch([(id, {"keywords": merged})])
               ← writes "species:Name" into existing keywords
```

---

## 3. Data flow in detail

### 3.1 Enqueueing the job

`POST /api/bird-species/start` → `modules/api.py`:

```python
db.enqueue_job(
    job_source,           # input_path or "SELECTOR_BIRD_SPECIES"
    phase_code=None,      # not a pipeline phase — standalone job type
    job_type="bird_species",
    queue_payload={
        "input_path":        request.input_path,
        "candidate_species": request.candidate_species,   # None → use default list
        "threshold":         request.threshold,           # default 0.1
        "top_k":             request.top_k,               # default 1
        "overwrite":         request.overwrite,           # default False
        "resolved_image_ids": resolved_ids,               # None if folder scope
    },
)
```

The job lands in the `jobs` table with `status = 'queued'` and sits in the queue until a dispatcher tick picks it up.

### 3.2 Dispatcher routing

`modules/job_dispatcher.py` → `_start_job()`:

```python
if phase in ("bird_species", "bird-species"):
    return self.bird_species_runner.start_batch(
        input_path,
        job_id=job_id,
        candidate_species=payload.get("candidate_species"),
        threshold=float(payload.get("threshold", 0.1)),
        top_k=int(payload.get("top_k", 1)),
        overwrite=bool(payload.get("overwrite", False)),
        resolved_image_ids=payload.get("resolved_image_ids"),
    ) == "Started"
```

`_start_job()` resolves the handler from the job row: `phase = (job.get("job_type") or "").lower()` — values `bird_species` and `bird-species` both map to `BirdSpeciesRunner`.

The dispatcher holds the same guarantee as for all other job types: **only one runner runs at a time**. `_any_runner_busy()` now includes `bird_species_runner`.

### 3.2.1 Eligibility, exhausted markers, and backfill

| State | Meaning | Filter hint |
|-------|---------|-------------|
| **Not in scope** | No `birds` keyword | Bird phase N/A |
| **Pending** | `birds`, no `species:*`, not exhausted | Backlog / autodrive queue |
| **Complete** | Has `species:…` | Done |
| **Exhausted** | Run found no species above threshold | Keyword `birds:species-exhausted` — excluded from pending |

When BioCLIP returns no species above threshold, the runner writes `birds:species-exhausted` and sets IPS `skipped` / `no_species_match` so folders do not stay in `awaiting_bird_species` forever.

**Maintenance** (`scripts/maintenance/backfill_bird_species_eligibility.py`):

```bash
python scripts/maintenance/backfill_bird_species_eligibility.py --report
python scripts/maintenance/backfill_bird_species_eligibility.py --mark-exhausted --dry-run
python scripts/maintenance/backfill_bird_species_eligibility.py --mark-exhausted
python scripts/maintenance/backfill_bird_species_eligibility.py --enqueue
```

**Gallery:** pending species work ≈ keyword `birds` and exclude `birds:species-exhausted`.

### 3.3 Image filtering (the key constraint)

`modules/db_legacy.py` → `get_images_with_keyword()`:

```sql
SELECT * FROM images
WHERE
    EXISTS (
        SELECT 1 FROM image_keywords ik
        JOIN keywords_dim kd ON ik.keyword_id = kd.keyword_id
        WHERE ik.image_id = images.id
          AND kd.keyword_norm LIKE '%birds%'
    )
    AND images.folder_id = ?   -- or images.id IN (...)
ORDER BY file_name
```

Images in the same folder that do not carry the `birds` keyword are **never fetched** — the filter runs at the SQL layer, not in Python.

Implementation detail: the match is `keyword_norm LIKE '%birds%'` (substring). In practice this is the intended `birds` tag; a hypothetical keyword whose normalized form merely **contained** `birds` as a substring would also match (uncommon).

**Large selector lists (>900 IDs):** Firebird limits `IN (?)` clauses to ~900 parameters. When `resolved_image_ids` exceeds this threshold, `get_images_with_keyword()` omits the `IN` clause, fetches all bird-keyword images from the scope, and post-filters by ID in Python. The second-pass query (`_get_image_ids_with_species_keyword`) uses chunked batches of ≤900 IDs directly.

If `overwrite=False` (default), a second pass removes any images that already have a `species:*` keyword:

```sql
SELECT DISTINCT ik.image_id
FROM image_keywords ik
JOIN keywords_dim kd ON ik.keyword_id = kd.keyword_id
WHERE ik.image_id IN (?, ?, ...)
  AND kd.keyword_norm LIKE 'species:%'
```

### 3.4 BioCLIP 2 inference

`modules/bird_species.py` → `BioCLIPClassifier`:

*Simplified pseudocode* (actual code moves token tensors to the device, calls `encode_text(tokens)`, and sorts/filters results in a slightly different order — same math):

```python
# Model loaded once per runner instance (lazy, cached on self.classifier)
model, _, preprocess = open_clip.create_model_and_transforms("hf-hub:imageomics/bioclip-2")

# Text embeddings computed ONCE per batch (cached on self._cached_text_features)
prompts = [f"a photo of {name}, a bird species" for name in candidate_species]
text_features = model.encode_text(tokenizer(prompts))
text_features /= text_features.norm(dim=-1, keepdim=True)

# Per image (cheap):
img_features = model.encode_image(preprocess(Image.open(path)).unsqueeze(0))
img_features /= img_features.norm(dim=-1, keepdim=True)
probs = (img_features @ text_features.T * 100).softmax(dim=-1)[0]

# Apply threshold, take top_k
results = [(name, prob) for name, prob in zip(species, probs) if prob >= threshold]
results = sorted(results, key=lambda x: -x[1])[:top_k]
```

**Why common names?** Research benchmarks show scientific-name prompts collapse BioCLIP 2 accuracy from ~75% to ~6–10% top-1. The default list and prompt template use common names exclusively.

**Text embedding cache:** The candidate species list is the same for every image in a batch. `BioCLIPClassifier` pre-computes and caches the `(N_species, embed_dim)` text matrix before the image loop, so per-image cost is a single matrix multiply — no repeated `encode_text` calls.

### 3.5 Writing results to the database

Species predictions are merged with the image's existing keyword string:

```python
# Existing keywords minus any old species: entries (for overwrite path)
base_kws = [k for k in existing_kws if not k.lower().startswith("species:")]
new_kws  = [f"species:{name}" for name, _ in predictions]
merged   = ",".join(base_kws + new_kws)

db.update_image_fields_batch([(image_id, {"keywords": merged})])
```

`update_image_fields_batch` writes to both the `images.keywords` text column and synchronizes the `image_keywords` junction table, so the results are immediately visible in keyword-filtered gallery queries.

---

## 4. Model details

| Property | Value |
|----------|-------|
| Model | **BioCLIP 2** (`imageomics/bioclip-2`) |
| Interface | OpenCLIP (`open_clip_torch`) |
| Training data | TreeOfLife-200M (200 million biology images) |
| Zero-shot NABirds top-1 | **74.9%** |
| Zero-shot Birds 525 top-1 | ~72% (BioCLIP v1 baseline) |
| License | MIT |
| Input size | 224×224 (preprocessed by OpenCLIP transforms) |
| Device | CUDA if available, else CPU |

Benchmark and dataset figures come from the model authors’ reporting; see the [BioCLIP 2 model card on Hugging Face](https://huggingface.co/imageomics/bioclip-2) for up-to-date claims and licensing.

The model is loaded **lazily** on the first job and reused for all subsequent runs (cached on `BirdSpeciesRunner.classifier`). The WebUI startup is not slowed by model loading.

---

## 5. Default species list

`data/bird_species_list.txt` — bundled North American common names (~360 entries; recount the file if you need an exact number) organized by family group:

- Passerines (robins, warblers, sparrows, tanagers, finches, …)
- Woodpeckers
- Raptors (hawks, eagles, falcons, owls, vultures)
- Shorebirds and waders
- Herons, egrets, ibis
- Waterfowl (ducks, geese, swans)
- Gulls, terns, skuas
- Pigeons and doves
- Game birds (turkey, grouse, quail)
- Hummingbirds
- Kingfishers, flycatchers, vireos, corvids
- Seabirds (alcids, puffins, murres)
- Grebes and loons
- Pelicans, cormorants, anhingas
- Rails, coots, gallinules
- Nightjars and swifts

Comments (`#`) and blank lines are ignored. The file path is resolved relative to the project root at import time.

---

## 5a. Starting via the New Run UI

The "New Run" modal in the React frontend (`/ui/`) provides a point-and-click entry point for bird species classification without writing a cURL command.

**Steps:**

1. Click **New Run** in the sidebar or on the Runs page.
2. Set the scope type (Folder recursive / Folder flat / Single file) and enter the path.
3. Click **Refresh** to preview the matched images.
4. Under **Workflow Stages**, check **Bird Species ID** (last item in the list — opt-in, not checked by default).
   - Uncheck all other stages if this is a follow-up run after Tagging has already completed.
   - Checking both "Tagging" and "Bird Species ID" submits a tagging job only; the bird_species stage is queued separately as a second pass after tags exist.
5. Click **Queue Run →**.

**What happens on submit:**

The frontend posts:
```json
{ "scope_type": "folder_recursive", "scope_paths": ["D:/Photos/2024"], "stages": ["bird_species"] }
```

The `POST /runs/submit` handler strips `bird_species` from the pipeline phase list (it is not a `PhaseCode`), detects it as the sole requested stage, and enqueues a `job_type="bird_species"` job with default `threshold=0.1`, `top_k=1`. The new run appears immediately in the Runs list with status `queued`.

---

## 6. API reference

### `POST /api/bird-species/start`

Start a bird species classification job. Only images with the `birds` keyword are processed.

**Request body:**

```jsonc
{
  "input_path": "D:/Photos/2024",        // folder scope (mutually exclusive with selectors)

  // OR explicit selectors (same as tagging/scoring endpoints):
  "image_ids":    [123, 456],
  "image_paths":  ["D:/Photos/img.nef"],
  "folder_ids":   [7],
  "folder_paths": ["D:/Photos/Birds"],
  "recursive":    true,

  // Classification options:
  "candidate_species": null,  // null → use bundled NA list; or ["Mallard", "Canada Goose"]
  "threshold":  0.1,          // minimum softmax probability to store a prediction
  "top_k":      1,            // max species to store per image (1 = BioCLIP argmax)
  "overwrite":  false         // re-classify images that already have species: keywords
}
```

**Response:**

```jsonc
{
  "success": true,
  "message": "Bird species classification job queued",
  "data": {
    "job_id":        42,
    "input_path":    "D:/Photos/2024",
    "resolved_count": null,     // non-null when explicit selectors were used
    "queue_position": 1
  }
}
```

---

### `GET /api/bird-species/status`

```jsonc
{
  "is_running":     true,
  "status_message": "Running...",
  "current":        47,
  "total":          120,
  "log":            "Starting bird species classification on D:/Photos...\n...",
  "job_type":       "bird_species"
}
```

---

### `POST /api/bird-species/stop`

Send a stop signal. The runner finishes the current image and then exits cleanly.

```jsonc
{ "success": true, "message": "Stop signal sent to bird species runner", "data": { "is_running": true } }
```

---

## 7. Querying results

Species keywords follow the `species:` prefix convention. Any existing keyword filter works:

**MCP tool:**
```
execute_sql("SELECT kd.keyword_norm, COUNT(*) cnt
             FROM image_keywords ik
             JOIN keywords_dim kd ON ik.keyword_id = kd.keyword_id
             WHERE kd.keyword_norm LIKE 'species:%'
             GROUP BY kd.keyword_norm
             ORDER BY cnt DESC
             FETCH FIRST 20 ROWS ONLY")
```

**REST gallery filter:**
```
GET /api/images?keyword=species%3AAmerican+Robin&sort_by=score&order=desc
```

**MCP query_images:**
```
query_images(keyword="species:Mallard", min_score=0.6)
```

---

## 7a. MCP tool usage

The MCP server (`modules/mcp_server.py`) exposes bird species classification directly as a tool call — useful for AI agent workflows.

### Trigger a job

```python
run_processing_job(
    job_type="bird_species",
    input_path="D:/Photos/2024",
    args={
        "threshold": 0.15,   # optional — default 0.1
        "top_k": 2,          # optional — default 1
        "overwrite": False,  # optional — default False
        # "candidate_species": ["Bald Eagle", "Osprey"]  # optional
    }
)
# → {"status": "Started", "job_id": "mcp_bird_species_a1b2c3d4"}
```

If the runner is already busy the tool returns `{"error": "Bird species job already running"}` without queuing a second job.

### Poll runner status

`get_runner_status()` includes a `bird_species` key alongside `scoring`, `tagging`, `clustering`, and `selection`:

```python
status = get_runner_status()
bs = status["bird_species"]
# {
#   "available": true,
#   "is_running": true,
#   "status_message": "Running...",
#   "progress": {"current": 47, "total": 120},
#   "recent_log": "Starting bird species classification...\nLoading BioCLIP 2 model..."
# }
```

`available: false` means the runner was not wired into the MCP server at startup (check that `ENABLE_MCP_SERVER=1` is set and the server started alongside the WebUI).

---

## 8. Installation

BioCLIP 2 requires `open_clip_torch`. It is **not** in the default requirements (optional ML dependency):

```bash
pip install open_clip_torch
```

The runner will log a clear error (`open_clip not installed`) if the package is missing and the job is submitted. No crash, no silent failure — the job is marked `failed` in the queue.

---

## 9. Usage examples

### Classify all bird images in a folder

```bash
curl -X POST http://127.0.0.1:7860/api/bird-species/start \
  -H "Content-Type: application/json" \
  -d '{"input_path": "D:/Photos/2024"}'
```

### Target a specific short species list (improves accuracy)

Restricting the candidate list to likely species improves both speed and accuracy (smaller softmax denominator, fewer look-alike confusions):

```bash
curl -X POST http://127.0.0.1:7860/api/bird-species/start \
  -H "Content-Type: application/json" \
  -d '{
    "input_path": "D:/Photos/Raptors",
    "candidate_species": ["Bald Eagle", "Golden Eagle", "Osprey", "Red-tailed Hawk",
                          "Cooper'\''s Hawk", "Sharp-shinned Hawk", "Peregrine Falcon",
                          "American Kestrel", "Merlin"],
    "threshold": 0.05,
    "top_k": 2
  }'
```

### Re-classify with updated model or list

```bash
curl -X POST http://127.0.0.1:7860/api/bird-species/start \
  -H "Content-Type: application/json" \
  -d '{"input_path": "D:/Photos/2024", "overwrite": true}'
```

### Classify specific images by ID

```bash
curl -X POST http://127.0.0.1:7860/api/bird-species/start \
  -H "Content-Type: application/json" \
  -d '{"image_ids": [1042, 1043, 1047]}'
```

---

## 10. Tuning guidance

| Situation | Recommendation |
|-----------|---------------|
| High false positives (wrong species) | `top_k` is already 1 (argmax); raise `threshold` to 0.3–0.5 |
| Want multiple candidates per image | Raise `top_k` (e.g. 3) to store the next-best species too |
| Missing predictions (nothing above threshold) | Lower `threshold` to 0.05; check the image has a visible bird |
| Slow on CPU | Run on GPU (set `CUDA_VISIBLE_DEVICES=0`); or reduce `candidate_species` list size |
| Regional shooting (e.g. Pacific Northwest only) | Pass a short `candidate_species` list of ~30 likely local species — dramatically improves accuracy |
| Scientific name output wanted | Post-process `species:Common Name` → scientific via a lookup table; do not change prompts (scientific names hurt CLIP accuracy) |
| RAW files | Automatically handled — the runner uses thumbnails for RAW formats (NEF, ARW, CR2, etc.) |

---

## 11. File map

| File | Role |
|------|------|
| [`modules/bird_species.py`](../../modules/bird_species.py) | `BioCLIPClassifier` + `BirdSpeciesRunner` + module helpers |
| [`data/bird_species_list.txt`](../../data/bird_species_list.txt) | Default bundled (~360) North American species list |
| [`modules/db_legacy.py`](../../modules/db_legacy.py) | `get_images_with_keyword()` — SQL filter; post-filters large ID lists in Python |
| [`modules/job_dispatcher.py`](../../modules/job_dispatcher.py) | Routes `job_type="bird_species"` to `BirdSpeciesRunner` |
| [`modules/api.py`](../../modules/api.py) | `BirdSpeciesStartRequest`; `/bird-species/start`, `/stop`, `/status`; `submit_run` routing |
| [`modules/mcp_server.py`](../../modules/mcp_server.py) | `run_processing_job("bird_species")` + `get_runner_status()["bird_species"]` |
| [`modules/ui/app.py`](../../modules/ui/app.py) | Instantiates `BirdSpeciesRunner`; wires it into API and MCP server |
| [`webui.py`](../../webui.py) | Forwards `BirdSpeciesRunner` to `mcp_server.set_runners()` at startup |
| [`frontend/src/types/api.ts`](../../frontend/src/types/api.ts) | `StageCode` union + `STAGE_DISPLAY` entry for `bird_species` |
| [`frontend/src/components/scope/ScopeSelector.tsx`](../../frontend/src/components/scope/ScopeSelector.tsx) | `ALL_STAGES` list — `"bird_species"` appears after `"keywords"` |
| [`tests/test_bird_species.py`](../../tests/test_bird_species.py) | 14 unit tests (12 non-ML): state machine, chunking, dispatcher routing, cache behavior |

---

## 12. Automated tests (local)

Quick run (skips `@pytest.mark.ml`; set `SKIP_TEST_DB_SETUP=1` if you do not want `scripts/setup_test_db.py` to run — e.g. no Firebird test DB):

```bash
SKIP_TEST_DB_SETUP=1 pytest tests/test_bird_species.py -v -m "not ml"
```

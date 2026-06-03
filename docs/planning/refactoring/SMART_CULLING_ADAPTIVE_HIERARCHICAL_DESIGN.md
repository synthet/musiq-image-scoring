# Smart Culling: Adaptive Hierarchical Clustering Design

> **Status:** Proposed design (not implemented). Ingested 2026-05-23 from smart_culling_adaptive_hierarchical_design.md.
> **See also:** [AUTO_CULLING_ALGORITHMS_RESEARCH_2026-05-23.md](../../reports/AUTO_CULLING_ALGORITHMS_RESEARCH_2026-05-23.md) (industry landscape), [STACK_CULLING_REFACTOR_PLAN.md](STACK_CULLING_REFACTOR_PLAN.md), [CULLING_FEATURE.md](../../technical/CULLING_FEATURE.md), [04-clustering-culling-stacks.md](../../features/implemented/04-clustering-culling-stacks.md), [AGENT_COORDINATION.md](../../technical/AGENT_COORDINATION.md), [EMBEDDING_APP_06_SMART_STACK_REPRESENTATIVE.md](../../features/planned/embeddings/EMBEDDING_APP_06_SMART_STACK_REPRESENTATIVE.md).
> Open questions in this doc remain authoritative until a backlog issue is filed.

---


## Goal

Implement **adaptive hierarchical smart culling** for Vexlum Scoring / Driftara Gallery.

Instead of using a single global similarity threshold, dynamically adjust clustering thresholds based on image-set heuristics, then perform two-level decomposition:

```text
Folder / Job
  → Level 1 clusters: scene / subject / burst groups
      → Level 2 clusters: near-duplicates / pose variants / micro-bursts
          → pick / alternate / variant / reject / manual_review
```

The core principle:

> Cluster primarily by visual/time/metadata similarity. Use scores mainly to choose winners inside clusters.

---

## Why this matters

Wildlife photography often contains sequences where many frames are visually similar but not equivalent.

Examples:

- Same bird, same perch, different head angles
- Same subject, wings up versus wings down
- Same action sequence, different behavior moments
- Same scene, changing light or distance
- Technically weaker image with more interesting behavior

A flat threshold can either:

- merge too much and reject meaningful variants, or
- split too much and fail to reduce duplicates.

Adaptive hierarchical culling should preserve important diversity while aggressively reducing obvious duplicates.

---

## Confirmed project assumptions

- Backend/scoring repo: `image-scoring-backend`
- Gallery repo: `image-scoring-gallery`
- Product names:
  - Backend/scoring: Vexlum Scoring
  - Desktop gallery: Driftara Gallery
- Current DB architecture: PostgreSQL + pgvector
- Firebird is legacy/decommissioned except for old compatibility references
- Current embedding architecture: MobileNetV2-style 1280-dimensional vectors stored in pgvector
- Canonical backend docs should remain authoritative for API/schema/pipeline terminology:
  - `docs/CANONICAL_SOURCES.md`
  - `docs/technical/API_CONTRACT.md`
  - `docs/reference/api/openapi.yaml`
  - `docs/technical/PIPELINE_TERMINOLOGY.md`
  - `docs/technical/DB_SCHEMA.md`
  - `docs/technical/AGENT_COORDINATION.md`

---

## MVP concept

### Phase 1 — Level 1 scene clustering

Use existing embeddings and metadata to create broad scene/subject/burst clusters.

Inputs:

- embedding vector
- capture timestamp
- file name / file sequence
- folder/job id
- focal length
- camera/lens
- aperture
- shutter speed
- ISO
- exposure compensation
- existing scores

Output:

- Level 1 clusters representing likely same scene, same subject, or same shooting opportunity.

Recommended implementation:

```text
pgvector nearest-neighbor search
  → build kNN graph
  → add edges above adaptive Level 1 threshold
  → connected components become Level 1 clusters
```

---

### Phase 2 — Level 2 near-duplicate clustering

Inside each Level 1 cluster, perform stricter decomposition.

Output should separate:

- same pose / true duplicates
- pose variants
- action variants
- distance/crop variants
- lighting/exposure variants

Recommended implementation:

```text
For each Level 1 cluster:
  if cluster is small and internally coherent:
      run strict connected-components split
  if cluster is large or internally mixed:
      recursively tighten threshold until decomposition is reasonable
```

---

### Phase 3 — Pick / alternate / reject decisions

Inside each Level 2 cluster:

- rank images using weighted score signals
- pick the best candidate
- keep close alternatives
- preserve meaningful variants
- reject only high-confidence worse duplicates

Default conservative rule:

```text
Auto-reject only when:
  similarity >= 0.94
  score delta >= 5
  technical delta >= 4
  timestamp gap <= 10 sec
  no distinct-pose / behavior / composition signal
```

Everything else should be:

```text
alternate
variant
manual_review
```

---

## Similarity channels

Do not rely on embedding similarity alone.

Suggested channels:

```text
visual_similarity     = cosine similarity of embedding
time_similarity       = normalized capture-time proximity
exposure_similarity   = normalized EXIF exposure similarity
focal_similarity      = focal length / lens similarity
score_similarity      = similarity of model score profile
metadata_similarity   = camera / dimensions / orientation / folder context
```

Example weighted similarity:

```text
combined_similarity =
    0.65 * visual_similarity
  + 0.15 * time_similarity
  + 0.10 * exposure_similarity
  + 0.05 * focal_similarity
  + 0.05 * score_similarity
```

Important: score similarity should be weak. Scores should not dominate clustering.

---

## Adaptive thresholding

### Level 1 threshold

Level 1 should be tolerant enough to group a photographic opportunity.

Typical range:

```text
0.74–0.90
```

Starting point:

```text
0.82
```

Heuristics:

Lower threshold when:

- capture times are very close
- same camera/lens/focal length
- exposure settings are similar
- filename sequence is continuous
- folder/job is known to be a burst import

Raise threshold when:

- timestamps are far apart
- focal length changes significantly
- GPS differs significantly
- exposure changes strongly
- preliminary clusters become too large
- local embedding density is very high

Pseudo-code:

```python
def level1_threshold(group_stats):
    threshold = 0.82

    if group_stats.median_time_gap_seconds < 3:
        threshold -= 0.04

    if group_stats.exposure_std_low:
        threshold -= 0.02

    if group_stats.focal_length_std_low:
        threshold -= 0.01

    if group_stats.cluster_size_estimate > 80:
        threshold += 0.04

    if group_stats.scene_density_high:
        threshold += 0.03

    return clamp(threshold, 0.74, 0.90)
```

---

### Level 2 threshold

Level 2 should be stricter and separate near-duplicates from meaningful variants.

Typical range:

```text
0.86–0.97
```

Starting point:

```text
0.91
```

Heuristics:

Lower threshold when:

- frames are from a tight burst
- score spread is high and direct comparison is useful
- parent cluster is visually consistent

Raise threshold when:

- parent cluster is large
- pose/action variation appears high
- image count is high
- embeddings show multiple local modes

Pseudo-code:

```python
def level2_threshold(parent_cluster):
    threshold = 0.91

    if parent_cluster.score_spread_high:
        threshold -= 0.02

    if parent_cluster.pose_variation_high:
        threshold += 0.02

    if parent_cluster.parent_size > 50:
        threshold += 0.03

    if parent_cluster.capture_burst_tight:
        threshold -= 0.01

    return clamp(threshold, 0.86, 0.97)
```

---

## Cluster quality metrics

Compute these for explainability and diagnostics.

### Cluster-level metrics

```text
image_count
score_min
score_max
score_mean
score_median
score_std
technical_score_mean
aesthetic_score_mean
best_image_id
worst_image_id
time_span_seconds
median_time_gap_seconds
embedding_similarity_min
embedding_similarity_mean
embedding_similarity_std
exposure_similarity_mean
focal_length_min
focal_length_max
rating_distribution
label_distribution
keyword_overlap
gps_spread
```

### Decision metrics

```text
pick_count
alternate_count
variant_count
reject_count
manual_review_count
best_score_margin
cluster_confidence
decomposition_depth
threshold_used
algorithm_used
```

Example explanation:

```text
Rejected because it is a near-duplicate of image 123, has 0.96 visual similarity, is 7.4 points lower in technical score, and has the same pose within a 2-second burst.
```

---

## Selection score

Inside Level 2 clusters, rank images using a culling-specific selection score.

Initial formula:

```text
selection_score =
    0.35 * score_general
  + 0.25 * score_technical
  + 0.20 * score_aesthetic
  + 0.10 * sharpness_or_blur_signal
  + 0.05 * subject_eye_confidence
  + 0.05 * user_rating_bonus
```

For wildlife, bias toward:

- technical quality
- eye/face sharpness
- subject size
- pose/behavior strength
- background cleanliness
- absence of obstruction

Do not blindly reject lower-scored images when they contain distinct behavior.

---

## Decision classification

Pseudo-code:

```python
def classify_cluster_members(images):
    ranked = sorted(images, key=lambda x: x.selection_score, reverse=True)

    best = ranked[0]
    result = {best.id: "pick"}

    for image in ranked[1:]:
        delta = best.selection_score - image.selection_score

        if delta <= 2.0:
            result[image.id] = "alternate"
        elif delta <= 6.0 and image.pose_is_distinct:
            result[image.id] = "variant"
        elif is_high_confidence_duplicate(best, image):
            result[image.id] = "reject"
        else:
            result[image.id] = "manual_review"

    return result
```

High-confidence duplicate rule:

```python
def is_high_confidence_duplicate(best, image):
    return (
        image.similarity_to_best >= 0.94
        and best.selection_score - image.selection_score >= 5
        and best.score_technical - image.score_technical >= 4
        and abs(best.capture_time - image.capture_time).total_seconds() <= 10
        and not image.pose_is_distinct
    )
```

---

## Database design

Do not overload the `images` table with culling run state.

Use separate tables so multiple culling experiments can coexist.

### `culling_runs`

```sql
create table culling_runs (
    id serial primary key,
    job_id integer references jobs(id) on delete set null,
    folder_id integer references folders(id) on delete set null,
    algorithm_version varchar(50) not null,
    parameters_json jsonb,
    created_at timestamptz default now()
);
```

### `image_clusters`

```sql
create table image_clusters (
    id serial primary key,
    run_id integer not null references culling_runs(id) on delete cascade,
    parent_cluster_id integer references image_clusters(id) on delete cascade,
    level smallint not null,
    cluster_type varchar(50),
    threshold_used double precision,
    algorithm varchar(100),
    image_count integer,
    best_image_id integer references images(id) on delete set null,
    metrics_json jsonb,
    created_at timestamptz default now()
);
```

Suggested `cluster_type` values:

```text
scene
near_duplicate
variant
manual
```

### `image_cluster_members`

```sql
create table image_cluster_members (
    cluster_id integer not null references image_clusters(id) on delete cascade,
    image_id integer not null references images(id) on delete cascade,
    similarity_to_centroid double precision,
    rank_in_cluster integer,
    decision varchar(50),
    decision_score double precision,
    decision_reason text,
    metrics_json jsonb,
    primary key (cluster_id, image_id)
);
```

Suggested `decision` values:

```text
pick
alternate
variant
reject
manual_review
```

Potential indexes:

```sql
create index idx_culling_runs_folder_id on culling_runs(folder_id);
create index idx_image_clusters_run_id on image_clusters(run_id);
create index idx_image_clusters_parent_cluster_id on image_clusters(parent_cluster_id);
create index idx_image_cluster_members_image_id on image_cluster_members(image_id);
create index idx_image_cluster_members_decision on image_cluster_members(decision);
```

---

## Backend implementation shape

Suggested module layout:

```text
modules/culling/
  __init__.py
  config.py
  models.py
  features.py
  similarity.py
  thresholds.py
  graph.py
  clustering.py
  hierarchy.py
  scoring.py
  decisions.py
  persistence.py
  explain.py
```

Pipeline:

```python
def run_smart_culling(folder_id: int, config: SmartCullingConfig):
    images = load_images_with_embeddings(folder_id)

    features = build_culling_features(images)

    level1_clusters = cluster_level1(features, config)

    all_results = []

    for cluster in level1_clusters:
        subclusters = cluster_level2(cluster, config)
        decisions = classify_subclusters(subclusters, config)
        all_results.append((cluster, subclusters, decisions))

    run_id = persist_culling_run(all_results, config)

    return run_id
```

---

## API surface proposal

Backend contract should be updated first.

Canonical docs to update:

- `docs/technical/API_CONTRACT.md`
- `docs/reference/api/openapi.yaml`
- `docs/technical/DB_SCHEMA.md`
- `docs/CANONICAL_SOURCES.md` if this becomes a canonical feature area

Possible endpoints:

```text
POST /api/culling/runs
GET  /api/culling/runs/{run_id}
GET  /api/culling/runs/{run_id}/clusters
GET  /api/culling/clusters/{cluster_id}/images
POST /api/culling/runs/{run_id}/apply
POST /api/culling/decisions/override
```

Important: endpoint names must be aligned with existing backend API conventions before implementation.

---

## Gallery integration

Driftara Gallery should consume culling data through backend API or Electron main-process IPC/provider boundaries.

Do not access PostgreSQL directly from the renderer process.

Suggested UI:

```text
Smart Culling Run
  - cluster tree
  - scene clusters
  - near-duplicate groups
  - best image highlighted
  - rejected images dimmed
  - threshold used
  - confidence
  - decision reason
```

Useful actions:

```text
Accept all high-confidence rejects
Review low-confidence clusters
Compare cluster members side-by-side
Promote alternate to pick
Demote pick to alternate
Mark all lower-ranked duplicates as reject
Show only cluster heroes
Show variants
Undo culling run
```

Apply should be explicit and reversible where possible.

---

## Safety rules

Smart culling must be conservative by default.

Avoid destructive over-rejection.

Default behavior:

- auto-pick one best image per near-duplicate group
- auto-reject only obvious worse duplicates
- preserve close alternatives
- preserve behavior/action variants
- flag ambiguous groups for manual review

Never permanently delete files as part of MVP.

If applying decisions to existing `images.rating`, `images.label`, or future pick/reject fields, store the culling run and decision provenance.

---

## Testing strategy

### Backend tests

Add unit tests for:

- threshold adjustment logic
- combined similarity calculation
- connected-component graph clustering
- recursive split behavior
- decision classification
- explanation generation
- persistence and retrieval

Recommended fast local command:

```bash
python -m pytest -m "not gpu and not db and not ml and not firebird" --ignore=tests/test_probe.py
```

For DB-backed tests, add targeted tests around:

- culling run creation
- cluster/member persistence
- cascade deletion
- retrieving cluster hierarchy
- applying decisions safely

### Gallery tests/checks

Recommended commands:

```bash
npx tsc --noEmit
npx tsc -p electron/tsconfig.json --noEmit
npm run lint
```

Add UI/provider tests for:

- loading culling runs
- rendering cluster hierarchy
- filtering by decision
- displaying decision reasons
- overriding pick/reject decisions

---

## Diagnostics

For backend troubleshooting, start with:

```bash
source ~/.venvs/tf/bin/activate
python scripts/doctor.py
python scripts/doctor.py --no-gpu
python scripts/doctor.py --json
```

`doctor.py` should help verify config, DB connectivity, simple query ping, pgvector, and optionally CUDA/GPU.

For support bundles:

```bash
source ~/.venvs/tf/bin/activate
python scripts/export_debug_bundle.py
```

Bundles are expected to be redacted and exclude `secrets.json`, but should still be reviewed before sharing.

For gallery troubleshooting:

```bash
npm run doctor
npm run dev
```

Also check backend `webui.lock`, `config.json`, and API URL/port discovery.

---

## Open design questions

1. Should culling decisions write back to existing `images.label` / `images.rating`, or stay separate until explicitly applied?
2. Is there already a pick/reject field, or should one be introduced?
3. Should culling operate by `folder_id`, `job_id`, arbitrary selection, or all three?
4. Should Level 1 clusters map to existing `stacks`, or should culling clusters remain separate?
5. Should user overrides become durable training/feedback signals for future culling runs?
6. Should culling run parameters be versioned as JSON only, or as a typed config table?
7. What should be the confidence threshold for fully automatic rejection?

---

## Recommended implementation order

1. Confirm canonical backend schema around `images`, `image_embeddings`, `stacks`, ratings, labels, and existing score fields.
2. Add culling DB tables via Alembic migration.
3. Implement feature extraction and similarity helpers.
4. Implement adaptive threshold functions.
5. Implement kNN graph + connected component clustering.
6. Implement Level 2 recursive decomposition.
7. Implement pick/alternate/variant/reject decision logic.
8. Persist culling runs and explanations.
9. Add read-only API endpoints.
10. Add gallery read-only review UI.
11. Add explicit apply/override operations.
12. Update docs and tests.

---

## Agent prompt draft

Use this prompt for an implementation agent:

```text
Implement Smart Culling v1 for the Vexlum Scoring / Driftara Gallery ecosystem.

Goal:
Create an adaptive hierarchical culling system that groups images by visual/time/metadata similarity, decomposes broad scene clusters into stricter near-duplicate/variant clusters, and assigns conservative pick/alternate/variant/reject/manual_review decisions using existing image quality scores.

Repository assumptions:
- Backend repo: image-scoring-backend
- Gallery repo: image-scoring-gallery
- PostgreSQL + pgvector is primary
- Firebird is legacy/decommissioned
- Embeddings are MobileNetV2-style 1280-dimensional vectors stored in pgvector

Backend canonical sources to check before coding:
- docs/CANONICAL_SOURCES.md
- docs/technical/API_CONTRACT.md
- docs/reference/api/openapi.yaml
- docs/technical/PIPELINE_TERMINOLOGY.md
- docs/technical/DB_SCHEMA.md
- docs/technical/AGENT_COORDINATION.md

Required backend work:
1. Inspect existing schema for images, scores, embeddings, stacks, labels, and ratings.
2. Add Alembic migration for:
   - culling_runs
   - image_clusters
   - image_cluster_members
3. Implement modules/culling/ with:
   - config.py
   - features.py
   - similarity.py
   - thresholds.py
   - graph.py
   - clustering.py
   - hierarchy.py
   - scoring.py
   - decisions.py
   - persistence.py
   - explain.py
4. Use pgvector nearest-neighbor search to build a kNN graph per folder/job/selection.
5. Use adaptive Level 1 thresholding for broad scene clusters.
6. Use stricter Level 2 thresholding inside each scene cluster.
7. Recursively split oversized or internally inconsistent clusters.
8. Rank images inside Level 2 clusters using existing scores plus optional technical heuristics.
9. Assign decisions conservatively:
   - pick
   - alternate
   - variant
   - reject
   - manual_review
10. Auto-reject only high-confidence worse duplicates.
11. Persist metrics and decision explanations.
12. Add read-only API endpoints first.
13. Add apply/override endpoints only after read-only review works.
14. Update backend docs and OpenAPI contract.
15. Add unit tests for thresholds, similarity, clustering, decisions, explanations, and persistence.

Required gallery work:
1. Do not access DB from renderer.
2. Add API/provider support through existing backend API or Electron main-process IPC/provider boundary.
3. Add Smart Culling Run review UI:
   - cluster tree
   - scene clusters
   - near-duplicate groups
   - decision badges
   - best image highlight
   - rejected image dimming
   - explanation display
4. Add filters:
   - picks
   - alternates
   - variants
   - rejects
   - manual review
5. Add manual override actions after backend override endpoint exists.
6. Run TypeScript and lint checks.

Safety:
- Do not delete files.
- Do not permanently apply rejects without explicit user action.
- Preserve meaningful variants.
- Store provenance for every decision.
- Keep culling runs reproducible through algorithm_version and parameters_json.

Backend checks:
source ~/.venvs/tf/bin/activate
python scripts/doctor.py
python scripts/doctor.py --no-gpu
python scripts/doctor.py --json
python -m pytest -m "not gpu and not db and not ml and not firebird" --ignore=tests/test_probe.py

Gallery checks:
npm run doctor
npm run dev
npx tsc --noEmit
npx tsc -p electron/tsconfig.json --noEmit
npm run lint
```


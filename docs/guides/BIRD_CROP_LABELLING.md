---
type: Runbook
title: Bird-crop study — human labelling runbook
description: How to fill the 236-row within-burst verdict set that unblocks the bird-bbox crop study's only non-circular ground truth.
resource: docs/guides/BIRD_CROP_LABELLING.md
tags: [research, labelling, bird-detection, culling, ground-truth, runbook]
timestamp: 2026-08-01T00:00:00Z
okf_version: 0.1
---

# Bird-crop study — human labelling runbook

**What you are doing:** for each of 54 photo bursts, marking which frame(s) you would keep. It is a side-by-side comparison inside each burst, not absolute scoring.

**Why it matters:** this is the study's *only* non-circular quality ground truth. Everything the database offers — `rating`, `label`, `pick_status`, `cull_decision` — is computed by the scoring pipeline from the very models under test, so measuring a new signal against those columns rewards agreement with the incumbent rather than accuracy. Until this file is filled, the bird-bbox crop study can make **no accuracy claim at all** ([close-out memo](../reports/BIRD_BBOX_CROP_STUDY_2026-08-01.md), issue [#317](https://github.com/synthet/image-scoring-backend/issues/317)).

**Effort:** 236 frames across 54 bursts. Most bursts are small — 21 have only 3 frames.

---

## 1. The files

| Path | What it is |
|---|---|
| `reports/bird-crop/labels/label_set.csv` | **The file you edit.** 236 rows, one per frame; you fill the `verdict` column. |
| `reports/bird-crop/labels/sheets/` | **What you look at.** 54 JPEG contact sheets, one per burst. |
| `reports/bird-crop/labels/label_set_provenance.json` | How the sample was drawn (seed `20260729`, 18 bursts per subject-size tercile, burst sizes 3–8, 2.0 s gap). Read-only. |
| [`scripts/research/bird_crop/labels.py`](../../scripts/research/bird_crop/labels.py) | CSV contract and validation rules. |
| [`scripts/research/bird_crop/build_label_set.py`](../../scripts/research/bird_crop/build_label_set.py) | Generated the CSV and the sheets. **Do not re-run** — it would resample and discard your work (it refuses if verdicts exist). |

### CSV columns

```
image_id,burst_id,area_frac_tercile,frame_index,verdict
8994,98,1,1,
8995,98,1,2,
8996,98,1,3,
```

| Column | Meaning | Edit? |
|---|---|---|
| `image_id` | Production `images.id` — the only join key | **No** |
| `burst_id` | Study-local burst id; matches the sheet filename | **No** |
| `area_frac_tercile` | 1 = smallest subjects … 3 = largest | **No** |
| `frame_index` | Position within the burst, 1-based; matches the `#N` on the sheet | **No** |
| `verdict` | `best` \| `good` \| `reject` | **Yes — this is your job** |

No file paths are stored in the CSV by design; everything resolves from `image_id`.

### Reading a contact sheet

Filename: `burst00098_t1-<uuid>.jpg` → `burst_id` **98**, subject-size tercile **1**, with a real random UUID in each produced Filename (work copies under the label/score harness use `burst{id:d5}_t{tercile}-{guid}.jpg`).

### Provenance (agent-derived labels)

When verdicts are filled by the skills-repo multi-agent harness (`/bird-crop-label`), they are **not** human ground truth. Expect a UUID-stamped `reports/bird-crop/labels/label_set_judges-<uuid>.json` sidecar with `ground_truth_kind: agent-derived`, the judge list, and per-image votes. Qualify any “non-circular” claim in study reports accordingly — these judges are vision LLMs, not the scoring pipeline under test, but they are still model-derived.

Each sheet is a 4-column grid of **bbox crops, not full frames** — deliberately, because a 200 px thumbnail of an 8256 px frame shows a ~50 px bird and would leave you as unable to judge sharpness as the full-frame model under test. Crops carry 25% padding so you can still see pose and clipping. Cells are 420 px.

Each cell is captioned:

```
#3 id=8996 area=11.4% conf=0.92
```

- `#3` → `frame_index` 3 (matches the CSV row)
- `id=8996` → `image_id` (the CSV join key)
- `area=` → how much of the frame the bird occupies
- `conf=` → detector confidence

Within a 2-second burst the composition barely changes, so **sharpness and pose are what actually vary** — which is exactly what the crop shows.

---

## 2. The three verdicts

Defined at [`labels.py:44`](../../scripts/research/bird_crop/labels.py). Ordered worst → best for ranking metrics (`reject` 0, `good` 1, `best` 2).

| Value | Meaning |
|---|---|
| `best` | **Would keep this one** — the pick |
| `good` | Acceptable, but not the pick |
| `reject` | Would delete |

Case-insensitive and whitespace-trimmed. Anything else fails validation with the offending line number.

### How to judge

Work **one burst at a time** and rank frames **against each other**, not against your general sense of a good photo. Comparative judgement inside a burst is far more reliable than absolute scoring, and it is exactly what culling needs.

For a typical 3-frame burst the natural shape is one `best` and two `good`/`reject`.

Don't agonise over `good` vs `reject` — the metric that matters most is which frame you would *pick*. That split mainly separates "acceptable alternates" from "would delete".

---

## 3. Two rules the validator enforces

Both are checked by `labels.load(require_complete=True)`, so a half-filled sheet fails loudly rather than silently shrinking the evaluation set.

1. **Every row needs a verdict.** No blanks.
2. **Every burst needs at least one `best`.** Otherwise top-1 accuracy is undefined for that burst. If an entire burst is unusable, still mark the least-bad frame `best` and `reject` the rest — never leave a burst without a keeper.

**Ties are fine.** Multiple `best` frames in one burst is allowed; top-1 metrics count a hit if the model picks any of them. It logs a note, not an error.

---

## 4. Action items

### Step 1 — label

Open `reports/bird-crop/labels/label_set.csv` in a spreadsheet or text editor, keep `reports/bird-crop/labels/sheets/` open beside it, and go burst by burst in `burst_id` order.

> **If you use Excel:** save back as **CSV UTF-8**, keep the header row, and do not let it reformat `image_id` into scientific notation. A plain text editor avoids both risks.

### Step 2 — check progress at any time

```powershell
python -c "import csv; r=list(csv.DictReader(open('reports/bird-crop/labels/label_set.csv'))); d=[x for x in r if x['verdict'].strip()]; print(f'{len(d)}/{len(r)} rows labelled')"
```

### Step 3 — validate before running anything

In WSL with the app venv:

```bash
cd /mnt/d/Projects/image-scoring-backend
source ~/.venvs/tf/bin/activate
python -c "
from scripts.research.bird_crop import labels
rows = labels.load()
print(f'OK: {len(rows)} rows, {len(labels.best_ids(rows))} bursts with a best frame')
"
```

Success prints `OK: 236 rows, 54 bursts with a best frame`. Any failure names the exact line or burst to fix.

### Step 4 — re-run the geometry phase

`geometry_eval` picks the labels up automatically once they validate ([`labels.py:176`](../../scripts/research/bird_crop/labels.py), `try_load`). Production is on the WSL host gateway, so pass `PROD_HOST`:

```bash
cd /mnt/d/Projects/image-scoring-backend
PROD_HOST=172.22.144.1 POSTGRES_HOST=172.22.144.1 \
  bash scripts/research/bird_crop/run_bird_crop_study.sh PHASE=1
```

Confirm the gateway first if WSL has restarted: `ip route show default`.

This is **CPU-only and takes about 30 seconds** — no GPU, no re-sweep. It refreshes `reports/bird-crop/geometry.{json,md}` and `reports/bird-crop/REPORT.md`.

### Step 5 — confirm the verdict flipped

```bash
sed -n '5,14p' reports/bird-crop/REPORT.md
```

The **Bbox geometry** row should change from `not yet measured` to a real verdict, and `geometry.md`'s "Predictive value against human labels" section should replace *"Not yet available"* with measured numbers.

---

## 5. What this unblocks

| Consequence | Detail |
|---|---|
| **Bbox geometry gets a verdict** | Currently the only phase with no answer. The bias probe (frame-edge contact: mean score 0.5969 clipped vs 0.6828 not) is against pipeline-derived columns and proves nothing about accuracy. |
| **First non-circular check on species and captions** | Both currently carry `derived` ground truth — they measure agreement with the incumbent stack, not correctness. |
| **Validates the whole pinned population** | The 236 pinned image ids *are* the label set, so these verdicts apply to every track: embeddings, IQA, captions, species, degradation. |

The IQA result (crop is **2.42×–17.51×** more sensitive to subject-only degradation) already stands on constructed ground truth and does **not** depend on this labelling.

---

## 6. Cautions

- **Never re-run `build_label_set.py`.** It resamples with a fresh seed and would invalidate both your work and the 236-id pin every other track shares. It refuses to clobber existing verdicts, but do not rely on that.
- **Don't edit any column but `verdict`,** and don't add, remove, or reorder rows. `image_id` is the join key to production and to `reports/bird-crop/study_image_ids.txt`.
- **Don't renumber `burst_id` or `frame_index`** — the sheets are keyed to them.
- Labelling is read-only with respect to production; nothing here writes to the database.

## Related

- [Close-out memo](../reports/BIRD_BBOX_CROP_STUDY_2026-08-01.md) — full results for all five phases
- [`reports/bird-crop/REPORT.md`](../../reports/bird-crop/REPORT.md) — generated consolidated report
- Issue [#317](https://github.com/synthet/image-scoring-backend/issues/317) — tracking card

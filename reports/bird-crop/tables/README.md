# Bird-crop study — machine-readable result tables

Tidy CSV exports of the study's result JSONs: one row per measurement, every
identifying column spelled out, so a spreadsheet can pivot without parsing nested
JSON. The markdown reports alongside them (`../REPORT.md`, `../focus.md`,
`../degradation.md`, `../species_crop.md`) are written to be *read*; these are
written to be *sorted, filtered and joined*.

Regenerate after any phase re-runs:

```bash
source ~/.venvs/tf/bin/activate
python -m scripts.research.bird_crop.export_results          # CSV (these files)
python -m scripts.research.bird_crop.export_results --tsv    # tab-separated instead
```

The exporter skips missing phases with a warning rather than failing, so a
partial run is fine.

## Files

| File | Rows | What it holds |
|---|---|---|
| `degradation_sensitivity.csv` | model × degradation | **The headline table.** Crop vs full-frame sensitivity to *subject-only* degradation, with the `crop_sensitivity_ratio` that carries the study's main finding. Constructed ground truth. |
| `degradation_cells.csv` | model × degradation × region × scored-on | Every measured cell behind the aggregate above, so it can be audited or re-derived. Includes the whole-frame control arm. |
| `focus_arm_a_auc.csv` | measure × source | Phase 4: how well each zero-inference focus measure predicts AF-vs-bird disagreement, on the crop and on the full frame. |
| `focus_arm_b_rule.csv` | 1 (the rule) | Phase 4 Arm B: the proposed *soft crop ∧ AF centre outside the box* rule scored against within-burst verdicts, with its confusion counts. Absent when the rule was never scored. |
| `focus_af_coverage.csv` | camera | How many images per camera body carry AF region geometry and focus distance. |
| `species_crop_vs_whole.csv` | subject-size tercile + overall | BioCLIP within-burst agreement and confidence, crop vs whole image. |
| `phase2_eval_runs.csv` | run | Embedding and caption sweep runs — burst pair-margin, clustering ARI, caption uniqueness. |

## Reading the important columns

- **`crop_sensitivity_ratio`** (`degradation_sensitivity.csv`) — how much more the
  crop score falls than the full-frame score when *only the subject* is degraded.
  `> 1` supports the study's premise; `~1` would refute it. Effect size is measured
  with the relative drop, not Spearman: Spearman saturates at −1.0 in nearly every
  cell and so cannot separate "noticed slightly" from "noticed a lot".
- **`auc_vs_af_disagreement`** (`focus_arm_a_auc.csv`) — 0.5 is chance.
  **Read `tracks_blur` first.** A measure that does not fall when detail is
  destroyed cannot support a claim about focus however well it separates the
  groups; `local_entropy` scores highest here and is exactly that case.
- **`noise_fooled`** — the measure rises when noise is added to a defocused
  region. Five of six do.
- **`ground_truth_kind`** (`focus_arm_b_rule.csv`) — always read this before
  `precision_vs_reject`. It reads `agent-derived`, meaning the positives were
  labelled by a vision-LLM panel whose members saw the same contact sheets, so
  their errors correlate. Compare `precision_vs_reject` against
  `base_reject_rate` — the lift, not the raw precision, is the informative
  number, and it is directional only.
- **`pair_margin`** (`phase2_eval_runs.csv`) — separation between same-burst and
  different-burst distances, grouped by EXIF capture time. Constructed ground
  truth, unlike `pick_review`, which scores against pipeline-produced columns and
  is therefore circular.

## Provenance

Every row comes from the pinned 236-image population
(`../study_image_ids.txt`), so all tables join on the same images. The
`image_ids_file` column records that explicitly. Production was read
**read-only** throughout.

**No accuracy claim is supported by these tables alone.** Ground truth here is
constructed (known degradation strength, EXIF bursts) or derived (agreement with
the incumbent stack, or with the camera's AF intent). Within-burst verdicts in
`../labels/label_set.csv` are filled as **agent-derived** (vision-LLM consensus;
sidecar `label_set_judges-57c86c08-6a1e-41d0-88b7-bf9d5e0a2f59.json`) — not human
ground truth. See [the labelling runbook](../../../docs/guides/BIRD_CROP_LABELLING.md).

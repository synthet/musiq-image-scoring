# Bird bbox crop study — consolidated report

> **Status:** point-in-time research memo, not a product spec. Production was read read-only throughout; nothing in this study writes to it.

## Verdicts

| Phase | Verdict | Ground truth | Basis |
|---|---|---|---|
| Quality scoring (IQA) | **no benefit** | constructed | Crop sensitivity ratio as low as 0.0x — the full frame already sees subject degradation, so cropping adds little. |
| Bbox geometry (free signal) | **add as complementary signal** | agent-derived | Geometry adds 0.2175 ROC-AUC over score-alone on agent-derived labels, clearing the 0.03 gate. Worth exposing as first-class features — and it costs no inference, since the box is already stored. |
| Species (BioCLIP) | **add as complementary signal** | derived | Within-burst agreement changes by 0.0181 and mean top-1 confidence by 0.0398 when cropping (crop minus whole image); labels flip on 0.2119 of images. Candidate-list normalised entropy is 0.8569. No material change in agreement either way. |
| Culling embeddings | **no benefit** | constructed | Burst pair-margin over 9 model x long-edge cell(s): the best crop source beats the full frame in 6 of them, mean delta +0.0028 (same-burst vs different-burst separation). That is below the +/-0.02 materiality bar, so cropping buys the culling embeddings nothing; the crop payoff is in the IQA track, not here. |
| Captions (BLIP) | **add as complementary signal** | derived | Within-burst caption uniqueness over 3 long-edge(s): best crop source minus full frame is +0.1052. Cropping makes BLIP distinguish frames within a burst more. |
| Focus (classical + AF) | **no benefit** | derived | Over 216 image(s) with AF geometry, the best blur-tracking measure on the crop is `tenengrad` at AUC 0.465 (0.5 = chance). Crop separates better than the full frame for 3/6 measures. That is inside the +/-0.05 materiality bar, so classical focus measures do not predict real misfocus on this population. `local_entropy` scores higher (AUC 0.6082) but does not track blur at all, so its separation reflects something else — scene complexity or subject size — not focus. |

### Ground-truth standing

| Tag | Meaning |
|---|---|
| `human` | Human within-burst verdicts. Non-circular; the only basis for an accuracy claim. |
| `agent-derived` | Vision-LLM consensus; independent of the scoring pipeline under test, but not human ground truth. |
| `constructed` | True by construction (known degradation strength) or unbiased (EXIF capture-time bursts). |
| `derived` | Compared against pipeline-produced columns (`rating`, `pick_status`, BLIP captions). Measures agreement with the incumbent stack, **not** accuracy. |

## The premise, measured

Corpus: **37417** images with a real bird box.

| Full-frame resize | bird long side p10 | p50 | p90 |
|---|---|---|---|
| 224 px | 42.8 | 77.6 | 157.4 |
| 384 px | 73.4 | 133.1 | 269.7 |
| 512 px | 97.9 | 177.4 | 359.7 |

`area_frac` p10/p50/p90: **0.0399 / 0.1173 / 0.4471** — the median bird occupies a single-digit percentage of the frame, which is why full-frame downscaling loses it.

## Degradation sensitivity (constructed ground truth)

| Model | Degradation | Full-frame drop | Crop drop | Ratio |
|---|---|---|---|---|
| liqe | blur | 0.1495 | 0.539 | **3.61x** |
| liqe | motion | 0.2977 | 0.7218 | **2.42x** |
| liqe | noise | 0.0224 | 0.3923 | **17.51x** |
| topiq | blur | 0.1203 | 0.3495 | **2.91x** |
| topiq | motion | 0.1671 | 0.5216 | **3.12x** |
| topiq | noise | 0.0413 | 0.2891 | **7.0x** |
| arniqa | blur | 0.0238 | 0.0936 | **3.93x** |
| arniqa | motion | 0.0369 | 0.1385 | **3.75x** |
| arniqa | noise | 0.0114 | 0.1345 | **11.8x** |
| laplacian_variance | blur | 0.2405 | 0.7612 | **3.17x** |
| laplacian_variance | motion | 0.2143 | 0.7071 | **3.3x** |
| laplacian_variance | noise | 0.0033 | 0.0 | **0.0x** |
| tenengrad | blur | 0.142 | 0.6568 | **4.63x** |
| tenengrad | motion | 0.1315 | 0.5843 | **4.44x** |
| tenengrad | noise | 0.0144 | 0.0073 | **0.51x** |
| dog_energy | blur | 0.0584 | 0.5137 | **8.8x** |
| dog_energy | motion | 0.0639 | 0.4166 | **6.52x** |
| dog_energy | noise | 0.004 | 0.0019 | **0.47x** |
| haar_energy | blur | 0.0545 | 0.3925 | **7.2x** |
| haar_energy | motion | 0.0564 | 0.3579 | **6.35x** |
| haar_energy | noise | 0.0019 | 0.0002 | **0.11x** |

## Detail reports

| Report | Present |
|---|---|
| `geometry.md` | yes |
| `degradation.md` | yes |
| `species_crop.md` | yes |
| `focus.md` | yes |
| `reports/clip-culling/input-size/` | embedding / iqa / caption sweep output |

## Caveats

- **No human quality ground truth exists in the database.** `rating` and `label` are computed by `snorm.compute_all()` (`modules/pipeline.py:652`), `pick_status` by `cull_decision_to_pick_status()` (`modules/selection_policy.py:89`), and `title`/`description` are BLIP output (`modules/tagging.py:1569`). Any metric against those columns measures agreement with the incumbent stack, so it would penalise exactly the new information cropping adds. Hence the label set and the constructed metrics.
- **The boxed population is still growing.** A `bird_bbox` backfill has been running during this study, so absolute counts and percentiles drift between runs; re-run once it settles before quoting final figures.
- **`cropctx` is a no-op on this library.** The computed-context variant expands only 5 of ~25k boxes at 224 px (198 at 512 px) because 45MP frames already yield native boxes far larger than any model input. It is excluded from the default sweep and retained only for long edges >= 768.
- **Only the top-1 box is stored.** `bird_bbox` holds a single object, so multi-bird frames are represented by their highest-confidence bird only.

---

Generated by `scripts.research.bird_crop.report`.

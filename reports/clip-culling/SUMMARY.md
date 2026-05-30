# Culling embedding spike — summary report (CLIP L/14 + DINOv2 + SigLIP2)

_Generated 2026-05-29T20:01:59 — E2E DB `image_scoring_test` (read/write), prod `image_scoring` (read-only seed)._

Offline research harness: seeds a representative bird/stack/label subset into the E2E Postgres DB, registers OpenAI + OpenCLIP ViT-L/14 (768-d) embedding spaces, and evaluates score signal novelty, mishot rejection, diverse stack picks, bird-pose selection, scene sub-stacking, CLIP color labels, keyword accuracy, and grouping quality (EXIF-burst GT). See `REFERENCES.md` for model/paper sources.

## Corpus & setup
| metric | value |
| --- | --- |
| seed folders | [62, 44, 45, 676] |
| images | 2126 |
| stacks | 688 |
| image_keywords | 6158 |
| image_model_scores | 12904 |
| baseline embeddings copied | 5171 |

**L/14 embedding persist (E2E):**
| space | embedded | ms/img | peak VRAM MB |
| --- | --- | --- | --- |
| dinov2_reg_base_image | 2126 | 155.6 | 1004.2 |
| siglip2_base_image | 2126 | 182.8 | 916.6 |

Aesthetic head: `21dd590f3ccdc646` (3714759 bytes). Towers: OpenAI `ViT-L-14-quickgelu/openai`, OpenCLIP `ViT-L-14/laion2b_s32b_b82k`.

## Exp 1 — Score signal quality / novelty
| signal | p02 | p50 | p98 | max|ρ| vs existing | |ρ| vs rating | new? |
| --- | --- | --- | --- | --- | --- | --- |
| aes_openai | 4.2003 | 4.73 | 5.2943 | 0.5443 | 0.1015 |  |
| sharp_openai | -0.007 | 0.0064 | 0.0282 | 0.2551 | 0.0648 |  |
| expo_openai | -0.0589 | -0.0332 | -0.0029 | 0.5754 | 0.4934 |  |
| clipiqa_openai | 0.3487 | 0.7855 | 0.9392 | 0.5159 | 0.4562 |  |
| aes_openclip | 4.6872 | 5.3762 | 6.1017 | 0.1658 | 0.1159 | (diag.) |

OpenAI vs OpenCLIP aesthetic-head agreement (diagnostic): Spearman -0.0995, Pearson -0.0565 (n=2126).

## Exp 2 — Mishot rejection
Ground-truth rejects: 573 / 2126 (cull=reject OR label=Red OR rating≤2).
| detector | ROC-AUC | PR-AUC | n |
| --- | --- | --- | --- |
| clipiqa_bad_openai | 0.5604 | 0.34 | 2126 |
| neg_sharp_openai | 0.5348 | 0.3004 | 2126 |
| neg_expo_openai | 0.5462 | 0.3133 | 2126 |
| neg_aesthetic_openai | 0.6112 | 0.3557 | 2126 |
| baseline_neg_score_technical | 0.6883 | 0.5749 | 2126 |
| baseline_neg_arniqa | 0.5981 | 0.3763 | 2126 |

## Exp 3 — Diverse high-scored stack picks (MMR vs single-best)
| metric | top-k by quality | MMR (L/14) |
| --- | --- | --- |
| mean intra-selection diversity | 0.0333 | 0.0357 |
| mean retained quality (aesthetic) | 4.824 | 4.823 |

Diversity gain from MMR: **7.3%** over 92 stacks (k=3).

## Exp 4 — Distinctive bird poses (BioCLIP vs CLIP L/14)
Species stacks evaluated: 52 (k=3). Mean selection overlap L/14 vs BioCLIP: **0.532**.

## Exp 5 — Scene-based sub-stacking (semantic vs visual)
| metric | semantic (CLIP L/14) | visual (MobileNet) |
| --- | --- | --- |
| mean silhouette | 0.5616 | 0.3272 |

Stacks evaluated: 48 (≥8 members); selected cosine threshold 0.08 (swept 0.08, 0.12, 0.18, 0.25, 0.3).

## Exp 6 — CLIP-query color labels
Evaluated 2126 labeled images; overall agreement with human labels: **0.4073**.

| label | precision | recall | support |
| --- | --- | --- | --- |
| Red | 0.097 | 0.167 | 18 |
| Yellow | 0.429 | 0.024 | 248 |
| Green | 0.0 | 0.0 | 957 |
| Blue | 0.423 | 0.95 | 902 |
| Purple | 0.0 | 0.0 | 1 |

_Heuristic rubric; bird folders are label-skewed. Agreement is directional._

## Exp 7 — Keyword accuracy
| model | Jaccard vs B/32 baseline |
| --- | --- |
| openai | 0.0972 |
| openclip | 0.1625 |

OpenAI vs OpenCLIP L/14 keyword Jaccard: **0.4279**. SigLIP2 vs OpenAI L/14: **None**. Human-truth F1: None (n_user_truth=0). No source='user' keywords in seed; reporting inter-model agreement vs B/32 baseline only.

Spot-check (file → B/32 | OpenAI L/14 | OpenCLIP L/14):
- `DSC_1253.NEF`: [] | ['insect'] | ['insect', 'nature', 'wildlife']
- `DSC_1265.NEF`: [] | ['birds'] | ['birds']
- `DSC_1276.NEF`: [] | ['birds'] | ['birds', 'wildlife']
- `DSC_1277.NEF`: [] | ['birds'] | ['birds']
- `DSC_1278.NEF`: [] | ['birds'] | ['birds']
- `DSC_1279.NEF`: [] | ['birds'] | ['birds']

## Exp 8 — Grouping quality (EXIF-burst ground truth)
Burst gap: **2.0s**; thresholds swept: [0.04, 0.06, 0.08, 0.1, 0.12, 0.15, 0.18, 0.22, 0.25, 0.3].

| space | mean ARI (burst GT) | best threshold |
| --- | --- | --- |
| openclip_l14_laion2b_image | 0.4502 | 0.06 |
| openai_clip_vit_l14_image | 0.4419 | 0.06 |
| siglip2_base_image | 0.4315 | 0.04 |
| mobilenet_v2_imagenet_gap | 0.4231 | 0.18 |
| clip_vit_b32_image | 0.4086 | 0.04 |
| dinov2_reg_base_image | 0.377 | 0.12 |

**mobilenet_v2_imagenet_gap** @ thr 0.18: ARI=0.4231, AMI=0.6125, false-merge=0.0097, false-split=0.0093, silhouette=0.3137; stack-id ARI (biased)=0.5933.
**clip_vit_b32_image** @ thr 0.04: ARI=0.4086, AMI=0.5652, false-merge=0.0037, false-split=0.0115, silhouette=0.2592; stack-id ARI (biased)=0.4716.
**openai_clip_vit_l14_image** @ thr 0.06: ARI=0.4419, AMI=0.6507, false-merge=0.0258, false-split=0.0061, silhouette=0.3269; stack-id ARI (biased)=0.3343.
**openclip_l14_laion2b_image** @ thr 0.06: ARI=0.4502, AMI=0.6362, false-merge=0.0103, false-split=0.0096, silhouette=0.2789; stack-id ARI (biased)=0.3646.
**dinov2_reg_base_image** @ thr 0.12: ARI=0.377, AMI=0.566, false-merge=0.018, false-split=0.0097, silhouette=0.3007; stack-id ARI (biased)=0.2663.
**siglip2_base_image** @ thr 0.04: ARI=0.4315, AMI=0.6109, false-merge=0.0124, false-split=0.0097, silhouette=0.2682; stack-id ARI (biased)=0.3859.

_Primary GT is EXIF-burst (unbiased). stack_id ARI is MobileNet-biased secondary._

## Recommendations (per use case × tower × head)
| use case | tower × head | verdict |
| --- | --- | --- |
| Score signal | OpenAI L/14 + aesthetic/CLIP-IQA | WATCH: signals largely track existing scores (aesthetic/exposure ρ≈0.5) and correlate only weakly with human rating; no clearly novel keeper signal. (`aes_openclip` low-corr is a tower-mismatch artifact, not a real signal.) |
| Mishot rejection | neg_aesthetic_openai | DROP/keep ARNIQA: best CLIP detector ROC-AUC 0.6112 vs baseline baseline_neg_score_technical=0.6883. |
| Diverse stack picks | OpenAI L/14 + MMR | WATCH: MMR adds 7.3% intra-selection diversity vs top-k-by-quality. |
| Bird poses | BioCLIP vs CLIP L/14 | INFO: selection overlap 0.532; towers pick different poses (complementary). |
| Scene sub-stacking | CLIP L/14 vs MobileNet | WATCH: at thr 0.08, semantic splits few stacks (7) but cleanly (silhouette 0.5616); visual splits many (45) at 0.3272. CLIP semantic is conservative (groups near-identical scenes) — useful for scene-level sub-stacks, not frame-level dedup. |
| Color labels | OpenAI L/14 + rubric | WATCH: 0.4073 agreement with human labels (rubric heuristic, label-skewed). |
| Keyword accuracy | SigLIP2 / CLIP L/14 / B/32 | INFO: Jaccard vs B/32 baseline {'openai': 0.0972, 'openclip': 0.1625}; SigLIP2=None. SigLIP2 uses per-tag sigmoid (roadmap method). |
| Grouping (stacks) | openclip_l14_laion2b_image | INFO: best space openclip_l14_laion2b_image ARI=0.4502; ranking head: [{'space': 'openclip_l14_laion2b_image', 'mean_ari': 0.4502, 'best_threshold': 0.06}, {'space': 'openai_clip_vit_l14_image', 'mean_ari': 0.4419, 'best_threshold': 0.06}, {'space': 'siglip2_base_image', 'mean_ari': 0.4315, 'best_threshold': 0.04}]. DINOv2 ARI=0.377 @ thr 0.12. |

> Tower-mismatch caveat: the LAION aesthetic head is valid on **OpenAI** CLIP embeddings; `aes_openclip` numbers are diagnostic only.
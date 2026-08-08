# Bird crop vs full frame — synthetic degradation sensitivity

> Ground truth **by construction**: the degradation strength is known, so this needs no human labels and cannot be circular.

Images: **236** · scored at long edge **512** · working resolution **3000** · crop variant **crop** · models ['haar_energy']

## Verdict — sensitivity to subject-only degradation

Effect size is the **relative score drop** from clean to worst. Spearman is not used here: it saturates at -1.0 in every cell, so it confirms direction but cannot separate "noticed slightly" from "noticed a lot".

`crop_sensitivity_ratio > 1` supports the premise; ~1 would refute it.

| Model | Degradation | Full-frame drop | Crop drop | Sensitivity ratio | Whole-frame control |
|---|---|---|---|---|---|
| liqe | blur | 0.1495 | 0.539 | **3.61x** | 0.415 |
| liqe | motion | 0.2977 | 0.7218 | **2.42x** | 0.6467 |
| liqe | noise | 0.0224 | 0.3923 | **17.51x** | 0.0936 |
| topiq | blur | 0.1203 | 0.3495 | **2.91x** | 0.4708 |
| topiq | motion | 0.1671 | 0.5216 | **3.12x** | 0.5674 |
| topiq | noise | 0.0413 | 0.2891 | **7.0x** | 0.1312 |
| arniqa | blur | 0.0238 | 0.0936 | **3.93x** | 0.2072 |
| arniqa | motion | 0.0369 | 0.1385 | **3.75x** | 0.4347 |
| arniqa | noise | 0.0114 | 0.1345 | **11.8x** | 0.0433 |
| laplacian_variance | blur | 0.2405 | 0.7612 | **3.17x** | 0.9473 |
| laplacian_variance | motion | 0.2143 | 0.7071 | **3.3x** | 0.8369 |
| laplacian_variance | noise | 0.0033 | 0.0 | **0.0x** | 0.0062 |
| tenengrad | blur | 0.142 | 0.6568 | **4.63x** | 0.6279 |
| tenengrad | motion | 0.1315 | 0.5843 | **4.44x** | 0.5761 |
| tenengrad | noise | 0.0144 | 0.0073 | **0.51x** | 0.045 |
| dog_energy | blur | 0.0584 | 0.5137 | **8.8x** | 0.3024 |
| dog_energy | motion | 0.0639 | 0.4166 | **6.52x** | 0.3268 |
| dog_energy | noise | 0.004 | 0.0019 | **0.47x** | 0.0128 |
| haar_energy | blur | 0.0545 | 0.3925 | **7.2x** | 0.2947 |
| haar_energy | motion | 0.0564 | 0.3579 | **6.35x** | 0.3058 |
| haar_energy | noise | 0.0019 | 0.0002 | **0.11x** | 0.0054 |

### Harness self-check

⚠️ **Suspect**: ['laplacian_variance/noise', 'dog_energy/noise', 'haar_energy/noise'] — a scorer that cannot rank a *whole-frame* degradation ladder at all points to a harness bug rather than a finding.

Weak but correctly-signed whole-frame response: ['liqe/noise (ρ=-0.8356)', 'arniqa/blur (ρ=-0.8475)', 'arniqa/noise (ρ=-0.553)', 'tenengrad/noise (ρ=-0.7186)']. That is a property of the model (limited sensitivity to that degradation), not a harness problem — LIQE in particular responds only weakly to noise.

## Full cell detail

| Model | kind/region/scored-on | mean ρ | mean rel. drop | % monotonic | n |
|---|---|---|---|---|---|
| liqe | `blur/frame/crop` | -0.9966 | 0.705 | 99.6 | 236 |
| liqe | `blur/frame/full` | -0.9996 | 0.415 | 100.0 | 236 |
| liqe | `blur/subject/crop` | -0.978 | 0.539 | 96.2 | 236 |
| liqe | `blur/subject/full` | -0.9254 | 0.1495 | 94.9 | 236 |
| liqe | `motion/frame/crop` | -0.9979 | 0.7618 | 99.6 | 236 |
| liqe | `motion/frame/full` | -0.9996 | 0.6467 | 100.0 | 236 |
| liqe | `motion/subject/crop` | -0.9945 | 0.7218 | 100.0 | 236 |
| liqe | `motion/subject/full` | -0.9767 | 0.2977 | 97.5 | 236 |
| liqe | `noise/frame/crop` | -0.9818 | 0.4328 | 97.0 | 236 |
| liqe | `noise/frame/full` | -0.8356 | 0.0936 | 74.2 | 236 |
| liqe | `noise/subject/crop` | -0.9758 | 0.3923 | 94.9 | 236 |
| liqe | `noise/subject/full` | -0.6627 | 0.0224 | 54.2 | 236 |
| topiq | `blur/frame/crop` | -1.0 | 0.7335 | 100.0 | 236 |
| topiq | `blur/frame/full` | -1.0 | 0.4708 | 100.0 | 236 |
| topiq | `blur/subject/crop` | -0.9517 | 0.3495 | 92.8 | 236 |
| topiq | `blur/subject/full` | -0.9165 | 0.1203 | 89.0 | 236 |
| topiq | `motion/frame/crop` | -0.9987 | 0.8155 | 100.0 | 236 |
| topiq | `motion/frame/full` | -1.0 | 0.5674 | 100.0 | 236 |
| topiq | `motion/subject/crop` | -0.9856 | 0.5216 | 97.9 | 236 |
| topiq | `motion/subject/full` | -0.9581 | 0.1671 | 91.9 | 236 |
| topiq | `noise/frame/crop` | -0.9966 | 0.3751 | 100.0 | 236 |
| topiq | `noise/frame/full` | -0.972 | 0.1312 | 96.2 | 236 |
| topiq | `noise/subject/crop` | -0.9945 | 0.2891 | 100.0 | 236 |
| topiq | `noise/subject/full` | -0.9258 | 0.0413 | 88.6 | 236 |
| arniqa | `blur/frame/crop` | -0.8733 | 0.4478 | 75.8 | 236 |
| arniqa | `blur/frame/full` | -0.8475 | 0.2072 | 75.8 | 236 |
| arniqa | `blur/subject/crop` | -0.5047 | 0.0936 | 49.2 | 236 |
| arniqa | `blur/subject/full` | -0.3398 | 0.0238 | 44.9 | 236 |
| arniqa | `motion/frame/crop` | -0.9839 | 0.5982 | 98.7 | 236 |
| arniqa | `motion/frame/full` | -0.9564 | 0.4347 | 93.2 | 236 |
| arniqa | `motion/subject/crop` | -0.5267 | 0.1385 | 47.0 | 236 |
| arniqa | `motion/subject/full` | -0.386 | 0.0369 | 46.6 | 236 |
| arniqa | `noise/frame/crop` | -0.9008 | 0.2453 | 86.0 | 236 |
| arniqa | `noise/frame/full` | -0.553 | 0.0433 | 58.5 | 236 |
| arniqa | `noise/subject/crop` | -0.8119 | 0.1345 | 72.5 | 236 |
| arniqa | `noise/subject/full` | -0.414 | 0.0114 | 42.4 | 236 |
| laplacian_variance | `blur/frame/crop` | -1.0 | 0.9897 | 100.0 | 236 |
| laplacian_variance | `blur/frame/full` | -1.0 | 0.9473 | 100.0 | 236 |
| laplacian_variance | `blur/subject/crop` | -0.9919 | 0.7612 | 100.0 | 236 |
| laplacian_variance | `blur/subject/full` | -1.0 | 0.2405 | 100.0 | 236 |
| laplacian_variance | `motion/frame/crop` | -1.0 | 0.9196 | 100.0 | 236 |
| laplacian_variance | `motion/frame/full` | -1.0 | 0.8369 | 100.0 | 236 |
| laplacian_variance | `motion/subject/crop` | -0.9996 | 0.7071 | 100.0 | 236 |
| laplacian_variance | `motion/subject/full` | -1.0 | 0.2143 | 100.0 | 236 |
| laplacian_variance | `noise/frame/crop` | 0.9996 | 0.0 | 0.0 | 236 |
| laplacian_variance | `noise/frame/full` | 0.597 | 0.0062 | 10.6 | 236 |
| laplacian_variance | `noise/subject/crop` | 0.9958 | 0.0 | 0.0 | 236 |
| laplacian_variance | `noise/subject/full` | 0.0326 | 0.0033 | 35.6 | 236 |
| tenengrad | `blur/frame/crop` | -1.0 | 0.8538 | 100.0 | 236 |
| tenengrad | `blur/frame/full` | -1.0 | 0.6279 | 100.0 | 236 |
| tenengrad | `blur/subject/crop` | -1.0 | 0.6568 | 100.0 | 236 |
| tenengrad | `blur/subject/full` | -1.0 | 0.142 | 100.0 | 236 |
| tenengrad | `motion/frame/crop` | -1.0 | 0.757 | 100.0 | 236 |
| tenengrad | `motion/frame/full` | -1.0 | 0.5761 | 100.0 | 236 |
| tenengrad | `motion/subject/crop` | -1.0 | 0.5843 | 100.0 | 236 |
| tenengrad | `motion/subject/full` | -1.0 | 0.1315 | 100.0 | 236 |
| tenengrad | `noise/frame/crop` | 0.5034 | 0.0078 | 19.5 | 236 |
| tenengrad | `noise/frame/full` | -0.7186 | 0.045 | 68.2 | 236 |
| tenengrad | `noise/subject/crop` | 0.422 | 0.0073 | 22.0 | 236 |
| tenengrad | `noise/subject/full` | -0.9237 | 0.0144 | 88.6 | 236 |
| dog_energy | `blur/frame/crop` | -1.0 | 0.6827 | 100.0 | 236 |
| dog_energy | `blur/frame/full` | -1.0 | 0.3024 | 100.0 | 236 |
| dog_energy | `blur/subject/crop` | -1.0 | 0.5137 | 100.0 | 236 |
| dog_energy | `blur/subject/full` | -1.0 | 0.0584 | 100.0 | 236 |
| dog_energy | `motion/frame/crop` | -1.0 | 0.5486 | 100.0 | 236 |
| dog_energy | `motion/frame/full` | -0.9979 | 0.3268 | 100.0 | 236 |
| dog_energy | `motion/subject/crop` | -1.0 | 0.4166 | 100.0 | 236 |
| dog_energy | `motion/subject/full` | -1.0 | 0.0639 | 100.0 | 236 |
| dog_energy | `noise/frame/crop` | 0.7627 | 0.0023 | 6.4 | 236 |
| dog_energy | `noise/frame/full` | 0.0013 | 0.0128 | 31.8 | 236 |
| dog_energy | `noise/subject/crop` | 0.7208 | 0.0019 | 7.2 | 236 |
| dog_energy | `noise/subject/full` | -0.5758 | 0.004 | 61.0 | 236 |
| haar_energy | `blur/frame/crop` | -1.0 | 0.5276 | 100.0 | 236 |
| haar_energy | `blur/frame/full` | -1.0 | 0.2947 | 100.0 | 236 |
| haar_energy | `blur/subject/crop` | -1.0 | 0.3925 | 100.0 | 236 |
| haar_energy | `blur/subject/full` | -1.0 | 0.0545 | 100.0 | 236 |
| haar_energy | `motion/frame/crop` | -1.0 | 0.4786 | 100.0 | 236 |
| haar_energy | `motion/frame/full` | -0.9979 | 0.3058 | 100.0 | 236 |
| haar_energy | `motion/subject/crop` | -1.0 | 0.3579 | 100.0 | 236 |
| haar_energy | `motion/subject/full` | -1.0 | 0.0564 | 100.0 | 236 |
| haar_energy | `noise/frame/crop` | 0.9758 | 0.0002 | 0.4 | 236 |
| haar_energy | `noise/frame/full` | 0.4979 | 0.0054 | 13.6 | 236 |
| haar_energy | `noise/subject/crop` | 0.9775 | 0.0002 | 0.4 | 236 |
| haar_energy | `noise/subject/full` | -0.0242 | 0.0019 | 28.4 | 236 |

### Ladders

- **blur**: [0.0, 0.8, 1.6, 3.2, 6.4]
- **motion**: [0.0, 5.0, 11.0, 21.0, 41.0]
- **noise**: [0.0, 4.0, 8.0, 16.0, 32.0]

---

Generated by `scripts.research.bird_crop.degradation_eval`. Production was read read-only; nothing was written to it.

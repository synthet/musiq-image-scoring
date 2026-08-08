# Student Scorer Model Card (template)

Fill after a checkpoint clears locked shadow gates. Do not publish weights without human approval.

## Intended use

Shadow multi-head proxy of the live Vexlum IQA ensemble for latency reduction research.
Not a production fusion member until a separate promotion decision.

## Identifiers

| Field | Value |
|-------|-------|
| Bundle ID | TBD |
| Manifest ID | TBD |
| Protocol ID | TBD |
| Namespace | `vexlum_student_v1_*` |

## Architecture

- Backbone: ConvNeXt-Tiny (reference) or recorded challenger
- Inputs: P0 production preprocess fingerprint
- Outputs: teacher proxies + derived composites + uncertainty

## Metrics

Report IID / OOD with confidence intervals from the frozen evaluator. Attach subgroup table.

## Limitations

- Distills teacher errors
- May miss fine technical detail at 512px (see P2 ablation)
- Uncertainty is advisory until calibration curves pass

## Latency / deps

See `requirements/requirements_student_scorer.txt` and benchmark JSON under artifacts.

## Rollback

Disable all `vexlum_student_v1_*` (`enabled:false`, `shadow:false`). Do not delete shadow DB rows.

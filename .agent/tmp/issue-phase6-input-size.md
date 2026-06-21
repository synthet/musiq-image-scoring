## Summary

**Phase 6:** Synthesize tiered pixel policy from full eval artifacts and produce sign-off memo. **No production config changes** in this issue — checklist only.

**Depends on:** Phases 1–3 complete; Phase 5 if applicable.

Part of epic #260.

## Acceptance criteria

- [ ] `eval_summary.json` populated for embedding, iqa, tagging, caption tracks
- [ ] `UNIFIED_INPUT_POLICY.md` contains per-track best configs (not placeholder status)
- [ ] Wiki memo updated: `INPUT_SIZE_CULLING_PRELIMINARY_2026-05-30.md` with measured findings
- [ ] Tiered recommendation drafted: MAX_SIZE, `max_load_px`, `raw_conversion.max_resolution`, per-model `max_dimension`, optional ViT preprocess
- [ ] Diversity checklist passed (burst ARI, tag entropy, caption uniqueness vs baseline)
- [ ] Production follow-up items filed as **separate** issues if policy warrants changes (do not ship config in research PR)

## Deliverables

- `reports/clip-culling/input-size/UNIFIED_INPUT_POLICY.md`
- `docs/reports/UNIFIED_INPUT_POLICY_2026-05-31.md` (or dated successor)
- Comment on gallery cross-repo issue with policy summary

## Decision rules

See preliminary memo § Decision rules (extended) — weight culling + mishot over keyword entropy unless Jaccard drops >5%.

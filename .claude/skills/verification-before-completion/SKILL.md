---
name: verification-before-completion
description: >-
  Use before claiming work is complete, fixed, passing, ready to commit, or ready
  for PR. Apply to ensure fresh command output supports every success claim and to
  report warnings or failures honestly.
---

# Verification before completion (compiled harness)

Do not claim done/fixed/passing/ready until fresh command output supports the claim.

## Invoke

```bash
# List catalog
python scripts/agent_skills/verification_before_completion.py --json

# Run selected proofs
python scripts/agent_skills/verification_before_completion.py \
  --claim assets_synced --claim frontmatter_ok --run --json

# Full agent-infra verify suite for this repo
python scripts/agent_skills/verification_before_completion.py --suite --run --json
```

## LLM judgment slots

1. **Name the claim** and pick the falsifying proof (catalog ids or custom command).
2. **Interpret output** after the final edit — exit code, warnings, skipped tests, scope.
3. Report pass / warn / fail with the exact command; never upgrade incomplete verification to pass.

## Use with

- `validate-implementation` when an AC matrix is required
- `commit-and-push` before an actual commit (backend)

---
name: eval
description: Capture task quality signals and log them to agent memory to build a
  feedback loop. Use at the end of each implemented task or merged PR.
---

# /eval — Task quality feedback loop

Run after every implemented task or merged PR. Captures three verifiable signals,
maps them to memory candidates, and writes them via `/log-session` so the team
learns from what worked and what needed iteration.

## Inputs

- Completed task or PR (description and outcome).
- Test results: pass rate, first-try success, number of iterations.

## Signals to capture

| Signal | Values | How to measure |
|--------|--------|----------------|
| `test_pass_rate` | `yes` / `partial` / `no` | Did tests pass after implementation? |
| `first_try_success` | `yes` / `no` | Did the first implementation attempt need rework? |
| `iteration_count` | integer | How many plan/implement cycles before done? |

## Outcome → memory candidate mapping

| Outcome | Category | Confidence |
|---------|----------|------------|
| First-try success, all tests green | `successful_pattern` | `high` |
| >2 iterations required | `recurring_issue` | `medium` |
| Tests were missing or not written before implementation | `working_rule` | `high` |
| Partial test pass (some failures remain) | `recurring_issue` | `medium` |

## Steps

1. Measure the three signals above for the completed task.
2. Map outcome to the category table; compose a one-line memory candidate text.
3. Log to agent memory:

```bash
python scripts/agent-memory/log_session.py \
  --summary "Implemented <feature>" \
  --outcome "Tests passed / partial / failed; <N> iterations" \
  --candidate "text|category|confidence"
```

### Example — first-try success

```bash
python scripts/agent-memory/log_session.py \
  --summary "Added ARNIQA shadow scoring" \
  --outcome "All tests green on first try; 1 iteration" \
  --candidate "Writing percentile anchors to config before fusing new model works cleanly|successful_pattern|high"
```

### Example — tests-first rule triggered

```bash
python scripts/agent-memory/log_session.py \
  --summary "Fixed clustering threshold bug" \
  --outcome "Tests were absent; wrote stubs first, then fixed; 3 iterations" \
  --candidate "Always write failing test stubs before touching clustering code—no fast unit tests exist yet|working_rule|high"
```

## Done when

- Signals are recorded for this task.
- At least one `--candidate` flag passed to `/log-session`.
- `/dream-memory` is queued for next periodic consolidation.

## Related

- [agent-memory skill](../agent-memory/SKILL.md) — full log/dream/promote workflow
- `/log-session` — session logging command
- `/dream-memory` — consolidate sessions into proposed memory

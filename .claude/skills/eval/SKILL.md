---
name: eval
description: Capture task quality signals and log them to agent memory to build a feedback loop. Use at the end of each implemented task or merged PR, or whenever a task required more than one agent iteration.
---

# eval

Eval design — building feedback loops with verifiable signals — is a core agentic engineering
skill. Without it, the framework improves only by accident. This skill closes that loop by logging
structured quality signals after each task so patterns surface in project memory.

## When to use

- After any `/implement` + `/pr-ready` cycle completes (success or not)
- When a task required more than one agent round to complete
- When tests were missing and had to be written after the fact
- When a regression was introduced and caught (or missed) during the task

## Three signals to capture

For each completed task, measure:

| Signal | Question | Values |
|--------|----------|--------|
| `test_pass_rate` | Did all tests pass on the **first** agent attempt? | `yes` / `partial` / `no` |
| `first_try_success` | Was the implementation accepted without revision? | `yes` / `no` |
| `iteration_count` | How many agent rounds before done? | integer |

## Step-by-step

### 1. Assess the outcome

After the task completes, answer the three signal questions above.

### 2. Map to a memory candidate

| Outcome | Category | Confidence | Example text |
|---------|----------|------------|--------------|
| First-try success, all tests green | `successful_pattern` | `high` | "Tests-first approach on auth module: zero retries, full green" |
| Required 2–3 iterations | `recurring_issue` | `medium` | "UI snapshot tests require manual update after layout changes" |
| Required >3 iterations | `recurring_issue` | `high` | "Database migration tasks consistently need schema inspection first" |
| Tests were missing (written after code) | `working_rule` | `high` | "Always write test stubs for [module] before implementing" |
| Regression caught in review | `working_rule` | `high` | "Run integration suite before merging [subsystem] changes" |
| Regression shipped (caught later) | `recurring_issue` | `high` | "[Feature] broke [dependency] — add coverage for that path" |

### 3. Log the session

```bash
python scripts/agent-memory/log_session.py \
  --summary "Implemented <feature> (issue #<N>)" \
  --outcome "<first_try_success|partial|multi-iteration>" \
  --test-results "<pass|partial|fail>" \
  --candidate "<memory text>|<category>|<confidence>"
```

Add a second `--candidate` flag for each additional insight from the task.

### 4. Periodic review

After 5–10 tasks, run `/dream-memory` and check the `## Successful Patterns` and
`## Recurring Issues` sections. If the same module or workflow appears in recurring issues
more than twice, that is a signal to improve the spec template, add a pre-flight checklist,
or improve test coverage for that area.

## Done when

- At least one memory candidate is logged per task outcome.
- Any pattern appearing ≥ 3 times in recurring issues has a proposed fix filed as a backlog issue.

## Cross-references

- `/log-session` — CLI wrapper for `log_session.py`
- `/dream-memory` — Consolidate logged sessions into a proposed memory update
- `agent-memory` skill — Full memory pipeline (log → dream → promote → context)
- `backlog-queue` skill — File a follow-up issue for systemic problems found via eval

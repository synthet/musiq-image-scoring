# /compile-skill — Lower a stable skill into a deterministic harness

Use when a procedural skill has crystallized and agents keep paying the reasoning tax to re-derive
the same steps. Compiles the fixed parts into `scripts/agent_skills/<name>.py` and shrinks the skill
to a thin bootloader. Pattern, current harnesses, and partition rules:
[`.agent/SKILL_COMPILATION.md`](../../.agent/SKILL_COMPILATION.md).

## Inputs

- Target skill: `.cursor/skills/<name>/SKILL.md` (or a command). If the user did not name one, list
  uncompiled candidates with their stability evidence and ask — do not pick silently.
- Stability evidence: transcript counts from the profiler, not a hunch.

```powershell
python scripts/agent_skills/profile_skill_usage.py
```

Prefer candidates already ranked in the profile table in `.agent/SKILL_COMPILATION.md`, and check its
**Next compilation candidates** section first.

## Readiness gate

Compile only if **all** hold. If any fails, say "not ready" and name the failing condition instead of
compiling an unstable procedure.

- Same sources, filters, and state every run — no per-run re-planning.
- At least one step is pure mechanics (path resolution, parsing, semver math, file rewrite, lint/test
  invocation, report skeleton).
- The judgment left over is nameable in a sentence or two ("choose the semver level").
- The skill is not mostly judgment. `critical-commit-audit`, `imgscore-mcp-debug`,
  `systematic-debugging`, and `subagent-review` are already marked **Keep LLM** — leave them as prose.

## Step 1 — Partition the steps

Produce this table before writing code, and show it to the user. It must agree with the partition
rules in `.agent/SKILL_COMPILATION.md`:

| Owner | Gets |
|-------|------|
| **Code** | Known paths, parsing, semver math, file rewrites, lint/test invocation, forbidden-path scans, report skeletons, retention/prune |
| **LLM** | Ambiguous change classification, AC verdicts from messy evidence, PR narrative, bug hunting, MCP triage, review synthesis |
| **Human** | Commit, push, publish, promote memory, apply housekeeping closes, Backlog→Ready, consequential overrides |

If a step needs a heuristic to stay correct, it belongs to the LLM. Freezing judgment into rules is
the main way this pattern fails.

## Step 2 — Implement the harness

```text
scripts/agent_skills/<name>.py
```

Match the existing harnesses (`release_bump.py`, `test_and_fix.py`, `validate_implementation.py`):

- Stdlib only; resolve the repo root from `Path(__file__).resolve().parents[2]` — no hardcoded paths.
- Read-only by default. Inspect/plan run free; writes need an explicit `apply` subcommand or `--run`.
- Support `--json` for agents and a readable summary otherwise. Errors to stderr, non-zero exit.
- When a harness needs logic another harness already has, import it rather than copying the parser.
- The harness never commits, pushes, tags, or exports outside the repo.
- Emit `needs_llm_judgment` (as `release_bump.py` does) rather than guessing when evidence is
  ambiguous — that is the handoff back to the model.

## Step 3 — Shrink the skill to a bootloader

Keep `name` first and a non-empty `description` in frontmatter, then keep only: when to use,
**Invoke** (copy-pasteable commands), **LLM judgment slots** (numbered), **Human authority**, and
**Verify**. Delete prose the harness now enforces.

## Step 4 — Test

Add fixture tests to [`tests/test_agent_skills_harnesses.py`](../../tests/test_agent_skills_harnesses.py)
covering the harness end-to-end via `--json`. Assert behavioral parity with the prose procedure on at
least one realistic fixture — that is the evidence the compile was lossless.

## Step 5 — Sync and record

```powershell
python scripts/sync_assistant_trees.py
python scripts/sync_assistant_trees.py --check
python scripts/ci/check_agent_frontmatter.py
python -m pytest tests/test_agent_skills_harnesses.py -q
```

Then update [`.agent/SKILL_COMPILATION.md`](../../.agent/SKILL_COMPILATION.md) (new row in the
compiled-harness table, and drop the skill from *Next compilation candidates*),
[`.agent/SKILL_INVENTORY.md`](../../.agent/SKILL_INVENTORY.md) (note the harness path, refresh
**Last reviewed**), and apply
[`.agent/SKILL_CHANGE_AST10_REVIEW.md`](../../.agent/SKILL_CHANGE_AST10_REVIEW.md).

## Done when

- Partition table was shown and the LLM slots are named in the bootloader.
- Harness runs read-only by default, emits `--json`, and hands ambiguity back to the model.
- Fixture tests pass and demonstrate parity on a real case.
- Sync, frontmatter, and tests are green; `.cursor/` is canonical and `.claude/` was regenerated.

## Do not

- Do not hand-edit `.claude/` — it is generated from `.cursor/` by `sync_assistant_trees.py`.
- Do not give the harness commit/push/tag or external-export authority.
- Do not claim numeric token savings; this repo has no matched before/after export. Savings are
  structural, per the measurement note in `.agent/SKILL_COMPILATION.md`.

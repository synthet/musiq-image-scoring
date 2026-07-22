# Skill compilation audit (Token Shrinker / Vivek Haldar)

Approach: [Compiling an AI agent skill](https://vivekhaldar.com/articles/compiling-an-ai-agent-skill/) — express workflows as natlang skills, run them until the shape crystallizes, then lower stable procedure into code. Keep LLM calls only where semantic judgment matters.

## Profile (2026-07-21)

Source: Cursor `agent-transcripts` for this workspace (488 jsonl files).

```powershell
python scripts/agent_skills/profile_skill_usage.py
```

| Rank | Workflow | Transcripts | Compilation state |
|-----:|----------|------------:|-------------------|
| 1 | backup-db | 72 | **Compiled** — thin skill → `Backup-Postgres.ps1` |
| 2 | /release | 68 | **Compiled** — `scripts/agent_skills/release_bump.py` |
| 3 | /test-and-fix | 55 | **Compiled this pass** — `scripts/agent_skills/test_and_fix.py` |
| 4 | docs-wiki / wiki-* | 29 | **Compiled this pass** (scaffold) — `wiki_scaffold.py`; prose/query stay LLM |
| 5 | backlog-queue | 28 | **Compiled this pass** (claim/stage) — `backlog_stage.py`; pick stays LLM |
| 6 | subagent-review | 22 | Keep LLM — review synthesis is model-shaped |
| 7 | /pr-ready | 21 | **Compiled** — `scripts/agent_skills/pr_ready_checks.py` |
| 8 | wsl-tf-python-runner | 19 | Partial — command recipes already deterministic |
| 9 | imgscore-mcp-debug | 19 | Keep LLM — triage judgment |
| 10 | critical-commit-audit | 16 | Keep LLM — bug-finding is judgment |
| 11 | agent-memory | 14 | **Compiled** — `scripts/agent-memory/*` |
| 12 | codebase-size-audit | 11 | **Compiled** — `scripts/audit/codebase_size_audit.py` |
| 13 | release-bump | 11 | **Compiled** (same harness as /release) |
| 14 | backlog-housekeeping | 9 | **Compiled** — `scripts/housekeeping_backlog.py` |
| 15 | validate-implementation | 8 | **Compiled** — `scripts/agent_skills/validate_implementation.py` |
| 16 | windows-keep-awake | 7 | **Compiled** — `Keep-Awake.ps1` |

## Partition rules

| Owner | Owns |
|-------|------|
| **Code** | Known paths, parsing, semver math, file rewrites, lint/test invocation, forbidden-path scans, report skeletons, retention/prune, wiki lint/scaffold, pytest failure fingerprints, `gh` Stage transitions |
| **LLM** | Ambiguous change classification, AC verdicts from messy evidence, PR narrative, bug hunting, MCP triage, review synthesis, root-cause repair, Ready-card prioritization, wiki prose |
| **Human** | Commit, push, publish, promote memory, apply housekeeping closes, Backlog→Ready, consequential overrides |

## Compiled harnesses (2026-07-21 pass)

| Harness | Bootloader skill / command | Code | LLM remains for |
|---------|----------------------------|------|-----------------|
| Test-and-fix | `/test-and-fix` | `scripts/agent_skills/test_and_fix.py` | Root-cause + minimal fix loop; blocker narrative |
| Backlog claim/stage | `backlog-queue`, `/task-claim` | `scripts/agent_skills/backlog_stage.py` | Picking which Ready card; Blocked comment body |
| Wiki scaffold | `docs-wiki`, `/wiki-ingest` | `scripts/agent_skills/wiki_scaffold.py` | Summarize source, page body, placement, cross-links |

## Earlier compiled harnesses

| Harness | Bootloader skill / command | Code | LLM remains for |
|---------|----------------------------|------|-----------------|
| Release bump | `release-bump`, `/release` | `scripts/agent_skills/release_bump.py` | Ambiguous Unreleased / git-history classification when `needs_llm_judgment` |
| Validate implementation | `validate-implementation` | `scripts/agent_skills/validate_implementation.py` | Assigning Verified/Failed when evidence is not a clean command exit |
| PR-ready hygiene | `/pr-ready` | `scripts/agent_skills/pr_ready_checks.py` | Summary / Motivation prose |
| Verification before completion | `verification-before-completion` | `scripts/agent_skills/verification_before_completion.py` | Claim naming; interpreting incomplete output |
| Commit and push | `commit-and-push` | `scripts/agent_skills/commit_and_push.py` | Conventional Commit wording; human must request ship |

## How to run (agent bootloader pattern)

```powershell
# Release: inspect → (optional LLM level) → apply → human commit
python scripts/agent_skills/release_bump.py inspect
python scripts/agent_skills/release_bump.py plan --level minor
python scripts/agent_skills/release_bump.py apply --level minor

# Spec validation scaffolding
python scripts/agent_skills/validate_implementation.py parse path/to/spec.md
python scripts/agent_skills/validate_implementation.py report path/to/spec.md --evidence "AC-1=pytest tests/foo.py -q"

# PR hygiene before narrative
python scripts/agent_skills/pr_ready_checks.py scan --run-tests
python scripts/agent_skills/pr_ready_checks.py skeleton --issue 123 -o .agent/scratch/pr.md

# Test-and-fix: run → parse → (LLM fix) → re-run failed
python scripts/agent_skills/test_and_fix.py run
python scripts/agent_skills/test_and_fix.py run --failed-only
python scripts/agent_skills/test_and_fix.py run -- tests/test_foo.py
python scripts/agent_skills/test_and_fix.py report -o .agent/scratch/test-fix.md

# Backlog claim / stage (requires gh auth)
python scripts/agent_skills/backlog_stage.py claim 123
python scripts/agent_skills/backlog_stage.py claim 45 --repo gallery
python scripts/agent_skills/backlog_stage.py set-stage 123 --stage in_progress

# Wiki ingest glue (prose stays LLM)
python scripts/agent_skills/wiki_scaffold.py frontmatter --type "Report" --title "…" --resource reports/FOO.md
python scripts/agent_skills/wiki_scaffold.py append-index docs/reports/INDEX.md --link FOO.md --desc "…"
python scripts/agent_skills/wiki_scaffold.py append-log --verb ingest --title "…"
python scripts/agent_skills/wiki_scaffold.py lint
```

## Already-compiled skills (do not re-interpret as long SOPs)

- `backup-db` → `scripts/powershell/Backup-Postgres.ps1`
- `windows-keep-awake` → `scripts/powershell/Keep-Awake.ps1`
- `codebase-size-audit` → `scripts/audit/codebase_size_audit.py`
- `backlog-housekeeping` → `scripts/housekeeping_backlog.py`
- `agent-memory` → `scripts/agent-memory/*.py`
- `docs-wiki` lint path → `scripts/okf_lint.py`, `scripts/wiki_lint.py`
- `/test-and-fix` → `scripts/agent_skills/test_and_fix.py`
- `/task-claim` / backlog Stage → `scripts/agent_skills/backlog_stage.py`
- wiki ingest scaffold → `scripts/agent_skills/wiki_scaffold.py`

## Next compilation candidates

1. **wsl-tf-python-runner** — already mostly command recipes; optional thin wrapper for venv + `LD_LIBRARY_PATH` only if agents still rediscover env setup.
2. **docs-wiki query** — keep LLM (retrieval + synthesis); no compile planned.

## Replay / measurement

Honest before/after token comparison needs matching historical scenarios with usage fields. Until those are exported, treat compilation success as:

1. Agent runs the harness first (no rediscovery of paths/semver/changelog structure).
2. LLM turns are limited to the judgment slots listed above.
3. Human gates (commit/push/apply) unchanged.

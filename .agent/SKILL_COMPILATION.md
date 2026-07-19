# Skill compilation audit (Token Shrinker / Vivek Haldar)

Approach: [Compiling an AI agent skill](https://vivekhaldar.com/articles/compiling-an-ai-agent-skill/) — express workflows as natlang skills, run them until the shape crystallizes, then lower stable procedure into code. Keep LLM calls only where semantic judgment matters.

## Profile (2026-07-19)

Source: Cursor `agent-transcripts` for this workspace (~480 jsonl files).

```powershell
python scripts/agent_skills/profile_skill_usage.py
```

| Rank | Workflow | Transcripts | Compilation state |
|-----:|----------|------------:|-------------------|
| 1 | backup-db | 69 | **Compiled** — thin skill → `Backup-Postgres.ps1` |
| 2 | /release | 59 | **Compiled this pass** — `scripts/agent_skills/release_bump.py` |
| 3 | /test-and-fix | 53 | Partial — pytest/ruff commands known; repair loop stays LLM |
| 4 | docs-wiki / wiki-* | 28 | Partial — `okf_lint.py`, `wiki_lint*.py`; ingest/query stay LLM |
| 5 | backlog-queue | 27 | Partial — board contract still judgment-heavy |
| 6 | subagent-review | 21 | Keep LLM — review synthesis is model-shaped |
| 7 | /pr-ready | 18 | **Compiled this pass** — `scripts/agent_skills/pr_ready_checks.py` |
| 8 | imgscore-mcp-debug | 17 | Keep LLM — triage judgment |
| 9 | wsl-tf-python-runner | 17 | Partial — command recipes already deterministic |
| 10 | critical-commit-audit | 14 | Keep LLM — bug-finding is judgment |
| 11 | agent-memory | 13 | **Compiled** — `scripts/agent-memory/*` |
| 12 | codebase-size-audit | 10 | **Compiled** — `scripts/audit/codebase_size_audit.py` |
| 13 | release-bump | 8 | **Compiled this pass** (same harness as /release) |
| 14 | backlog-housekeeping | 8 | **Compiled** — `scripts/housekeeping_backlog.py` |
| 15 | windows-keep-awake | 7 | **Compiled** — `Keep-Awake.ps1` |
| 16 | validate-implementation | 4 | **Compiled this pass** — `scripts/agent_skills/validate_implementation.py` |

## Partition rules

| Owner | Owns |
|-------|------|
| **Code** | Known paths, parsing, semver math, file rewrites, lint/test invocation, forbidden-path scans, report skeletons, retention/prune, wiki lint |
| **LLM** | Ambiguous change classification, AC verdicts from messy evidence, PR narrative, bug hunting, MCP triage, review synthesis |
| **Human** | Commit, push, publish, promote memory, apply housekeeping closes, consequential overrides |

## Compiled harnesses (this pass)

| Harness | Bootloader skill / command | Code | LLM remains for |
|---------|----------------------------|------|-----------------|
| Release bump | `release-bump`, `/release` | `scripts/agent_skills/release_bump.py` | Ambiguous Unreleased / git-history classification when `needs_llm_judgment` |
| Validate implementation | `validate-implementation` | `scripts/agent_skills/validate_implementation.py` | Assigning Verified/Failed when evidence is not a clean command exit |
| PR-ready hygiene | `/pr-ready` | `scripts/agent_skills/pr_ready_checks.py` | Summary / Motivation prose |

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
```

## Already-compiled skills (do not re-interpret as long SOPs)

- `backup-db` → `scripts/powershell/Backup-Postgres.ps1`
- `windows-keep-awake` → `scripts/powershell/Keep-Awake.ps1`
- `codebase-size-audit` → `scripts/audit/codebase_size_audit.py`
- `backlog-housekeeping` → `scripts/housekeeping_backlog.py`
- `agent-memory` → `scripts/agent-memory/*.py`
- `docs-wiki` lint path → `scripts/okf_lint.py`, `scripts/wiki_lint.py`

## Next compilation candidates

1. **/test-and-fix** — wrap fast pytest + failure fingerprinting; keep root-cause/fix as LLM.
2. **docs-wiki ingest** — frontmatter + INDEX/log append helpers; keep prose drafting as LLM.
3. **backlog-queue claim** — `gh` Project item transitions with typed state; keep prioritization as LLM.

## Replay / measurement

Honest before/after token comparison needs matching historical scenarios with usage fields. Until those are exported, treat compilation success as:

1. Agent runs the harness first (no rediscovery of paths/semver/changelog structure).
2. LLM turns are limited to the judgment slots listed above.
3. Human gates (commit/push/apply) unchanged.

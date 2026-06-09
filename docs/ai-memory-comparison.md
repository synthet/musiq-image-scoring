# AI memory tools — comparison and recommendation for Vexlum Scoring

**Date:** 2026-06-08 · **Consolidated:** 2026-06-08
**Source comparison:** [carsteneu/ai-memory-comparison](https://github.com/carsteneu/ai-memory-comparison) (73 systems, 79 features, every ✅ source-backed)
**Live table:** [carsteneu.github.io/ai-memory-comparison](https://carsteneu.github.io/ai-memory-comparison/)

This document evaluates external agent-memory products against the **current** Vexlum Scoring (`image-scoring-backend`) / Driftara Gallery architecture and picks the most suitable approach for agent-driven development across **Claude Code, Cursor, Codex, and Antigravity**.

> **Supersedes** four per-agent drafts (`ai-memory-claude.md`, `ai-memory-codex.md`, `ai-memory-cursor.md`, `ai-memory-antigravity.md`), which were never committed. Three of those four reached the same conclusion (keep `.agent-memory`, treat external tools as opt-in sidecars); the fourth (Antigravity → Mem0 embedded in the app DB) is rejected here for the reasons in [§ Rejected approaches](#rejected-approaches).

---

## Executive summary

| Rank | Choice | Verdict |
|------|--------|---------|
| **1 (recommended)** | **Keep the shipped `.agent-memory` workflow + native Claude `MEMORY.md`** | Best fit today. `.agent-memory/memory.md` is git-tracked, human-promoted **team** memory; Claude's native `MEMORY.md` is **personal** cross-session recall. No migration. |
| **2 (best third-party)** | **[ai-memory](https://github.com/akitaonrails/ai-memory)** (~546★, Rust, MIT) | Closest external match: git-markdown source of truth, MCP **and** lifecycle hooks across Claude/Cursor/Codex/Antigravity, zero-LLM mode, runs outside the app DB. Trial as an **opt-in sidecar only**. Close alternatives: **[Icarus](https://github.com/esaradev/icarus-memory-infra)** (verification-first; the Cursor review's top pick) and **[Origin](https://github.com/7xuanlu/origin)** (richer confidence/contradiction lifecycle). |
| **3 (optional augment)** | **[Midas](https://github.com/vornicx/Midas)** (Python, MIT) | Add semantic recall via MCP over the YAML session corpus without touching `memory.md` governance. **Recall sidecar only.** |

**Do not adopt as primary:** cloud-first platforms (Mem0, Supermemory), proxy/auto-extraction stacks (YesMem), a second Postgres+pgvector service for agent notes (Stash), Claude-only hook-driven auto-capture (claude-mem), or the Antigravity draft's **Mem0-embedded-in-the-app-pgvector** proposal — each conflicts with this repo's human-promote, markdown-canonical, app-DB-separated model.

---

## Why "keep what we have" is the answer, not a cop-out

Claude Code already gives this repo **two** complementary memory layers, and the repo already wired a governance workflow on top of them:

| Layer | Location | Scope | Lifecycle |
|-------|----------|-------|-----------|
| Native auto-memory | `~/.claude/projects/<repo>/memory/MEMORY.md` + per-fact files | **Personal** (this operator, cross-session) | Claude writes/updates fact files; loaded into context each session |
| Approved project memory | `.agent-memory/memory.md` (git-tracked) | **Team-shared** project facts | Log → dream → promote (human-reviewed) |
| Session logs | `.agent-memory/raw-sessions/*.yaml` (gitignored) | Staging | `scripts/agent-memory/log_session.py` |
| Consolidation | `scripts/agent-memory/dream.py` | Proposal only | Deterministic merge, never auto-writes |
| Promotion | `scripts/agent-memory/promote_dream.py` | Human gate | Explicit replace of `memory.md` |
| Agent wiring | `.cursor/rules/agent-memory.mdc`, `.claude/skills/agent-memory`, `/log-session` … `/promote-memory` (Cursor + Claude parity) | Cross-agent | Claude Code + Cursor both drive it |

The constraint is **not** "maximum memory features." It is preserving a **reviewable, git-auditable, team-shared source of truth** that any agent (Claude, Cursor, Codex, Antigravity) can use without silently polluting repo instructions or the application database. Most of the 73 tools in the comparison are optimized for the opposite: automatic, opaque, single-agent capture.

See [technical/AGENT_MEMORY.md](technical/AGENT_MEMORY.md) and [`../.agent-memory/CURSOR_USAGE.md`](../.agent-memory/CURSOR_USAGE.md).

---

## Non-negotiables inferred from repo policy

1. **Human-in-the-loop** — `dream` never overwrites `memory.md` without an explicit promote.
2. **Git-auditable artifacts** — markdown/YAML in-repo beats an opaque vector DB as the canonical store.
3. **Authority stack wins on conflict** — `CLAUDE.md`, `AGENTS.md`, `docs/CANONICAL_SOURCES.md`, and code beat any memory note.
4. **Local-first** — no mandatory cloud memory API or extra always-on service.
5. **Separation from app DB** — agent memory must **not** share the production image-scoring PostgreSQL/pgvector database (schema, migrations, backups stay clean).
6. **Multi-agent, not single-agent-locked** — the repo already runs Cursor/Codex/Antigravity mirrors; a Claude-exclusive store fragments the team.

---

## Evaluation criteria (weighted for this repo)

| Criterion | Weight | Why it matters here |
|-----------|--------|---------------------|
| Human review before canonical write | High | Prevents agent drift into `memory.md` |
| Markdown / git portability | High | PR-reviewable, backs up with the repo |
| Agent integration (MCP / hooks / rules / skills) | High | Primary surface for Claude + Cursor + Codex + Antigravity |
| Low ops overhead | High | Team already runs Postgres for *scoring*, not for agent notes |
| Separation from application DB | High | Keep pgvector schema/migrations/backups clean |
| Multi-agent (not locked to one client) | Medium | Cursor/Codex/Antigravity parity already exists |
| Deterministic / zero-LLM consolidation option | Medium | Matches v1 `dream.py` design; no egress cost |
| Semantic recall / auto-capture | Low–Medium | Nice-to-have; not worth cloud lock-in or a bypassed human gate |

---

## Shortlist from ai-memory-comparison

Filtered to tools with **documented coding-agent support** and **coding-agent intent**, then scored against the criteria above. (Comparison attributes — language, storage, local-first, zero-LLM — taken from the source table.)

### Tier A — structural alignment

#### 1. Shipped `.agent-memory` + native Claude `MEMORY.md` (this repo)

| Aspect | Assessment |
|--------|------------|
| Data model | Native per-fact files (personal) + fixed H2 sections in `memory.md` (team) + YAML session logs |
| Lifecycle | Native: Claude writes personal facts. Team: log → dream (proposal) → promote (human) |
| Agent integration | Skill + slash commands (`/log-session`, `/dream-memory`, `/promote-memory`, `/memory-context`); native auto-memory built in; Cursor + Claude mirrors |
| Search | None over `.agent-memory` (agents `@`/read it or use `context.py`); native memory is auto-loaded |
| Gaps | No semantic recall, no auto session capture into the team store, gallery sibling has no tree |

**Fit:** **Best overall** — zero migration, tested (`tests/test_agent_memory.py`), matches the governance model, uses Claude's native memory for the personal layer it is designed for.

#### 2. [ai-memory](https://github.com/akitaonrails/ai-memory) (~546★, Rust, MIT)

| Aspect | Assessment |
|--------|------------|
| Data model | **Git wiki (markdown)** source of truth + SQLite/FTS5 derived index + optional embeddings |
| Lifecycle | Hooks auto-capture → session compile → `memory_consolidate` (LLM optional; **zero-LLM mode exists**) |
| Agent integration | MCP server **and** lifecycle hooks; documents Claude Code, Codex, Cursor, Gemini, Antigravity |
| Search | FTS5, optional vector RRF, `/web` UI |
| Strengths | Markdown-git truth (aligns with `.agent-memory`), supersession chains, multi-agent handoff narratives, single binary, offline path |
| Risks | Extra daemon/binary; hook auto-capture can bypass an explicit human promote unless disciplined |

**Fit:** **Best third-party** — same markdown-git philosophy as `.agent-memory`, broadest agent surface (MCP + hooks). Trial it feeding candidates into `raw-sessions/`, **not** writing `memory.md` directly.

#### 3. [Icarus](https://github.com/esaradev/icarus-memory-infra) (~288★, Python, MIT)

| Aspect | Assessment |
|--------|------------|
| Data model | Three layers: working → session archive → shared wiki (markdown) |
| Lifecycle | `memory_write` → optional `memory_verify` / supersede / rollback (non-destructive) |
| Agent integration | Documented `.cursor/mcp.json` snippet; MCP |
| Search | Keyword, embedding (optional), hybrid RRF |
| Strengths | Provenance, verification, contradiction tools, git-friendly `.icarus/` layout — philosophy almost matches log → dream → `memory.md` with human verify |
| Risks | Smaller community; no background auto-extraction |

**Fit:** **Best third-party if migrating off the custom scripts** (the Cursor review's pick). Verification-first lifecycle (`memory_verify`/rollback/lineage ≈ promote + archive).

#### 4. [Origin](https://github.com/7xuanlu/origin) (~31★, Rust)

| Aspect | Assessment |
|--------|------------|
| Data model | Local libSQL/FTS5 daemon, git-versioned memories, distilled wiki pages |
| Lifecycle | Confidence/review semantics, contradiction surfacing, source-backed pages |
| Agent integration | MCP; Codex/Cursor/Claude |
| Risks | Daemon + database is more moving parts than `.agent-memory` needs today |

**Fit:** Pick over ai-memory **only if** you want built-in confidence/contradiction lifecycle in a fully automated daemon.

### Tier B — strong products, poor fit for this repo

| System | Stars | Why not primary here |
|--------|-------|----------------------|
| [claude-mem](https://github.com/thedotmack/claude-mem) | ~81k | Claude-native and hook-first, but auto-capture competes with native `MEMORY.md`, is Claude-only (breaks Cursor/Codex/Antigravity parity), and is not the committed-markdown, human-promote model. |
| [YesMem](https://github.com/carsteneu/yesmem) | ~13 | Highest feature coverage in the comparison, but **maintained by the comparison's author** (disclosed); proxy + 70+ MCP tools + auto-extraction conflicts with deterministic promote. |
| [Stash](https://github.com/alash3al/stash) | ~710 | Postgres + pgvector + multi-stage LLM consolidation — **duplicates the app DB stack** with no markdown canonical layer. |
| [Mem0](https://github.com/mem0ai/mem0) / [Supermemory](https://github.com/supermemoryai/supermemory) | 58k / 26k | Cloud/freemium bias; weak git-markdown audit story for repo-specific working rules. Self-host adds a service for no governance gain. |
| [mcp-memory-service](https://github.com/doobidoo/mcp-memory-service) | ~1.9k | Mature and broad, but SQLite-vec/Milvus/Cloudflare surface + auto-consolidation fights the human promote gate. Overpowered for this repo. |
| [gbrain](https://github.com/garrytan/gbrain) | ~21.5k | Excellent federated org "team brain," but oriented to multi-org memory, not a twin-repo Python/Electron project. |

### Tier C — useful as optional augment only

#### [Midas](https://github.com/vornicx/Midas) (Python, MIT)

- **$0 LLM** at ingest/query; hybrid BM25 + vector; supersede chains; MCP server documented (Claude Code + Cursor).
- Stores in **SQLite**, not git markdown — use as a **recall sidecar**, never the canonical policy store.
- Strong retrieval benchmarks (LongMemEval R@k 0.95) if the YAML session corpus grows large.

---

## Recommendation

### Primary: keep `.agent-memory` + native Claude `MEMORY.md`

None of the 73 external tools beats the **already-shipped** setup for this architecture because:

1. **Governance is encoded in repo policy** — promote-only writes, section schema, and "prefer `CLAUDE.md`/`AGENTS.md` on conflict" are first-class here, not bolt-ons.
2. **The two layers are already right** — Claude's native `MEMORY.md` covers personal cross-session recall; `.agent-memory/memory.md` covers reviewed, team-shared project facts. Most tools collapse both into one opaque auto-captured store.
3. **No new moving parts** — no second database, daemon, or cloud account for memory; app pgvector stays clean.
4. **Integration is complete** — skill, slash commands, Claude + Cursor mirrors, tests.

The five consensus points, as policy:

1. **Canonical stays in-repo, unchanged.** `.agent-memory/memory.md` (team, human-promoted) + native `MEMORY.md` (personal). No migration.
2. **External tools are capture/search infrastructure only.** They may feed candidates into `.agent-memory/raw-sessions/*.yaml`, but must **never** write `memory.md` directly or bypass `promote_dream.py`.
3. **Best third-party (if/when trialed): ai-memory** — Icarus and Origin are close alternatives.
4. **Optional augment: Midas** for semantic recall once the session corpus grows — recall sidecar only.
5. **Explicit rejections** — see [§ Rejected approaches](#rejected-approaches).

**Integration shape** — any sidecar must respect the existing gate:

```text
Claude/Cursor/Codex/Antigravity session
  → sidecar (ai-memory / Midas) captures & searches local session context
  → selected findings exported as candidates → .agent-memory/raw-sessions/*.yaml
  → scripts/agent-memory/dream.py proposes a memory.md update
  → human review
  → scripts/agent-memory/promote_dream.py updates .agent-memory/memory.md
```

**Do not** let any sidecar write `.agent-memory/memory.md` directly.

**Suggested extensions (still within the current model)**

| Gap | Low-cost follow-up |
|-----|-------------------|
| Gallery sibling has no memory tree | Copy the `.agent-memory/` pattern to `image-scoring-gallery`, or share a `memory.md` for cross-repo rules |
| No semantic recall over many sessions | Optional Midas MCP; keep `memory.md` as the approved surface only |
| Manual session logging | Optional Claude/Cursor `Stop`/`SessionEnd` hook → append to `raw-sessions/` (never auto-promote) |
| Transcript import | One-off script: parse agent transcripts → YAML session candidates for `dream.py` |

---

## Decision matrix (summary)

| System | Human gate | Git markdown SOtT | Agent integration | Multi-agent | Ops cost | Match |
|--------|------------|-------------------|-------------------|-------------|----------|-------|
| **`.agent-memory` + native `MEMORY.md`** | ✅ Promote | ✅ `memory.md` | ✅ Built-in + skills | ✅ | None | **9/10** |
| **ai-memory** | ⚠️ Hook auto-write | ✅ Git wiki | ✅ MCP + hooks | ✅ | Medium (binary) | **7/10** |
| **Icarus** | ✅ Verify tools | ✅ Wiki markdown | ✅ MCP docs | ✅ | Low (pip) | **8/10** |
| **Origin** | ✅ Confidence/review | ✅ Wiki pages | ✅ MCP | ✅ | Medium (daemon) | **7/10** |
| **Midas** | ⚠️ MCP only | ❌ SQLite | ✅ MCP | ✅ | Low | **6/10** (augment) |
| **claude-mem** | ⚠️ Auto-capture | ❌ | ✅ Hook-native | ❌ Claude-only | Low–med | **5/10** |
| **YesMem** | ⚠️ Auto pipeline | Partial | ✅ | ✅ | Medium–high | **5/10** |
| **Stash** | ❌ Auto consolidate | ❌ Postgres | ✅ MCP | ✅ | High (+Postgres) | **4/10** |
| **Mem0 / Supermemory** | ❌ Cloud API | ❌ | ✅ MCP | Partial | Cloud | **3/10** |

---

## Rejected approaches

The Tier-B table above gives the per-tool rationale. One draft warrants an explicit rebuttal because it was a standalone recommendation:

### Why not Mem0 embedded in the app (the Antigravity draft)

The Antigravity review recommended embedding **Mem0** directly into the FastAPI backend and pointing it at the existing docker-compose **PostgreSQL + pgvector** instance, exposed through `is-be-mcp` as `memory.store` / `memory.recall`. Each load-bearing claim violates a non-negotiable:

| Antigravity claim | Violated non-negotiable |
|-------------------|-------------------------|
| "Reuse the existing docker-compose Postgres/pgvector — single source of truth for scoring data *and* agent memory." | **#5 Separation from app DB** — pollutes the scoring schema, migrations, and backups with agent notes; the opposite of what we want. |
| SDK auto-store / auto-recall with entity extraction; no promote step. | **#1 Human-in-the-loop** — bypasses `promote_dream.py`; agents would silently mutate canonical memory. |
| Vector store is the canonical memory. | **#2 Git-auditable markdown SOtT** — no PR-reviewable, grep-able artifact. |
| "Designed partially as a cloud service" (self-host supported). | **#4 Local-first** — cloud/freemium bias for no governance gain. |

Mem0 is a strong product; it is simply the wrong shape for a repo whose whole memory design is human-promoted, markdown-canonical, and DB-separated. If semantic recall is the actual goal, **Midas** (Tier C) delivers it as a sidecar without touching the app DB or the promote gate.

---

## Next steps (queued as backlog issues)

1. **(p2)** Trial **ai-memory** as an opt-in capture/search sidecar feeding `.agent-memory/raw-sessions/*.yaml`; must not write `memory.md` or bypass `promote_dream.py`.
2. **(p3)** Optional **Midas** MCP for semantic recall over the YAML session corpus (recall sidecar only).
3. **(p3)** Copy the `.agent-memory/` pattern to **image-scoring-gallery** (cross-repo; gallery has no memory tree).
4. **(p3)** Optional Claude/Cursor `Stop`/`SessionEnd` hook → append a candidate to `raw-sessions/` (never auto-promote).

---

## What this is not

- **Not a replacement for `CLAUDE.md`, `AGENTS.md`, rules, or skills** — memory holds durable *learnings*; canonical contracts and commands stay in the agent-sdlc files.
- **Not the application database** — PostgreSQL + pgvector remains for images, embeddings, and jobs only.
- **Not the backlog** — the GitHub Project board owns task state.

---

## Disclosure

The ai-memory-comparison maintainer also authors [YesMem](https://github.com/carsteneu/yesmem), which scores highest on raw feature coverage. This recommendation does **not** select YesMem as the primary fit, because its proxy complexity and auto-extraction conflict with this repo's human-promote, markdown-canonical model.

## Sources

- [AI Memory Comparison README](https://github.com/carsteneu/ai-memory-comparison/blob/main/README.md), [criteria](https://github.com/carsteneu/ai-memory-comparison/blob/main/CRITERIA.md), and [live table](https://carsteneu.github.io/ai-memory-comparison/)
- [ai-memory](https://github.com/akitaonrails/ai-memory) · [Icarus](https://github.com/esaradev/icarus-memory-infra) · [Origin](https://github.com/7xuanlu/origin) · [Midas](https://github.com/vornicx/Midas) · [claude-mem](https://github.com/thedotmack/claude-mem)
- Local agent memory workflow: [technical/AGENT_MEMORY.md](technical/AGENT_MEMORY.md) · operator guide: [`../.agent-memory/CURSOR_USAGE.md`](../.agent-memory/CURSOR_USAGE.md)

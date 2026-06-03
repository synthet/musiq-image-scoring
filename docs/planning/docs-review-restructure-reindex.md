# Documentation review, restructure, cleanup, and reindex

**Status:** planned  
**Purpose:** Review the `docs/` tree (~106 files), restructure overlapping content, remove deprecated VILA references, and consolidate to a single authoritative index with correct cross-references.  
**Conventions:** [WIKI_SCHEMA.md](../WIKI_SCHEMA.md) · [CANONICAL_SOURCES.md](../CANONICAL_SOURCES.md)

---

## Current state summary

The `docs/` folder contains **106 files** across multiple categories. [INDEX.md](../INDEX.md) provides a comprehensive index with an audit report; [README.md](../README.md) is a competing index that still promotes deprecated VILA docs as the primary "Where do I start" path. Several documents are missing from both indexes, and many cross-references point to deprecated or incorrect content.

---

## 1. Restructure

### 1.1 Consolidate duplicate indexes

- **Problem:** Two index files ([INDEX.md](../INDEX.md) and [README.md](../README.md)) with overlapping but inconsistent content. README.md promotes VILA as the starting point; INDEX.md has audit notes but is not the canonical entry.
- **Action:** Make [INDEX.md](../INDEX.md) the single source of truth. Convert [README.md](../README.md) to a thin redirect/wrapper that points to INDEX.md and the project root README.

### 1.2 Archive deprecated content

Move to `docs/archive/`:

| Source | Destination |
|--------|-------------|
| `docs/vila/` (entire folder) | `docs/archive/vila/` |
| `technical/MODEL_FALLBACK_MECHANISM.md` | `archive/MODEL_FALLBACK_MECHANISM.md` |
| `technical/TRIPLE_FALLBACK_SYSTEM.md` | `archive/TRIPLE_FALLBACK_SYSTEM.md` |
| `reports/UNCOMMITTED_CHANGES_ANALYSIS.md` | `archive/` (dated 2025-01-29) |

### 1.3 Merge overlapping documents

| Files | Action |
|-------|--------|
| [project-structure.md](../architecture/project-structure.md) + [FOLDER_STRUCTURE.md](../technical/FOLDER_STRUCTURE.md) | Merge into single `technical/PROJECT_STRUCTURE.md`. FOLDER_STRUCTURE is outdated (references `musiq/`; current layout uses `modules/`). Keep PROJECT_STRUCTURE as base, add any unique FOLDER_STRUCTURE content, then delete FOLDER_STRUCTURE. |
| [DOCKER_WSL2_SETUP.md](../DOCKER_WSL2_SETUP.md) + [DOCKER_SETUP.md](../technical/DOCKER_SETUP.md) | Compare scope; merge into one (likely `guides/setup/DOCKER_SETUP.md`), remove duplicate. |
| [GPU_IMPLEMENTATION_SUMMARY.md](../guides/setup/GPU_IMPLEMENTATION_SUMMARY.md) + [README_gpu.md](../guides/setup/README_gpu.md) | Merge into single `setup/GPU_SETUP.md` with clear sections. |
| Gallery README trio under `docs/gallery/` | Consolidate into 2 files: `GALLERY_README.md` (overview + features) and `GALLERY_CREATION_GUIDE.md` (step-by-step). |

### 1.4 Relocate misplaced files

| File | New location | Reason |
|------|--------------|--------|
| `getting-started/QUICK_REFERENCE.md` | `gallery/QUICK_REFERENCE.md` | Content is gallery creation reference, not general scoring. |
| `docs/TEST_STATUS.md` | `docs/testing/TEST_STATUS.md` | Co-locate with [WSL_TESTS.md](../testing/WSL_TESTS.md) per [DOCUMENTATION_ISSUES.md](../testing/DOCUMENTATION_ISSUES.md). |
| `docs/DOCKER_WSL2_SETUP.md` | `docs/guides/setup/` | Belongs with other setup docs. |

---

## 2. Cleanup

### 2.1 Remove/update VILA references

Files to update (remove or qualify VILA mentions):

| File | Change |
|------|--------|
| [RAW_PROCESSING_GUIDE.md](../technical/RAW_PROCESSING_GUIDE.md) | Replace "MUSIQ and VILA models" with "MUSIQ and LIQE models". |
| [WSL_WRAPPER_VERIFICATION.md](../guides/setup/WSL_WRAPPER_VERIFICATION.md) | Update title and content to "MUSIQ + LIQE processing"; remove VILA-specific verification. |
| [MODEL_SOURCE_TESTING.md](../technical/MODEL_SOURCE_TESTING.md) | Add deprecation note for VILA section; keep for users who re-enable it. |
| Gallery creation instructions | Remove "Kaggle account for VILA model" requirement. |
| [MODEL_INPUT_SPECIFICATIONS.md](../technical/MODEL_INPUT_SPECIFICATIONS.md) | Keep VILA parameter mention only if still used; otherwise remove. |
| [WINDOWS_NATIVE_WEBUI_PLAN.md](setup/WINDOWS_NATIVE_WEBUI_PLAN.md) | Update "no VILA" to "no LIQE" or clarify current model stack. |
| [technical-summary.md](../architecture/technical-summary.md) | Remove Related Documents links to MODEL_FALLBACK_MECHANISM and TRIPLE_FALLBACK_SYSTEM; add link to WEIGHTED_SCORING_STRATEGY. |
| [CODE_DESIGN_REVIEW.md](../technical/CODE_DESIGN_REVIEW.md) | Update "MUSIQ, LIQE, VILA" to "MUSIQ, LIQE". |
| [MODELS_SUMMARY.md](../technical/MODELS_SUMMARY.md) | Move VILA to "Deprecated/Legacy" section. |

### 2.2 Fix stale content

| File | Action |
|------|--------|
| [project/TODO.md](../project/TODO.md) | Review; if all items complete or obsolete, add "Last verified" date or archive. |
| TEST_STATUS.md | Re-run `pytest -m wsl -ra` and update pass/fail/skip counts; fix or remove stale bug notes per [DOCUMENTATION_ISSUES.md](../testing/DOCUMENTATION_ISSUES.md). |

### 2.3 Resolve WEIGHTED_SCORING vs current_model_weights overlap

- Compare [WEIGHTED_SCORING_STRATEGY.md](../technical/WEIGHTED_SCORING_STRATEGY.md) and [current_model_weights.md](../reference/models/current_model_weights.md).
- If redundant: keep WEIGHTED_SCORING_STRATEGY as canonical; add cross-link or merge.
- If complementary: add cross-links in both.

---

## 3. Reindex

### 3.1 Add missing documents to INDEX.md

Documents not currently in INDEX.md (embedding apps, DB refactor plans, design mockups, API contract, proposals, reports, testing docs, CODE_DESIGN_REVIEW).

### 3.2 Add `.agent/` section

INDEX.md and README should reference [AGENTS.md](../../AGENTS.md) and the `.agent/` folder (MCP reference, workflows, ai_edit_spec).

### 3.3 Update "Getting Help" and entry points

- Replace "VILA_QUICK_START" with "INSTRUCTIONS_RUN_SCORING" or "README_simple" as primary "Where do I start".
- Ensure INDEX.md "Getting Started" links to project root README and CHANGELOG.

### 3.4 Fix cross-references

- [WSL_TESTS.md](../testing/WSL_TESTS.md): requirements file reference, optional deps, link to TEST_STATUS.md.
- Clarify "Docs index" link target: use `docs/INDEX.md` explicitly where appropriate.

---

## 4. Implementation order

1. **Archive** deprecated content (vila/, fallback docs, UNCOMMITTED_CHANGES_ANALYSIS).
2. **Merge** overlapping docs (PROJECT_STRUCTURE+FOLDER_STRUCTURE, Docker, GPU, Gallery).
3. **Relocate** misplaced files (QUICK_REFERENCE, TEST_STATUS, DOCKER).
4. **Update** VILA references across all affected files.
5. **Reindex** INDEX.md with new structure, add missing docs, add `.agent` section.
6. **Simplify** docs/README.md to redirect to INDEX.md.
7. **Fix** cross-references (TECHNICAL_SUMMARY, WSL_TESTS, PROJECT_STRUCTURE).
8. **Update** TEST_STATUS.md after re-running tests.

---

## 5. Out of scope (optional follow-ups)

- PDF files in docs/ — keep as-is.
- Obsidian config (`.obsidian/`) — leave unchanged.
- Design mockup Python/HTML files — index but do not restructure.
- Deep-research-report.md, proposals_old.md — consider archiving in a later pass.

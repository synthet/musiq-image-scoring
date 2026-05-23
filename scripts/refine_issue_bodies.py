#!/usr/bin/env python3
"""Refine GitHub issue bodies to match current codebase (backlog inventory)."""
from __future__ import annotations

import subprocess
import sys
import time

BACKEND = "synthet/image-scoring-backend"
GALLERY = "synthet/image-scoring-gallery"

OBSOLETE_BANNER = """> **Status: obsolete** — {reason} Kept for historical tracking.

"""

BOOTSTRAP_FOOTER = "_Bootstrapped from legacy `TODO.md` on 2026-04-28._"


def gh_run(*args: str) -> None:
    res = subprocess.run(["gh", *args], capture_output=True, text=True, encoding="utf-8")
    if res.returncode != 0:
        raise RuntimeError(f"gh {' '.join(args)}\n{res.stderr}")


def get_body(repo: str, number: int) -> str:
    res = subprocess.run(
        ["gh", "issue", "view", str(number), "--repo", repo, "--json", "body", "-q", ".body"],
        capture_output=True, text=True, encoding="utf-8",
    )
    return (res.stdout or "").strip()


def set_body(repo: str, number: int, body: str) -> None:
    gh_run("issue", "edit", str(number), "--repo", repo, "--body", body)
    time.sleep(0.4)


def strip_footer(body: str) -> str:
    if BOOTSTRAP_FOOTER in body:
        body = body.replace("\n---\n" + BOOTSTRAP_FOOTER, "").replace(BOOTSTRAP_FOOTER, "")
    return body.strip()


def ensure_banner(body: str, reason: str) -> str:
    body = strip_footer(body)
    banner = OBSOLETE_BANNER.format(reason=reason)
    if "**Status: obsolete**" in body:
        return body
    return banner + body


def main() -> int:
    print("Refining issue bodies...")

    # Epic #200 RAW checklist in body
    raw_epic_body = """## Goal
Manual QA checklist for RAW preview via `/api/raw-preview` and operator/React surfaces.

## Checklist (sub-issues)
- [ ] #104 — NEF → Extract Preview → canvas renders
- [ ] #105 — JPG → warning message shown
- [ ] #106 — No image selected → error message
- [ ] #107 — No JS errors on page load
- [ ] #108 — Large files (>50MB) → progress bar works

## Canonical references
- `modules/api.py` — raw-preview routes
- `docs/features/implemented/` — RAW/export notes
- Primary product UI: React `/ui/`; operator Gradio at `/app`

## Sub-issues
Linked via GitHub sub-issues under this epic (#200).
"""
    set_body(BACKEND, 200, raw_epic_body)

    # Phase 4d
    set_body(
        BACKEND,
        103,
        """## Source
Database keyword normalization — Phase 4d (v7.0 target)

## Description
Drop the legacy `IMAGES.KEYWORDS` column after all readers use `IMAGE_KEYWORDS` / `KEYWORDS_DIM`.

**Blocker resolved:** Gallery read-path cutover completed ([#72](https://github.com/synthet/image-scoring-gallery/issues/72) closed).

## Canonical references
- [PHASE4_KEYWORDS_DEPRECATION.md](docs/planning/database/PHASE4_KEYWORDS_DEPRECATION.md)
- [AGENT_COORDINATION.md](docs/technical/AGENT_COORDINATION.md)
- `modules/db_postgres.py` — schema authority

## Acceptance criteria
- [ ] No production reader depends on `IMAGES.KEYWORDS`
- [ ] Alembic migration drops column idempotently
- [ ] Gallery `electron/db.ts` queries use normalized tables only
""",
    )

    set_body(
        BACKEND,
        111,
        """## Source
Database Phase 5 — PostgreSQL optimizations

## Description
Consolidate embedding storage into `image_embeddings` SSOT, add integrity constraints (job/phase status), apply JSONB where appropriate.

## Canonical references
- [POSTGRES_SCHEMA_OPTIMIZATIONS.md](docs/planning/database/POSTGRES_SCHEMA_OPTIMIZATIONS.md)
- [DB_SCHEMA.md](docs/technical/DB_SCHEMA.md)
- Primary engine: **PostgreSQL + pgvector** (not Firebird)

## Acceptance criteria
- [ ] Embeddings single source of truth documented and enforced
- [ ] Job/phase integrity constraints in Alembic
- [ ] Gallery contract updated if read shapes change
""",
    )

    set_body(
        GALLERY,
        76,
        """## Source
Ongoing cross-repo API discipline (supersedes closed #71 notification task)

## Description
When adding or changing backend REST endpoints, update gallery integration in the same PR or linked PR:
- `electron/apiService.ts`
- `electron/apiTypes.ts` or generated OpenAPI types (`npm run generate:api-types`)
- `electron/db.ts` if SQL shapes change

## Canonical references
- Backend [API_CONTRACT.md](https://github.com/synthet/image-scoring-backend/blob/main/docs/technical/API_CONTRACT.md)
- [AGENT_COORDINATION.md](docs/technical/AGENT_COORDINATION.md)
- `npm run contract:check` in this repo

## Acceptance criteria
- [ ] New endpoints reflected in apiService + types before merge
""",
    )

    obsolete_reasons = {
        117: "Superseded by React Embedding Atlas (`/ui/`) and REST `/api/similarity/*`. ",
        102: "Operator-only Gradio `/app` scope; primary product UI is React `/ui/`. See `docs/features/planned/ux-ui-implementation-plan.md`. ",
        124: "Icebox: video scoring not on current roadmap. ",
        125: "Icebox: real-time camera assessment. ",
        126: "Icebox: mobile app. ",
        127: "Icebox: deployable web service packaging. ",
        128: "Icebox: Lightroom Classic plugin. ",
        129: "Icebox: Capture One workflow. ",
        130: "Icebox: Photo Mechanic integration. ",
    }
    for num, reason in obsolete_reasons.items():
        body = ensure_banner(get_body(BACKEND, num), reason)
        set_body(BACKEND, num, body)

    # RAW child issues — point to epic
    raw_children = {
        104: "NEF → Extract Preview → canvas renders (`/api/raw-preview`).",
        105: "JPG selection shows not-a-RAW warning.",
        106: "No image selected shows error message.",
        107: "No JS errors on page load (DevTools).",
        108: "Files >50MB show progress without UI freeze.",
    }
    for num, desc in raw_children.items():
        set_body(
            BACKEND,
            num,
            f"""## Source
Epic: #200 RAW preview verification

## Description
{desc}

## Canonical references
- `/api/raw-preview` in `modules/api.py`
- React `/ui/` or operator `/app` as applicable

## Parent epic
Tracked under [#200](https://github.com/synthet/image-scoring-backend/issues/200).
""",
        )

    # Architecture issues — append canonical block if missing
    arch_footer = """

## Canonical references
- [CANONICAL_SOURCES.md](docs/CANONICAL_SOURCES.md)
- [AGENT_COORDINATION.md](docs/technical/AGENT_COORDINATION.md)
- Primary DB: PostgreSQL + pgvector; legacy `database.engine=firebird` maps to Postgres with warning.
"""
    for num in range(169, 176):
        body = strip_footer(get_body(BACKEND, num))
        if "CANONICAL_SOURCES.md" not in body:
            body += arch_footer
        set_body(BACKEND, num, body)

    print("Done.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

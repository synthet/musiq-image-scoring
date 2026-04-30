"""Bootstrap GitHub Issues from the legacy TODO.md and add them to the kanban Project.

One-time migration. Idempotent if re-run via title-search guard:
  gh issue list --search "in:title \"<title>\"" — skip if found.

Project: https://github.com/users/synthet/projects/1  (number=1, owner=synthet)
Stage field id: PVTSSF_lAHOAFXgIs4BWC3czhRaNZ0
  Backlog=83b7a780  Ready=ddaf7773  Claimed=1cc70f0b  In Progress=8b22e18e
  Blocked=4bbe5dd0  Review=cb723acb  Done=73062c96
Project node id: PVT_kwHOAFXgIs4BWC3c
"""
from __future__ import annotations

import json
import subprocess
import sys
from dataclasses import dataclass, field

PROJECT_NUMBER = 1
PROJECT_OWNER = "synthet"
PROJECT_NODE_ID = "PVT_kwHOAFXgIs4BWC3c"
STAGE_FIELD_ID = "PVTSSF_lAHOAFXgIs4BWC3czhRaNZ0"
STAGE_BACKLOG = "83b7a780"
STAGE_READY = "ddaf7773"

BACKEND = "synthet/image-scoring-backend"
GALLERY = "synthet/image-scoring-gallery"


@dataclass
class Issue:
    title: str
    repo: str
    labels: list[str]
    body: str
    stage: str = STAGE_BACKLOG  # P0 items overridden to STAGE_READY


def _gh(*args: str, capture: bool = True) -> str:
    res = subprocess.run(
        ["gh", *args],
        capture_output=capture,
        text=True,
        check=False,
        encoding="utf-8",
    )
    if res.returncode != 0:
        sys.stderr.write(f"FAILED: gh {' '.join(args)}\n{res.stderr}\n")
        raise SystemExit(res.returncode)
    return (res.stdout or "").strip()


def _exists(repo: str, title: str) -> str | None:
    """Return existing issue URL if a same-titled open/closed issue already exists."""
    out = _gh(
        "issue", "list",
        "--repo", repo,
        "--state", "all",
        "--search", f'in:title "{title}"',
        "--json", "number,title,url",
        "--limit", "5",
    )
    for it in json.loads(out or "[]"):
        if it["title"].strip() == title.strip():
            return it["url"]
    return None


def file_issue(issue: Issue) -> str:
    existing = _exists(issue.repo, issue.title)
    if existing:
        print(f"  SKIP (exists): {issue.title} -> {existing}")
        url = existing
    else:
        url = _gh(
            "issue", "create",
            "--repo", issue.repo,
            "--title", issue.title,
            "--body", issue.body,
            *(arg for lbl in issue.labels for arg in ("--label", lbl)),
        ).splitlines()[-1]
        print(f"  CREATED: {issue.title} -> {url}")

    add_out = _gh(
        "project", "item-add", str(PROJECT_NUMBER),
        "--owner", PROJECT_OWNER,
        "--url", url,
        "--format", "json",
    )
    item_id = json.loads(add_out)["id"]

    _gh(
        "project", "item-edit",
        "--id", item_id,
        "--field-id", STAGE_FIELD_ID,
        "--project-id", PROJECT_NODE_ID,
        "--single-select-option-id", issue.stage,
    )
    return url


def make_issue(title: str, repo: str, markers: list[str], priority: str,
               type_label: str, source: str, description: str,
               docs: list[str] | None = None, cross_repo: bool = False,
               ready: bool = False) -> Issue:
    labels: list[str] = [f"priority:{priority}", f"type:{type_label}"]
    for m in markers:
        labels.append(f"area:{m}")
    if cross_repo:
        labels.append("cross-repo")

    body_lines = [
        "## Source",
        source,
        "",
        "## Markers",
        " ".join(f"`[{m}]`" for m in markers) if markers else "(none)",
        "",
        "## Description",
        description,
    ]
    if docs:
        body_lines += ["", "## Related docs"]
        body_lines += [f"- {d}" for d in docs]
    if cross_repo:
        body_lines += [
            "",
            "## Cross-repo",
            "Coordinated change across `image-scoring-backend` and `image-scoring-gallery`.",
            "Track the counterpart issue via the `cross-repo` label.",
        ]
    body_lines += [
        "",
        "---",
        "_Bootstrapped from legacy `TODO.md` on 2026-04-28._",
    ]

    return Issue(
        title=title,
        repo=repo,
        labels=labels,
        body="\n".join(body_lines),
        stage=STAGE_READY if ready else STAGE_BACKLOG,
    )


# Each entry: (title, repo, markers, priority, type, source, description, docs, cross_repo, ready)
ISSUES = [
    # ── P0 — promoted to Ready ──────────────────────────────────────────────
    make_issue(
        title="Pipeline UX: Quick Start panel, Stop/Skip confirmation rows, inline action microcopy",
        repo=BACKEND,
        markers=["gradio"],
        priority="p0",
        type_label="feature",
        source="High Priority › Operator UI (plans)",
        description="Implement the P0 operator-UI polish per plan: Quick Start panel, Stop/Skip confirmation rows, inline action microcopy.",
        docs=["docs/features/planned/ux-ui-implementation-plan.md"],
        ready=True,
    ),
    make_issue(
        title="Notify image-scoring-gallery on API/schema changes (apiService.ts, db.ts)",
        repo=GALLERY,
        markers=["electron", "db"],
        priority="p0",
        type_label="chore",
        source="High Priority › API & Embedding (cross-repo)",
        description="When backend API or schema changes, propagate to gallery: update `apiService.ts`, `db.ts`, and `apiTypes.ts`. Drives the cross-repo sync discipline.",
        docs=["docs/technical/AGENT_COORDINATION.md (in image-scoring-backend)"],
        cross_repo=True,
        ready=True,
    ),
    make_issue(
        title="DB Phase 4d: Hard deprecation — remove IMAGES.KEYWORDS legacy column (v7.0)",
        repo=BACKEND,
        markers=["python", "db"],
        priority="p0",
        type_label="refactor",
        source="Database & Migration › Schema refactor — keywords / metadata",
        description="Final phase of keyword normalization: drop the `IMAGES.KEYWORDS` legacy column. Targeted for v7.0 (July 2026). Requires gallery read-path cutover first.",
        docs=[
            "docs/planning/database/PHASE4_STATUS_SUMMARY.md",
            "docs/planning/database/PHASE4_KEYWORDS_DEPRECATION.md",
        ],
        ready=True,
    ),
    make_issue(
        title="DB Phase 4 coordinated: gallery read-path cutover to normalized keywords",
        repo=GALLERY,
        markers=["electron", "db"],
        priority="p0",
        type_label="refactor",
        source="Database & Migration › Schema refactor — keywords / metadata (cross-repo)",
        description="Update gallery query/read paths to use the normalized `IMAGE_KEYWORDS` / `KEYWORDS_DIM` schema before backend Phase 4d removes the legacy column.",
        docs=["docs/technical/AGENT_COORDINATION.md (in image-scoring-backend)"],
        cross_repo=True,
        ready=True,
    ),

    # ── P1 — verification debt + embedding wiring + Phase 5 ────────────────
    make_issue(
        title="In-browser RAW preview test: NEF → Extract Preview → canvas renders",
        repo=BACKEND, markers=["gradio"], priority="p1", type_label="test",
        source="High Priority › Testing & Verification",
        description="Manual verification: select a NEF, click Extract Preview, confirm canvas renders.",
    ),
    make_issue(
        title="In-browser RAW preview test: JPG → warning message shown",
        repo=BACKEND, markers=["gradio"], priority="p1", type_label="test",
        source="High Priority › Testing & Verification",
        description="Manual verification: select a JPG, confirm the 'not a RAW' warning is shown.",
    ),
    make_issue(
        title="In-browser RAW preview test: no image selected → error message",
        repo=BACKEND, markers=["gradio"], priority="p1", type_label="test",
        source="High Priority › Testing & Verification",
        description="Manual verification: trigger Extract Preview with no image selected and confirm the error message.",
    ),
    make_issue(
        title="In-browser RAW preview test: no JS errors on page load",
        repo=BACKEND, markers=["gradio"], priority="p1", type_label="test",
        source="High Priority › Testing & Verification",
        description="Open the RAW preview page, check DevTools console for JS errors.",
    ),
    make_issue(
        title="In-browser RAW preview test: large files (>50MB) → progress bar works",
        repo=BACKEND, markers=["gradio"], priority="p1", type_label="test",
        source="High Priority › Testing & Verification",
        description="Manual verification with >50MB RAW: progress bar updates, no UI freeze.",
    ),
    make_issue(
        title="AI culling: Lightroom Cloud import — verify ratings and labels",
        repo=BACKEND, markers=["python", "gradio"], priority="p1", type_label="test",
        source="High Priority › Testing & Verification",
        description="End-to-end check: run AI culling, import resulting XMP into Lightroom Cloud, confirm ratings and color labels apply.",
    ),
    make_issue(
        title="AI culling: pick/reject flags — verify Lightroom recognition",
        repo=BACKEND, markers=["python", "gradio"], priority="p1", type_label="test",
        source="High Priority › Testing & Verification",
        description="Confirm Lightroom honors `xmpDM:pick` and `xmpDM:good` flags written by the culling pipeline.",
    ),
    make_issue(
        title="Embedding/UI end-to-end wiring: gallery IPC/WebSocket bridge + Gradio/Electron flows",
        repo=GALLERY,
        markers=["electron", "gradio"],
        priority="p1",
        type_label="feature",
        source="Medium Priority › Clustering & Embeddings (cross-repo)",
        description="Wire the bidirectional IPC/WebSocket bridge between gallery and backend per the embedding integration plan.",
        docs=["docs/features/planned/embeddings/EMBEDDING_APP_08_GRADIO_INTEGRATION_PLAN.md (in image-scoring-backend)"],
        cross_repo=True,
    ),
    make_issue(
        title="Pipeline mode selector + headless lifecycle + INTEGRATION_QUEUE table",
        repo=GALLERY,
        markers=["electron", "db"],
        priority="p1",
        type_label="feature",
        source="Medium Priority › Clustering & Embeddings",
        description="Gallery-side pipeline-mode selector with headless lifecycle support; backend exposes/owns the `INTEGRATION_QUEUE` table coordination.",
        cross_repo=True,
    ),
    make_issue(
        title="DB Phase 5: PostgreSQL optimizations — embeddings SSOT, integrity constraints, JSONB",
        repo=BACKEND,
        markers=["python", "db"],
        priority="p1",
        type_label="refactor",
        source="Database & Migration › Schema refactor (Phase 5)",
        description="Consolidate embedding storage into `image_embeddings` SSOT, add integrity constraints (job/phase status), apply JSONB where appropriate.",
        docs=["docs/planning/database/POSTGRES_SCHEMA_OPTIMIZATIONS.md"],
    ),

    # ── P2 — medium ─────────────────────────────────────────────────────────
    make_issue(
        title="Web Worker for non-blocking RAW decode",
        repo=BACKEND, markers=["gradio"], priority="p2", type_label="feature",
        source="Medium Priority › RAW & Culling",
        description="Offload RAW decoding to a Web Worker so the UI stays responsive on large files.",
    ),
    make_issue(
        title="LibRaw WASM integration for full RAW decode",
        repo=BACKEND, markers=["gradio"], priority="p2", type_label="feature",
        source="Medium Priority › RAW & Culling",
        description="Replace embedded-JPEG-only preview with full LibRaw WASM decode.",
    ),
    make_issue(
        title="AI-Assisted culling mode (user picks with AI suggestions)",
        repo=BACKEND, markers=["python", "gradio"], priority="p2", type_label="feature",
        source="Medium Priority › RAW & Culling",
        description="Add AI-Assisted culling mode in addition to fully automated mode — user picks, AI suggests.",
    ),
    make_issue(
        title="Face detection: prioritize expressions for portrait photography",
        repo=BACKEND, markers=["python", "gradio"], priority="p2", type_label="feature",
        source="Medium Priority › RAW & Culling",
        description="Add face detection so portrait expressions can be prioritized in scoring/culling.",
    ),
    make_issue(
        title="Capture One support — additional XMP fields",
        repo=BACKEND, markers=["python", "gradio"], priority="p2", type_label="feature",
        source="Medium Priority › RAW & Culling",
        description="Write additional XMP fields for Capture One compatibility.",
    ),
    make_issue(
        title="Tag Propagation UI: AI Suggestions sidebar + Accept/Reject in ImageViewer",
        repo=GALLERY, markers=["electron"], priority="p2", type_label="feature",
        source="Medium Priority › Tag Propagation",
        description="Add AI Suggestions sidebar to `ImageViewer.tsx`; implement Accept/Reject interaction logic.",
    ),
    make_issue(
        title="Similarity Search tab / context menu in Gradio WebUI",
        repo=BACKEND, markers=["gradio"], priority="p2", type_label="feature",
        source="Medium Priority › Clustering & Embeddings",
        description="Surface `similar_search.py` in the Gradio WebUI as a tab or right-click context menu.",
    ),
    make_issue(
        title="Update electron/apiService.ts and apiTypes.ts when adding endpoints",
        repo=GALLERY, markers=["electron"], priority="p2", type_label="chore",
        source="Medium Priority › API & Contract",
        description="Discipline item: any new backend endpoint must be reflected in gallery's `apiService.ts` and `apiTypes.ts`.",
        cross_repo=True,
    ),
    make_issue(
        title="Additional Vision-Language Models — BLIP-2, LLaVA, InternVL",
        repo=BACKEND, markers=["python"], priority="p2", type_label="feature",
        source="Medium Priority › Model & Performance",
        description="Evaluate and integrate additional VLMs (BLIP-2, LLaVA, InternVL) for tagging.",
    ),

    # ── P3 — low / future ───────────────────────────────────────────────────
    make_issue(
        title="Database migration tooling — ongoing Alembic revisions and runbooks",
        repo=BACKEND, markers=["db", "python"], priority="p3", type_label="chore",
        source="Low Priority › Infrastructure",
        description="Maintain Alembic revisions and operational runbooks as schema evolves.",
    ),
    make_issue(
        title="Batch API endpoints — REST API for programmatic access",
        repo=BACKEND, markers=["python"], priority="p3", type_label="feature",
        source="Low Priority › Infrastructure",
        description="Expose batch processing via REST for headless / scripted use.",
    ),
    make_issue(
        title="Cloud processing support — remote GPU inference (RunPod, Lambda Labs)",
        repo=BACKEND, markers=["python"], priority="p3", type_label="feature",
        source="Low Priority › Infrastructure",
        description="Allow scoring/tagging to run against remote GPU providers.",
    ),
    make_issue(
        title="Gallery themes and customization — user-selectable color themes",
        repo=BACKEND, markers=["gradio"], priority="p3", type_label="feature",
        source="Low Priority › UI & Future",
        description="User-selectable color themes for the operator UI.",
    ),
    make_issue(
        title="Keyboard navigation — full keyboard support for gallery navigation",
        repo=BACKEND, markers=["gradio"], priority="p3", type_label="feature",
        source="Low Priority › UI & Future",
        description="Full keyboard navigation in the Gradio gallery view.",
    ),
    make_issue(
        title="Video quality assessment — extend scoring to video files",
        repo=BACKEND, markers=["python"], priority="p3", type_label="feature",
        source="Low Priority › UI & Future",
        description="Extend the scoring pipeline to handle video inputs.",
    ),
    make_issue(
        title="Real-time camera assessment — live feed quality analysis",
        repo=BACKEND, markers=["python"], priority="p3", type_label="feature",
        source="Low Priority › UI & Future",
        description="Live-feed quality analysis (real-time camera input).",
    ),
    make_issue(
        title="Mobile app support — native mobile application",
        repo=BACKEND, markers=[], priority="p3", type_label="feature",
        source="Low Priority › UI & Future",
        description="Native mobile companion application.",
    ),
    make_issue(
        title="Web API/service — deployable scoring service",
        repo=BACKEND, markers=["python"], priority="p3", type_label="feature",
        source="Low Priority › UI & Future",
        description="Package the scoring engine as a deployable web service.",
    ),
    make_issue(
        title="Adobe Lightroom Classic plugin — native Lightroom integration",
        repo=BACKEND, markers=["python"], priority="p3", type_label="feature",
        source="Low Priority › UI & Future",
        description="Native Lightroom Classic plugin for in-app scoring/culling.",
    ),
    make_issue(
        title="Capture One workflow — culling workflow for Capture One",
        repo=BACKEND, markers=["python"], priority="p3", type_label="feature",
        source="Low Priority › UI & Future",
        description="End-to-end Capture One culling workflow.",
    ),
    make_issue(
        title="Photo Mechanic integration — ingest workflow support",
        repo=BACKEND, markers=["python"], priority="p3", type_label="feature",
        source="Low Priority › UI & Future",
        description="Photo Mechanic ingest-side integration.",
    ),

    # ── Gallery-only items from image-scoring-gallery/TODO.md ──────────────
    make_issue(
        title="2D Embedding Map UI — extend EmbeddingMap.tsx with projection + WebGL viz",
        repo=GALLERY, markers=["electron"], priority="p2", type_label="feature",
        source="image-scoring-gallery/TODO.md › Embeddings",
        description="`EmbeddingMap.tsx` is currently a placeholder scaffold. Add projection pipeline, WebGL/canvas visualization of 1280-d vectors projected to 2D, and map UX in `AppContent.tsx`.",
        cross_repo=True,
    ),
    make_issue(
        title="Outlier Detection UI — Show Outliers toggle + visual badge",
        repo=GALLERY, markers=["electron"], priority="p2", type_label="feature",
        source="image-scoring-gallery/TODO.md › Embeddings",
        description="Add a 'Show Outliers' toggle to `FilterPanel.tsx`, a visual badge in `GalleryGrid.tsx`, and connect to the backend outlier detection endpoint.",
        cross_repo=True,
    ),
    make_issue(
        title="Smart Stack Representative — Smart Cover toggle + centroid-based selection",
        repo=GALLERY, markers=["electron"], priority="p2", type_label="feature",
        source="image-scoring-gallery/TODO.md › Embeddings",
        description="Add a 'Smart Cover' toggle to `SelectionSettings.tsx`; implement centroid-based cover selection across IPC + backend.",
        cross_repo=True,
    ),
    make_issue(
        title="Refactor folder lookup to indexed structure in useFolders",
        repo=GALLERY, markers=["electron", "db"], priority="p3", type_label="refactor",
        source="image-scoring-gallery/TODO.md › DB",
        description="Replace ad-hoc folder lookups in `useFolders` with an indexed structure for performance.",
    ),
    make_issue(
        title="Consolidate styling into a unified system (CSS Modules or Tailwind)",
        repo=GALLERY, markers=["electron"], priority="p3", type_label="refactor",
        source="image-scoring-gallery/TODO.md › UI",
        description="Pick CSS Modules or Tailwind and consolidate the gallery's styling into a single, consistent system.",
    ),
]


def main() -> None:
    print(f"Filing {len(ISSUES)} issues into project #{PROJECT_NUMBER} ({PROJECT_OWNER})\n")
    for i, issue in enumerate(ISSUES, 1):
        print(f"[{i:02d}/{len(ISSUES)}] {issue.repo}: {issue.title}")
        file_issue(issue)
    print("\nDone.")


if __name__ == "__main__":
    main()

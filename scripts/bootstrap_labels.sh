#!/usr/bin/env bash
# One-time: create the unified label taxonomy in both repos.
# Idempotent — re-running updates color/description.
set -euo pipefail

REPOS=("synthet/image-scoring-backend" "synthet/image-scoring-gallery")

# name|color|description
LABELS=(
  "area:python|1f6feb|Backend (modules/, FastAPI, tests)"
  "area:db|8957e5|PostgreSQL, Alembic, modules/db.py"
  "area:gradio|d29922|Gradio WebUI / operator UI"
  "area:electron|2da44e|image-scoring-gallery / Electron / React"
  "area:docs|6e7681|Docs, planning, runbooks"
  "priority:p0|b62324|Highest impact / unblocks others"
  "priority:p1|d29922|High impact"
  "priority:p2|9e6a03|Normal"
  "priority:p3|6e7681|Low / opportunistic"
  "type:bug|d1242f|Defect or regression"
  "type:feature|1f883d|New capability"
  "type:refactor|0969da|Internal restructuring"
  "type:test|8250df|Test coverage / verification"
  "type:chore|6e7681|Tooling, deps, infra"
  "cross-repo|0e8a9c|Coordinated change across both repos"
)

for repo in "${REPOS[@]}"; do
  echo "=== $repo ==="
  for spec in "${LABELS[@]}"; do
    IFS='|' read -r name color desc <<<"$spec"
    gh label create "$name" --repo "$repo" --color "$color" --description "$desc" --force >/dev/null
    echo "  $name"
  done
done

# Design — Index

| Document | Description |
|----------|-------------|
| [UX_UI_CONSTITUTION.md](UX_UI_CONSTITUTION.md) | Mandatory UX/UI rules for backend `/ui/` and Gradio `/app` (binding doc; shared principles in image-scoring-ui) |
| [DESIGN_SYSTEM.md](DESIGN_SYSTEM.md) | Pointer to **image-scoring-ui** canonical palette/icons (`@synthet/image-scoring-design` 1.2.x) |
| [FRONTEND_VISUAL_SPEC.md](FRONTEND_VISUAL_SPEC.md) | Typography, Leaflet, density — backend SPA implementation annex |
| [ui-pipeline-redesign.md](../features/planned/ui-pipeline-redesign.md) | Pipeline-centric UI redesign proposal |

## UI surfaces (where tokens apply)

| Surface | Repo | Route / entry | Styling |
|---------|------|---------------|---------|
| Primary product UI | **image-scoring-backend** | `/ui/` (React + Vite SPA) | Tailwind v4 + design package `tailwind-theme.css` |
| Runs planner (buckets) | **image-scoring-backend** | `/ui/dashboard` | Same SPA; folder buckets + Drive to Complete |
| Runs list | **image-scoring-backend** | `/ui/runs` | Active / Queued / History only |
| Operator status | **image-scoring-backend** | `/app` (minimal Gradio) | Base Gradio + design package `gradio-snippet.css` |
| Desktop gallery | **image-scoring-gallery** | Electron + Vite renderer | CSS Modules + design package `tokens.css` |

Stage labels and run-status icons must stay aligned with [PIPELINE_TERMINOLOGY.md](../technical/PIPELINE_TERMINOLOGY.md) (`phase_code` authority remains backend).

## Mockups

HTML and Python mockups for the pipeline UI:

- `UI_PIPELINE_REDESIGN_MOCKUP.html`
- `UI_PIPELINE_REDESIGN_MOCKUP_ELECTRON.html`
- `gradio_pipeline_mockup.py`, `gradio_pipeline_mockup_v2.py`, `gradio_pipeline_mockup_v3.py`
- `pipeline_ui_v2.py`

**See also:** [Main docs index](../INDEX.md) · [Plans](../planning/INDEX.md)

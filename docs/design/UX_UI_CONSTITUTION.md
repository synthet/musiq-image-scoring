# UX/UI Constitution — Backend binding

Mandatory UX/UI rules for **image-scoring-backend** surfaces. Shared principles and articles are **canonical** in [image-scoring-ui UX_UI_CONSTITUTION.md](https://github.com/synthet/image-scoring-ui/blob/main/docs/UX_UI_CONSTITUTION.md). This document binds those rules to this repo's stacks and file paths.

## Surfaces

| Surface | Route | Styling |
|---------|-------|---------|
| Primary product UI | `/ui/` (React + Vite SPA) | Tailwind v4 + `@synthet/image-scoring-design/tailwind-theme.css` |
| Operator status | `/app` (minimal Gradio) | Gradio base + synced `gradio-snippet.css` |

See [design/INDEX.md](INDEX.md) for route map and mockup links.

## Stack binding

- **Framework:** React 19 + TypeScript + Vite (`frontend/`)
- **Styling:** Tailwind CSS v4 — theme from design package (no separate `tailwind.config`)
- **Components:** Radix UI primitives (dialog, popover, tooltip)
- **Icons:** Lucide React (chrome); `EmbeddingSpaceIcon` from design package (embedding badges)
- **Toasts:** Sonner
- **Maps / viz:** Leaflet, Cosmograph — overrides in [FRONTEND_VISUAL_SPEC.md](FRONTEND_VISUAL_SPEC.md)

## Token wiring

| Layer | Path |
|-------|------|
| CSS theme | `frontend/src/index.css` — `@import "@synthet/image-scoring-design/tailwind-theme.css"` |
| Label / phase colors (TS) | `frontend/src/constants/labelColors.ts` — re-exports from package |
| Stage labels | `frontend/src/types/api.ts` — re-exports `STAGE_DISPLAY`, `StageCode` |
| Embedding UI | `EmbeddingSpaceChip.tsx`, `EmbeddingSpaceSelect.tsx`, `InspectorPrimitives.tsx` — direct package imports |
| UI primitives | `frontend/src/components/ui/` — button, badge, card, progress |
| Phase status icons | `frontend/src/components/status/PhaseStatusIcon.tsx` — **canonical** for run/phase affordances |
| Gradio CSS sync | `npm run design:sync` → `modules/ui/gradio_design_tokens.css` |

Palette tables: [DESIGN_SYSTEM.md](DESIGN_SYSTEM.md) (pointer) · [image-scoring-ui DESIGN_SYSTEM.md](https://github.com/synthet/image-scoring-ui/blob/main/docs/DESIGN_SYSTEM.md).

## Styling rules (backend-specific)

1. **Prefer theme tokens:** `var(--color-*)` in component CSS or Tailwind utilities from `@theme` — not new hex literals.
2. **New components:** Start from `frontend/src/components/ui/` primitives; use Radix for focus/ARIA.
3. **Scores:** `formatScoreValue()` from `@synthet/image-scoring-design` in tables and inspector.
4. **Connection indicator:** Follow DESIGN_SYSTEM live-connection states (Connecting / Reconnecting / Live / Offline).
5. **Leaflet / map chrome:** Documented exceptions in [FRONTEND_VISUAL_SPEC.md](FRONTEND_VISUAL_SPEC.md) — prefer `--color-bg-preview` and accent tokens where feasible.
6. **Gradio:** After token changes, run `npm run design:sync` from `frontend/`; verify with `npm run design:check`.

## Out of scope

Python backend, API schema, and DB — use `imgscore-backend-implementer` skill. Gallery Electron renderer — use gallery `gallery-ui` skill.

## Agent checklist

Before claiming UI work complete:

```bash
cd frontend && npm run design:check
npx tsc --noEmit
```

When editing `src/tokens.json` in sibling **image-scoring-ui**, follow that repo's `design-tokens` skill and refresh Gradio sync.

**Skill:** `.cursor/skills/backend-frontend-ui/SKILL.md`

**See also:** [FRONTEND_VISUAL_SPEC.md](FRONTEND_VISUAL_SPEC.md) · [AGENT_COORDINATION §6](../technical/AGENT_COORDINATION.md)

# Design system — palette and icon contract

Canonical source for colors, icons, and sizing across both projects. The same
contract applies to:

- **`image-scoring-backend/frontend`** — React + Tailwind v4 SPA at `/ui/` (token source: [`frontend/src/index.css`](../../frontend/src/index.css))
- **`image-scoring-gallery`** — Electron + React + CSS Modules (token source: [`src/styles/tokens.css`](https://github.com/synthet/image-scoring-gallery/blob/main/src/styles/tokens.css))

The two products share a VS Code Dark+ visual identity. Anything else (Material
greens, Tailwind blues, ad-hoc hex literals) is a deviation and should be
migrated to a token below.

> Note on terminology: this doc describes UI tokens. For pipeline stage names
> (Discovery / Inspection / Quality Analysis / …) and `phase_code` mapping, see
> [`technical/PIPELINE_TERMINOLOGY.md`](../technical/PIPELINE_TERMINOLOGY.md).

## Palette

### Surfaces and chrome

| Token | Hex | Use |
|---|---|---|
| `--color-bg-primary` | `#1e1e1e` | Default page background |
| `--color-bg-secondary` | `#252526` | Sidebar, side panels, elevated regions |
| `--color-bg-tertiary` | `#2d2d30` | Cards, list rows, modals |
| `--color-bg-elevated` | `#3c3c3c` | Hover row, popovers, input focus |
| `--color-border` | `#474747` | Default 1px divider, card border |
| `--color-border-muted` | `#3c3c3c` | Subtle separator inside a card |

### Text

| Token | Hex | Use |
|---|---|---|
| `--color-text-primary` | `#cccccc` | Body copy, headings |
| `--color-text-secondary` | `#9d9d9d` | Captions, secondary labels |
| `--color-text-muted` | `#6d6d6d` | Disabled / placeholder text, muted icons |

### Accent (interactive blue)

| Token | Hex | Use |
|---|---|---|
| `--color-accent` | `#007acc` | Primary buttons, links, focus ring, "running" state |
| `--color-accent-hover` | `#1e8ad6` | Hover on accent surfaces |
| `--color-accent-dim` | `#003f6e` | Selected row background, accent border-dim |

### Status (semantic)

| Token | Hex | Use | Lucide icon |
|---|---|---|---|
| `--color-success` | `#89d185` | Done / completed phase, positive toast | `CheckCircle2` |
| `--color-success-bg` | `#1a3320` | Tinted success surface |  |
| `--color-success-border` | `#2d6a2d` | Success card outline |  |
| `--color-warning` | `#cca700` | Warnings, partial / paused, "needs attention" | `AlertTriangle` |
| `--color-warning-bg` | `#332900` | Tinted warning surface |  |
| `--color-danger` | `#f44747` | Errors, failed / canceled phase, destructive action | `XCircle` |
| `--color-danger-bg` | `#3a1515` | Tinted danger surface |  |
| `--color-danger-border` | `#7a2a2a` | Danger card outline |  |
| `--color-info` | `#9cdcfe` | Informational toast, neutral hint | `Info` |
| `--color-info-bg` | `#003a5c` | Tinted info surface |  |

### Pipeline / phase status

| State | Token | Hex | Lucide icon |
|---|---|---|---|
| `pending` | `--color-text-muted` | `#6d6d6d` | `Circle` |
| `queued` | `--color-text-secondary` | `#9d9d9d` | `Clock3` |
| `running` | `--color-accent` | `#007acc` | `Loader2` (animated) |
| `paused` | `--color-warning` | `#cca700` | `PauseCircle` |
| `done` / `completed` | `--color-success` | `#89d185` | `CheckCircle2` |
| `skipped` | `--color-text-muted` | `#6d6d6d` | `MinusCircle` |
| `failed` / `canceled` | `--color-danger` | `#f44747` | `XCircle` |
| `partial` / `interrupted` / `cancel_requested` | `--color-warning` | `#cca700` | `AlertTriangle` |

The canonical implementation is
[`frontend/src/components/status/PhaseStatusIcon.tsx`](../../frontend/src/components/status/PhaseStatusIcon.tsx).
It is the **single source** for run / phase status visuals; the older
`frontend/src/components/ui/phaseStatus.tsx` was removed.

### Photo color labels (Lightroom-style)

These are user-facing color tags applied to images (`image.label === 'red' | 'yellow' | 'green' | 'blue' | 'purple'`).
They are **not** UI status colors and live in their own namespace.

| Token | Hex |
|---|---|
| `--label-red` | `#e53935` |
| `--label-yellow` | `#fdd835` |
| `--label-green` | `#43a047` |
| `--label-blue` | `#1e88e5` |
| `--label-purple` | `#8e24aa` |

Backend implementation: [`frontend/src/constants/labelColors.ts`](../../frontend/src/constants/labelColors.ts).
Gallery implementation: [`src/styles/tokens.css`](https://github.com/synthet/image-scoring-gallery/blob/main/src/styles/tokens.css) (`--label-*`).

### Score / rating

| Token | Hex | Use |
|---|---|---|
| `--score-gold` | `#ffd700` | Filled star, score-bar peak |

This is the only place gold appears. Star outlines use `--color-text-muted`.

## Icon contract (Lucide)

All icons come from [`lucide-react`](https://lucide.dev). Both repos pin a
recent 0.5x release. Avoid mixing icon libraries.

### One concept, one icon

| Concept | Canonical icon | Notes |
|---|---|---|
| Refresh / reload | `RefreshCw` | Drop `RefreshCcw` |
| Cancel edits / discard | `RotateCcw` | Distinct from refresh; pair with "Cancel" copy |
| External link | `ExternalLink` |  |
| Folder collapsed / open | `Folder` / `FolderOpen` |  |
| Tree expand / collapse | `ChevronRight` / `ChevronDown` |  |
| Pagination | `ChevronLeft` / `ChevronRight` |  |
| Add | `Plus` |  |
| Delete | `Trash2` |  |
| Close / dismiss | `X` |  |
| Star (rating) | `Star` |  |
| Search | `Search` |  |
| Settings | `Settings` (use `Settings2` only when both meanings appear in one view) |  |
| Tools | `Wrench` |  |
| Brand mark | `Zap` |  |

### Severity (notifications, toasts, banners)

| Severity | Icon | Color token |
|---|---|---|
| `info` | `Info` | `--color-info` |
| `success` | `CheckCircle2` | `--color-success` |
| `warning` | `AlertTriangle` | `--color-warning` |
| `error` | `XCircle` | `--color-danger` |

`AlertCircle` is **retired** wherever it overlaps the four severities above.
Reserve it only for cases that are clearly neither error nor warning (rare —
prefer `Info`).

### Sizes

| Context | Pixel size | Tailwind class |
|---|---|---|
| Inline with body text | `size={14}` | `h-3.5 w-3.5` |
| Buttons, toolbar, card actions | `size={16}` | `h-4 w-4` |
| Panel headers, page titles | `size={20}` | `h-5 w-5` |
| Empty-state hero | `size={32}` | `h-8 w-8` |

Use the numeric `size={...}` prop in TSX. `className="h-4 w-4"` is acceptable
only when the icon sits inside a `<Button>` whose own size variant already
defines its bounds.

### Animation

- Spin: `Loader2` with `className="animate-spin"`. No custom keyframes.
- Pulse: not used. If you need it, add a token first.

## Do / don't

**Do**

- Use Tailwind v4 utilities generated from `@theme` (e.g. `bg-bg-primary`,
  `text-text-secondary`, `border-border`) in the backend frontend.
- Use `var(--color-...)` in gallery CSS Modules and inline `style={{ ... }}`.
- Take all status visuals from `PhaseStatusIcon` / the table above.

**Don't**

- Add new hex literals in component files. If a shade is missing, propose a
  token in `index.css` / `tokens.css` first, then use it.
- Mix Material (`#4caf50`, `#f44336`, `#ff9800`, `#2196f3`) with VS Code Dark+
  status colors. Pick the table above.
- Reuse photo-label hex (`--label-*`) for status / severity. They are visually
  similar but semantically distinct.
- Re-introduce a parallel `PhaseStatusIcon` component.

## Implementation map

| Concern | Backend frontend | Gallery |
|---|---|---|
| Token definitions | [`frontend/src/index.css`](../../frontend/src/index.css) `@theme` | [`src/styles/tokens.css`](https://github.com/synthet/image-scoring-gallery/blob/main/src/styles/tokens.css) |
| Status icon component | [`frontend/src/components/status/PhaseStatusIcon.tsx`](../../frontend/src/components/status/PhaseStatusIcon.tsx) | n/a (gallery does not render run status today) |
| Severity toasts | [`frontend/src/components/ui/badge.tsx`](../../frontend/src/components/ui/badge.tsx) | [`src/components/Layout/NotificationTray.tsx`](https://github.com/synthet/image-scoring-gallery/blob/main/src/components/Layout/NotificationTray.tsx) |
| Photo label palette | [`frontend/src/constants/labelColors.ts`](../../frontend/src/constants/labelColors.ts) | `--label-*` in [`tokens.css`](https://github.com/synthet/image-scoring-gallery/blob/main/src/styles/tokens.css) |

## Migration notes

For agents touching legacy code:

- Replace `bg-[#xxxxxx]` / `text-[#xxxxxx]` with the closest theme utility. If
  the literal does not match any token within ~5%, ask whether to add a token
  rather than introduce a new shade.
- Replace `<RefreshCcw />` with `<RefreshCw />`.
- Replace `<AlertCircle />` used for warning copy with `<AlertTriangle />`,
  and used for error copy with `<XCircle />`.
- Treat icon `size={n}` outliers (8, 10, 11, 12, 13, 18, 24) as suspect; round
  to 14 / 16 / 20 unless there is a specific reason.

**See also:** [Design index](INDEX.md) · [Pipeline terminology](../technical/PIPELINE_TERMINOLOGY.md) · [Canonical sources](../CANONICAL_SOURCES.md)

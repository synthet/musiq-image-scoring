# Frontend UX/UI Visual Specification

## 1. Design Philosophy & Theme
The frontend adopts a **VS Code Dark+ color system**, deliberately aligned with `electron-image-scoring`. This creates a cohesive, professional, developer-centric, or "pro-tool" aesthetic. The design relies heavily on modern dark mode principles with subtle contrast between surfaces, vibrant interactive accents, and clear semantic feedback colors.

*(For the canonical palette, icon contract, and UI patterns — live connection indicator, score formatting, images table, inspector — see the package doc [image-scoring-ui/docs/DESIGN_SYSTEM.md](https://github.com/synthet/image-scoring-ui/blob/main/docs/DESIGN_SYSTEM.md) and the local mirror [DESIGN_SYSTEM.md](DESIGN_SYSTEM.md).)*

## 2. Technology Stack
- **Framework:** React 19 + TypeScript + Vite
- **Styling Engine:** Tailwind CSS (v4)
- **Component Library:** Radix UI Primitives (headless components for dialogs, popovers, tooltips)
- **Icons:** Lucide React
- **Animations:** Framer Motion
- **Data Visualization & Maps:** Leaflet, React Leaflet, Cosmograph

---

## 3. Typography
The typography is optimized for data density and readability in a professional tool environment.

- **Primary Font Family:** `'Segoe UI', system-ui, -apple-system, sans-serif`
- **Monospace/Code Font:** `'Segoe UI Mono', 'Cascadia Code', monospace` (Used for scores, hashes, log outputs, and IDs)
- **Base Font Size:** `13px` (High-density optimized for desktop/pro tools)
- **Line Height:** `1.5`
- **Rendering:** `-webkit-font-smoothing: antialiased` for crisp rendering on dark backgrounds.

---

## 4. Layout & UI Component Patterns

### Global Elements
- **Scrollbars:** Styled to match the VS Code aesthetic.
  - Width/Height: `10px`
  - Track: Transparent
  - Thumb: `#424242` with `2px` border radius.
  - Thumb Hover: `#555`

### Map & Geo UI (Leaflet Overrides)
- **Container:** Deep dark theme override (`#141414`).
- **Cluster Markers:**
  - Transparent wrapper.
  - Circular nodes with white text, `2px` solid white border (25% opacity).
  - Blue glow effect using `box-shadow: 0 2px 12px rgba(0, 122, 204, 0.35)`.
  - **Hover Interaction:** Smooth scaling (`1.12x`) and intensified shadow glow.
- **Popups:**
  - Surface: `#252526` with `#3c3c3c` border and `10px` border radius.
  - Heavy drop shadow (`0 8px 32px rgba(0, 0, 0, 0.5)`) for elevation.
  - **Image Thumbnails:** Aspect-ratio constrained (`4/3`), with subtle hover scaling (`1.05x`). Includes a loading spinner (`#4fc1ff` top border) and a fallback for errors.
  - **Metadata:** Compact layout utilizing monospace fonts for scores (`#003f6e` background, `#4fc1ff` text) and `11px` bold primary text for filenames.

### Component Architecture
- **Density:** High density UI (13px base font, compact padding) suitable for dashboard interfaces (e.g., `RunsPage`, `DiagnosticsPage`, `ImagesPage`).
- **Interactive States:** Use of Framer Motion for micro-animations, layout animations, and smooth state transitions.
- **Accessibility:** Headless components via Radix UI ensure correct ARIA roles, focus management, and keyboard navigation, while completely adopting the custom Tailwind styling system.
- **Toasts/Notifications:** Handled via Sonner, styled to fit the dark theme.

> **Tip:** When building new components, always reference the Tailwind configuration and standard CSS variables defined in `index.css`. Avoid hardcoding hex values to maintain the VS Code Dark+ theme integrity.

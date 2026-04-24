# UI Standards

Last updated: 2026-04-24
Scope: `AEGIS/client/src`

## Typography

### Font families

- Primary UI font: `var(--font-family-sans)` -> `'Segoe UI', Tahoma, Geneva, Verdana, sans-serif`
- Monospace: `var(--font-family-monospace)` -> `'Cascadia Mono', Consolas, 'Courier New', monospace`

### Scale hierarchy

Defined in `AEGIS/client/src/styles.css`:
- Caption: `--font-size-caption` (`0.8rem`)
- Label: `--font-size-label` (`0.9rem`)
- Body: `--font-size-body` (`1rem`)
- Title small: `--font-size-title-sm` (`1.05rem`)
- Title medium: `--font-size-title-md` (`1.2rem`)
- Title large: `--font-size-title-lg` (`clamp(1.65rem, 2.8vw, 2.2rem)`)

### Line heights

- Tight headings: `--line-height-tight` (`1.2`)
- Default text: `--line-height-base` (`1.5`)

## Layout and Spacing

### Grid and breakpoints

- Main workspace uses a two-pane grid in `geospatial-page.component.css`:
  - chat/toolbar pane
  - resize handle
  - map pane
- Toolbar width constraints are enforced in component logic:
  - min: `280px`
  - max: `760px`
  - map minimum width guard: `320px`
- Settings page uses two-column layout (`7fr/3fr`) with responsive fallback rules in page CSS.

### Spacing scale

Global spacing tokens:
- `--space-1` to `--space-6` (`0.25rem` to `2rem`)

Rules:
- Prefer spacing tokens for margin/padding/gaps.
- Where component CSS still uses literals, new work should converge toward tokenized values.

## Color System

### Core palette

Defined in `styles.css`:
- Primary text: `--color-text-primary`
- Secondary/muted text: `--color-text-secondary`, `--color-text-muted`
- Brand/accent: `--color-brand`, `--color-accent`, `--color-accent-soft`, `--color-accent-muted`, `--color-accent-border`
- Surface/background: `--color-surface-app`, `--color-surface-panel`, `--color-surface-subtle`, `--color-surface-canvas`
- Borders: `--color-border-subtle`, `--color-border-strong`

### Semantic colors

- Error text token: `--color-text-danger`
- Focus ring token: `--color-focus-ring`

### Contrast and accessibility

- Ensure text/background combinations remain readable (target WCAG AA for normal UI text).
- Interactive focus states must remain visible regardless of theme variations.

## Components and Patterns

### Reusable components

- `map-preview.component.*`: map rendering and overlay visualization
- `model-role-actions.component.*`: model role assignment actions
- `settings-icon-action.component.*`: compact icon action controls
- `settings-modal-shell.component.*`: modal shell pattern for settings dialogs

### Standard interaction states

All interactive components must provide:
- default
- hover
- active/selected (where applicable)
- disabled
- focus-visible

### Buttons and form controls

- Base form controls are normalized globally in `styles.css`.
- Component-level variants may specialize visuals but should preserve shared focus and disabled behavior.

## Page Structure

### Primary pages

- `/` (`GeospatialPageComponent`):
  - left chat/command pane
  - right map pane
  - resizable divider
  - inline alert and progress indicators
- `/settings` (`SettingsPageComponent`):
  - sticky header
  - search/filter controls
  - model cards and assignment UI
  - API key and Ollama management modals

### Navigation hierarchy

- Top-level route pair: workspace and settings.
- Unknown routes redirect to workspace.

## User Experience Standards

### Core user journeys

- Ask geospatial question -> receive assistant response -> inspect map session and overlays.
- Open settings -> manage provider/model assignments -> return to workspace.

### Interaction consistency rules

- `Enter` submits chat; `Shift+Enter` inserts newline.
- Loading and request-in-progress states must be explicit.
- Error states should use actionable human-readable text.

### Feedback patterns

- Use persistent status text for settings operations.
- Use inline alerts for map/session concerns.
- Keep progress indicator visible during in-flight chat requests.

### Loading and empty states

- Workspace shows welcome/idle content before first successful turn.
- Settings page includes explicit empty-state UI when no filtered model results exist.

## Responsiveness

- The app must remain usable across desktop and narrow widths.
- Workspace supports collapsing toolbar and constrained resize behavior.
- Settings content adapts from multi-column to narrower layouts for smaller viewports.
- Avoid fixed heights that break small-screen scrolling.

## Accessibility

- Maintain keyboard navigability for all controls.
- Preserve `:focus-visible` outlines for buttons and inputs.
- Maintain semantic containers and labels for form elements.
- Do not encode status solely by color.
- Respect reduced-motion settings (`prefers-reduced-motion` rule in global styles).

## Design Principles

- Consistency: reuse tokens, shared components, and recurring patterns.
- Clarity: prioritize legible content hierarchy and predictable control placement.
- Predictability: keep workflow and interaction semantics stable across pages.
- Simplicity: avoid unnecessary visual complexity and one-off style variants.
- Usability-first: functional clarity is preferred over stylistic novelty.

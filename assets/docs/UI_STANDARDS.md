# UI Standards

Date: 2026-03-27  
Scope: `AEGIS/client/src`

## 1) Spacing Scale

Use the shared spacing tokens from `index.css`:

- `--space-1`: 4px
- `--space-2`: 8px
- `--space-3`: 12px
- `--space-4`: 16px
- `--space-5`: 24px
- `--space-6`: 32px

Rules:
- Prefer tokenized spacing over one-off pixel literals.
- Use `--space-1` to `--space-3` for intra-component spacing.
- Use `--space-4`+ for section/panel spacing.

## 2) Typography Scale

Use these shared tokens:

- `--font-size-caption`: 0.8rem
- `--font-size-label`: 0.9rem
- `--font-size-body`: 1rem
- `--font-size-title-sm`: 1.05rem
- `--font-size-title-md`: 1.2rem
- `--font-size-title-lg`: responsive `clamp(1.65rem, 2.8vw, 2.2rem)`

Weight conventions:
- Labels/meta: `--font-weight-semibold`
- Titles/key metrics/actions: `--font-weight-bold`

## 3) Color System

Primary text/surface:

- `--color-text-primary`
- `--color-text-secondary`
- `--color-text-muted`
- `--color-surface-app`
- `--color-surface-panel`
- `--color-surface-subtle`

Brand/accent:

- `--color-brand`
- `--color-accent`
- `--color-accent-soft`
- `--color-accent-muted`
- `--color-accent-border`

Semantic:

- Danger text: `--color-text-danger`
- Focus: `--color-focus-ring`

Rules:
- Prefer variables over hex literals in component CSS.
- Do not rely on color alone to communicate state.

## 4) Component Usage Rules

Buttons:
- `primary-button`: primary submit action only.
- `secondary-button`: supporting actions.
- Always include `:hover`, `:disabled`, `:focus-visible`.

Inputs/selects/textarea:
- Use global input styles from `index.css`.
- Keep labels visible and placed above controls.

Panels/cards:
- Use shared panel surface and border tokens.
- Keep radius/shadow consistent (`--radius-*`, `--shadow-*`).

Headings:
- Use `PanelHeader` with explicit `headingLevel` where needed to preserve hierarchy.

## 5) Layout Rules

- Main geospatial shell is full-height and split into:
  - Left continuous command toolbar (includes brand/logo area at top).
  - Right full working canvas.
- Avoid redundant top headers when the toolbar already carries app identity.
- Primary workspace layout:
  - Left command toolbar.
  - Right output canvas.
- Desktop target split: roughly 30/70.
- At narrow widths, stack toolbar above canvas.

## 6) Accessibility Rules

- Every interactive custom element must have a visible `:focus-visible` style.
- Respect reduced-motion preferences (global `prefers-reduced-motion` guard).
- Keep helper and error text near related inputs.
- Preserve semantic structure (`main`, `header`, `aside`, `section`, heading levels).

## 7) Do and Don’t

Do:
- Use design tokens.
- Keep spacing and radii on scale.
- Keep action labels explicit.
- Keep responsive behavior deterministic.

Don’t:
- Add duplicate class names with conflicting definitions across files.
- Add one-off color literals when a token exists.
- Use rigid heights that break small viewports.
- Introduce new visual variants without a documented need.

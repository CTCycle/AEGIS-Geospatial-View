# UI Standards

Last updated: 2026-03-28  
Scope: `AEGIS/client/src`

## 1. Design Tokens

Use shared tokens from `src/index.css` for:
- spacing (`--space-*`)
- typography (`--font-size-*`, weights, line heights)
- colors (`--color-*`)
- radii and shadows (`--radius-*`, `--shadow-*`)

Rules:
- Prefer tokens over one-off literals.
- Keep spacing and sizing on the existing scale where possible.

## 2. Layout Rules

Current primary layout is a two-pane workspace:
- left: command toolbar (`.toolbar-panel`)
- right: map canvas (`.canvas-panel`)

Implementation expectations:
- desktop: persistent split layout (`GeospatialPage.css`)
- narrow screens: stack toolbar above canvas via breakpoints
- avoid introducing additional global navigation shells unless product requirements change

## 3. Typography and Hierarchy

- Keep heading hierarchy semantic (`h1` page title, `h2` section headers, etc.).
- Use shared title/body token sizes.
- Keep metadata/helper text visually secondary with muted text tokens.

## 4. Interaction and States

- All custom interactive controls require visible `:focus-visible` styles.
- Provide clear disabled, hover, and loading states.
- Keep primary actions distinct from secondary actions.

## 5. Accessibility

- Use semantic structure (`main`, `section`, `aside`, labeled regions).
- Keep labels associated with controls.
- Do not rely only on color to communicate state.
- Respect `prefers-reduced-motion` (already implemented globally in `index.css`).

## 6. Styling Hygiene

Do:
- keep component styles scoped and predictable
- reuse shared utility patterns where practical
- prefer small, targeted CSS changes

Do not:
- duplicate conflicting class definitions across files
- introduce hardcoded colors when token equivalents exist
- use rigid heights that break mobile/small laptop viewports

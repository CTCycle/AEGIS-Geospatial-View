# UI Standards

Last updated: 2026-04-08
Scope: `AEGIS/client/src`

## 1. Design Tokens

Use shared tokens from `src/index.css` for:
- spacing (`--space-*`)
- typography (`--font-size-*`)
- colors (`--color-*`)
- radii and shadows (`--radius-*`, `--shadow-*`)

Rules:
- prefer tokens over one-off literals
- keep spacing/sizing on the existing scale

## 2. Layout Rules

Primary layout is a two-pane workspace:
- left: command/chat toolbar
- right: map canvas

Expectations:
- desktop: persistent split layout
- narrow screens: stacked layout via breakpoints
- avoid introducing extra global shells unless requirements change

## 3. Typography and Hierarchy

- Keep heading hierarchy semantic.
- Use shared title/body token sizes.
- Keep helper text visually secondary.

## 4. Interaction and States

- Provide visible `:focus-visible` styles.
- Provide clear disabled, hover, and loading states.
- Keep primary actions visually distinct.

## 5. Accessibility

- Use semantic structure (`main`, `section`, `aside`).
- Keep labels associated with controls.
- Do not rely only on color for meaning.
- Respect `prefers-reduced-motion`.

## 6. Styling Hygiene

Do:
- keep styles scoped and predictable
- reuse shared patterns
- prefer small targeted CSS changes

Do not:
- duplicate conflicting class definitions
- hardcode token-equivalent colors
- use rigid heights that break small viewports

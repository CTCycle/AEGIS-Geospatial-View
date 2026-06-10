# Design Tokens

Last updated: 2026-06-02

## Typography

- Primary font: `var(--font-family-sans)` -> `'Segoe UI', Tahoma, Geneva, Verdana, sans-serif`
- Monospace font: `var(--font-family-monospace)` -> `'Cascadia Mono', Consolas, 'Courier New', monospace`

Type scale defined in `app/client/src/styles.css`:

- `--font-size-caption`
- `--font-size-label`
- `--font-size-body`
- `--font-size-title-sm`
- `--font-size-title-md`
- `--font-size-title-lg`

Line-height tokens:

- `--line-height-tight`
- `--line-height-base`

## Spacing

Global spacing tokens run from `--space-1` to `--space-6`. New work should prefer tokens instead of literal spacing values.

## Color System

Core token groups:

- text: `--color-text-primary`, `--color-text-secondary`, `--color-text-muted`
- accent: `--color-brand`, `--color-accent`, `--color-accent-soft`, `--color-accent-muted`, `--color-accent-border`
- surfaces: `--color-surface-app`, `--color-surface-panel`, `--color-surface-subtle`, `--color-surface-canvas`
- borders: `--color-border-subtle`, `--color-border-strong`
- semantics: `--color-text-danger`, `--color-focus-ring`

Text and background combinations should remain WCAG AA readable for normal UI text.

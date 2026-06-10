# TypeScript

Last updated: 2026-06-02

## Baseline

- Angular 19 standalone architecture
- TypeScript strict mode
- Shared frontend contracts live in `app/client/src/app/core/types.ts`
- Backend calls route through `app/client/src/app/core/api.ts`

## Typing And Data Safety

- Avoid `any`.
- Prefer explicit interfaces and narrowing from `unknown`.
- Validate response shape before rendering.
- Keep shared payload contracts centralized.

## Component And State Design

- Keep route orchestration in `pages/*`.
- Keep reusable presentational blocks in `components/*`.
- Keep API and shared state utilities in `core/*`.
- Represent async UI state explicitly.

## UX And Accessibility Coding

- Implement explicit loading, empty, and error states.
- Preserve keyboard access and visible focus behavior.
- Use semantic HTML.
- Do not rely on color alone to convey meaning.

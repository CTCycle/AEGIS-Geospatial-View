# TypeScript Guidelines (AEGIS Frontend)

Last updated: 2026-04-09
Scope: `AEGIS/client/src`

Project baseline:
- Angular 19 (standalone APIs)
- TypeScript 5
- Angular CLI build pipeline
- Strict TypeScript configuration

## 1. Type Safety

- Keep `strict` mode enabled.
- Avoid `any`; use `unknown` for untrusted data and narrow before use.
- Type exported component inputs/outputs, service responses, and helper interfaces.
- Keep shared contracts in `src/app/core/types.ts`.

## 2. Component and Page Boundaries

- Keep page-level orchestration in `src/app/pages`.
- Keep reusable UI blocks in `src/app/components`.
- Keep API/network and persistence logic in `src/app/core`.
- Keep components focused on rendering and interaction.

## 3. API Usage

- Route HTTP calls through shared API modules.
- Assume backend responses are untrusted and validate required fields before render.
- Handle fallback states explicitly.
- Use `/api` base semantics expected by backend mounting/proxying.

## 4. State and UX

- Keep async state explicit (`loading`, `success`, `error`).
- Show actionable errors for failed requests.
- Prevent duplicate request spam with disabled/loading states.

## 5. Styling and UI Consistency

- Follow `assets/docs/UI_STANDARDS.md`.
- Use design tokens from `src/styles.css` instead of one-off literals.
- Keep accessibility behavior explicit (`:focus-visible`, semantic elements, labels).

## 6. Build and Quality Gates

- Keep `npm run build` green (`ng build`).
- Keep lint checks green when lint rules are present.
- Prefer small, clear modules over abstraction-heavy patterns.

## 7. Testing Impact

- Frontend behavior is validated primarily via Playwright E2E in `tests/e2e`.
- Update E2E coverage when user-visible behavior changes.

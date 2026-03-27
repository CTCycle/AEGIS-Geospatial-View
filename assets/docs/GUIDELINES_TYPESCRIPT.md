# TypeScript Guidelines (AEGIS Frontend)

Last updated: 2026-03-28  
Scope: `AEGIS/client/src`

Project baseline:
- React 18
- TypeScript 5
- Vite 6
- Strict TypeScript configuration

## 1. Type Safety

- Keep `strict` mode enabled.
- Avoid `any`; use `unknown` for untrusted data and narrow before use.
- Type all exported component props, service responses, and helper interfaces.
- Keep shared contracts in `src/types.ts`.

## 2. Component and Page Boundaries

- Keep page-level orchestration in `src/pages`.
- Keep reusable UI in `src/components`.
- Keep API/network logic in `src/services`.
- Keep components focused on rendering and interaction, not transport concerns.

## 3. API Usage

- Route all HTTP calls through shared service modules.
- Assume backend responses are untrusted; validate required fields before rendering.
- Prefer stable response-shape handling and clear fallback states.
- Use `/api` base path semantics expected by current backend mounting and frontend proxying.

## 4. State and UX

- Keep async state explicit (`loading`, `success`, `error`).
- Show actionable error messages for failed requests.
- Prevent duplicate request spam with appropriate disabled states.

## 5. Styling and UI Consistency

- Follow `assets/docs/UI_STANDARDS.md`.
- Use design tokens from `src/index.css` instead of one-off color/spacing literals.
- Keep accessibility behavior explicit (`:focus-visible`, semantic elements, label associations).

## 6. Build and Quality Gates

- Keep `npm run build` green (`tsc && vite build`).
- Keep lint checks green when lint rules are present.
- Prefer small, clear modules over abstraction-heavy patterns.

## 7. Testing Impact

- Frontend behavior is validated primarily via Python Playwright E2E tests in `tests/e2e`.
- Update/add E2E coverage for user-visible behavior changes.

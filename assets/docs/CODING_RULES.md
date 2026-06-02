# Coding Rules

Last updated: 2026-06-02
Scope: `app/server`, `app/client`, `app/tests`

## Python Rules

### Baseline

- Target version: `>=3.14` (from `pyproject.toml`).
- Use virtual environment at `runtimes/.venv` when present; otherwise use root `.venv`.
- Keep dependency state aligned with `app/server/pyproject.toml` and `app/server/uv.lock`.
- Do not create ad-hoc environments outside repository conventions.

### Typing

- Type annotations are required for public APIs and non-trivial logic.
- Use built-in generics (`list[str]`, `dict[str, Any]`).
- Prefer `|` unions over `Optional`.
- Use `collections.abc` for abstract collection/function types.
- Treat typing as a quality gate, not optional documentation.

### Validation and API contracts

- Use Pydantic/domain models for request and response contracts.
- Avoid ad-hoc manual validation blocks when schema models can enforce constraints.
- Use explicit HTTP status codes and consistent response models.
- Return safe, actionable errors; never leak secrets/credentials.
- Preserve request and job traceability (session IDs, job IDs, structured payloads).

### Async and background jobs

- Use async only when dependencies are non-blocking.
- Keep CPU-heavy work out of async handlers.
- Use the existing `JobManager` flow for long-running map operations.
- Long-running APIs must support start (`POST /api/maps/jobs`), poll (`GET /api/maps/jobs/{job_id}`), and cancel (`DELETE /api/maps/jobs/{job_id}`).

### Code structure

- Keep functions small, focused, and deterministic where possible.
- Make side effects explicit at boundaries (I/O, DB, network).
- Prefer composition and straightforward control flow over deep indirection.
- Use comments only where they add safety or design clarity.
- Preserve local style conventions; avoid broad stylistic churn.
- Keep modules below approximately 1000 LOC when practical.
- Place imports at module top.
- Avoid nested function definitions unless narrowly justified.
- Use classes when they improve cohesion around shared state/behavior.

### Tooling and testing

- Lint/format with Ruff or project-standard equivalent.
- Type-check with Pylance-compatible typing discipline.
- Test with pytest.
- Cover `app/tests/unit` and relevant `app/tests/e2e` for user-visible or contract changes.

## TypeScript Rules

### Baseline

- Angular 19 standalone architecture with TypeScript strict mode.
- Keep frontend contracts in `app/client/src/app/core/types.ts`.
- Route all backend calls through `app/client/src/app/core/api.ts`.

### Typing and data safety

- Avoid `any`; prefer explicit interfaces and narrowing from `unknown`.
- Validate API response shape before rendering.
- Keep shared type aliases and payload contracts centralized.

### Component and state design

- Keep page orchestration in `pages/*`.
- Keep reusable presentational blocks in `components/*`.
- Keep API/state utilities in `core/*`.
- Represent async UI status explicitly (`loading`, `complete`, `failed`, etc.).

### UX and accessibility coding

- Implement explicit loading, empty, and error states.
- Preserve keyboard access and visible focus behavior.
- Use semantic HTML and avoid color-only meaning.

### Build and tests

- Maintain `npm run build` success in `app/client`.
- Update E2E tests for user-visible behavior changes.
- Keep regressions covered in `app/tests/e2e` where flows are affected.

## Cross-Language Rules

- Keep API contracts synchronized between backend Pydantic models and frontend TS types.
- Prefer additive, scoped changes over broad refactors.
- Remove dead code and obsolete artifacts when identified.
- Avoid duplicate logic across layers when a shared contract can serve.
- Keep docs in `assets/docs` updated in the same change when behavior or conventions change.
- New static catalog/reference data must be added under `app/resources/catalog/reference`, not hardcoded in Python constants.

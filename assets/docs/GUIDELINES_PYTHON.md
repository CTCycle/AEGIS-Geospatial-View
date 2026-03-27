# Python Engineering Guidelines

Last updated: 2026-03-28  
Scope: `AEGIS/server`, Python tooling in repo root

## 1. Baseline

- Required Python: `>=3.14` (`pyproject.toml`).
- Dependency/environment management: `uv`.
- Primary style and quality tools: Ruff, mypy, pytest.

## 2. Typing Rules

- Type all public functions, methods, and non-trivial internal interfaces.
- Prefer built-in generics (`list[str]`, `dict[str, Any]`) over legacy typing aliases.
- Use `|` unions (`str | None`) instead of `Optional`.
- Import `Callable` from `collections.abc`.
- Treat mypy failures as defects to fix, not warnings to ignore.

## 3. Imports and Module Structure

- Keep imports at top-level.
- Avoid conditional imports unless strictly necessary for optional runtime paths.
- Keep modules cohesive: API layer, service layer, repository layer, and utilities should stay separated.
- Do not place business logic directly in route handlers when it belongs in services.

## 4. FastAPI Conventions

- Keep routes in `AEGIS/server/api`.
- Keep request/response models in `AEGIS/server/domain`.
- Raise `HTTPException` with clear, user-actionable messages.
- Use async endpoints only when needed, and isolate blocking work with safe offloading (`asyncio.to_thread`) where applicable.

## 5. Error and Logging Practices

- Fail with specific exceptions at service boundaries.
- Preserve root cause in logs.
- Avoid swallowing exceptions silently.
- Keep user-facing error messages concise and safe.

## 6. Data and Persistence

- Repository/database access belongs in `AEGIS/server/repositories`.
- Keep ORM entities and serialization concerns separate.
- Ensure DB backend behavior remains compatible with both SQLite and PostgreSQL modes.

## 7. Testing Expectations

- Add/update tests when API behavior, validation rules, or integration flow changes.
- Cover success path, validation path, and error path for touched logic.
- Use pytest and existing fixtures from `tests/conftest.py`.

## 8. Quality Gate Checklist

Before completion:
1. Ruff passes.
2. mypy passes for touched modules (when configured for them).
3. Relevant pytest/E2E checks pass, or explicitly report what was not run.

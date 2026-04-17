# Python Engineering Guidelines

Last updated: 2026-04-08
Scope: `AEGIS/server`, Python tooling in repo root

## 1. Baseline

- Required Python: `>=3.14` (`pyproject.toml`).
- Dependency/environment management: `uv`.
- Primary quality tools: Ruff, mypy, pytest.

## 2. Typing Rules

- Type all public functions, methods, and non-trivial internal interfaces.
- Prefer built-in generics (`list[str]`, `dict[str, Any]`) over legacy aliases.
- Use `|` unions (`str | None`) instead of `Optional`.
- Import `Callable` from `collections.abc`.
- Treat mypy failures as defects.

## 3. Imports and Module Structure

- Keep imports at top-level.
- Avoid conditional imports unless required for optional runtime paths.
- Keep API, service, repository, and utility concerns separated.
- Keep business logic out of route handlers.
- Avoid mutable module-level globals and `global` declarations; pass dependencies explicitly or use immutable/config-driven patterns.

## 4. FastAPI Conventions

- Keep routes in `AEGIS/server/api`.
- Keep request/response models in `AEGIS/server/domain`.
- Raise `HTTPException` with clear actionable messages.
- Use async endpoints where needed and offload blocking work safely.

## 5. Error and Logging Practices

- Fail with specific exceptions at service boundaries.
- Preserve root cause in logs.
- Avoid silent exception swallowing.
- Keep user-facing error text concise and safe.

## 6. Data and Persistence

- Keep repository/database access in `AEGIS/server/repositories`.
- Keep ORM entities and serialization boundaries explicit.
- Maintain compatibility with SQLite and PostgreSQL runtime modes.

## 7. Testing Expectations

- Update tests when API behavior, validation, or integration flow changes.
- Cover success, validation, and error paths for touched logic.
- Reuse pytest fixtures from `tests/conftest.py`.

## 8. Quality Gate Checklist

Before completion:
1. Ruff passes.
2. mypy passes for touched modules where configured.
3. Relevant pytest/E2E checks pass, or explicitly report what was not run.

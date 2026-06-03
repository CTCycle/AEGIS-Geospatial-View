# Python

Last updated: 2026-06-02

## Baseline

- Target version: `>=3.14`
- Use the existing repository virtual environment, preferring `app/server/.venv` and then `runtimes/.venv`
- Keep dependency state aligned with `app/server/pyproject.toml` and `app/server/uv.lock`
- Do not create ad-hoc environments

## Typing

- Type annotations are required for public APIs and non-trivial logic.
- Use built-in generics such as `list[str]`.
- Prefer `|` unions.
- Use `collections.abc` for abstract collection and callable types.
- Treat typing as a quality gate.

## Validation And Contracts

- Use Pydantic and domain models for request and response contracts.
- Prefer schema-driven validation over ad-hoc validation blocks.
- Use explicit HTTP status codes and consistent response models.
- Never leak secrets or credentials in errors.
- Preserve job and request traceability.

## Async And Background Work

- Use async only when dependencies are non-blocking.
- Keep CPU-heavy work out of async handlers.
- Use the existing `JobManager` pattern for long-running map operations.
- Long-running APIs must support start, poll, and cancel flows.

## Code Structure

- Keep functions focused and deterministic where practical.
- Make side effects explicit at I/O, database, and network boundaries.
- Prefer composition over deep indirection.
- Keep imports at module top.
- Avoid nested function definitions unless narrowly justified.
- Use classes when they improve cohesion around shared state or behavior.

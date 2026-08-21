# Testing And Quality

Last updated: 2026-08-20

## Python Quality Gates

- Lint and format with Ruff or the project-standard equivalent.
- Run Pyright in strict mode across the complete `app/server` package using
  `app/server/pyproject.toml`; do not narrow the include list to selected
  modules to avoid diagnostics.
- Maintain Pylance-compatible typing discipline without suppressing newly
  exposed backend diagnostics.
- Test backend behavior with pytest.
- Persistence tests are SQLite-only and must cover the concrete engine,
  migrations, transactions, rollback behavior, and isolated startup paths.
- Validate database changes through Alembic; use `Base.metadata.create_all()`
  only in isolated tests that explicitly exercise ORM fixture construction.
- Keep one migration head and run `alembic current --check-heads` and
  `alembic check` before release.

The bounded backend validation sequence is:

```text
ruff check app/server app/tests
pyright --project app/server/pyproject.toml
python -m pytest -c app/server/pyproject.toml app/tests/unit -q
```

`app/tests/run_tests.bat` does not start the frontend for a bounded backend
target. Full-suite and E2E targets retain frontend startup because those tests
depend on the UI runtime.

## Development Cache And Artifact Locations

Disposable development state is split between runtime and test-tool cache roots:

- uv, pip, npm, Python bytecode, and Playwright state: named subdirectories
  under `runtimes/cache`
- pytest cache: `app/tests/cache/pytest`
- pytest temporary directories: `app/tests/cache/pytest-tmp`
- Ruff cache: `app/tests/cache/ruff`
- Angular CLI cache and Karma coverage: `app/tests/cache/angular` and
  `app/tests/cache/coverage`
- Other test and migration-tool state belongs under `app/tests/cache`

Run quality commands from the repository root so the configured relative paths
resolve to these roots. `app/tests/run_tests.bat`, the Windows launcher, and CI
also set absolute cache environment variables. Retained QA evidence remains
under `assets/QA`.

## Frontend Quality Gates

- Maintain `npm run build` success in `app/client`.
- Keep relevant frontend tests passing.
- Update E2E coverage for user-visible workflow changes.
- Browser smoke coverage lives in `app/client/src/app/e2e`; backend/API E2E
  coverage lives in `app/tests/e2e`.

## Scope Expectations

- Cover `app/tests/unit` for contract and logic changes.
- Cover relevant `app/tests/e2e` when user-facing behavior changes.
- Prefer targeted regression coverage over broad speculative tests.
- For provider, catalog, clarification, overlay-removal, or run-stream changes,
  assert both the structured response contract and the user-visible failure or
  clarification state.

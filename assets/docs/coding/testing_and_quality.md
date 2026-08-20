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

Disposable development-tool state is centralized under `assets/cache`:

- pytest cache: `assets/cache/pytest`
- pytest temporary directories: `assets/cache/pytest-tmp`
- Ruff cache: `assets/cache/ruff`
- Python bytecode, uv, pip, npm, Playwright, and coverage state: their named
  subdirectories under `assets/cache`
- Angular CLI cache and Karma coverage: `assets/cache/angular` and
  `assets/cache/coverage`

Run quality commands from the repository root so the configured relative paths
resolve to this shared cache root. `app/tests/run_tests.bat`, the Windows
launcher, and CI also set absolute cache environment variables. Retained QA
evidence remains under `assets/QA`.

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

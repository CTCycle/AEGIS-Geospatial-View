# Testing And Quality

Last updated: 2026-07-30

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

## Frontend Quality Gates

- Maintain `npm run build` success in `app/client`.
- Keep relevant frontend tests passing.
- Update E2E coverage for user-visible workflow changes.

## Scope Expectations

- Cover `app/tests/unit` for contract and logic changes.
- Cover relevant `app/tests/e2e` when user-facing behavior changes.
- Prefer targeted regression coverage over broad speculative tests.

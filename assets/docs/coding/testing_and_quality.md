# Testing And Quality

Last updated: 2026-06-02

## Python Quality Gates

- Lint and format with Ruff or the project-standard equivalent.
- Maintain Pylance-compatible typing discipline.
- Test backend behavior with pytest.

## Frontend Quality Gates

- Maintain `npm run build` success in `app/client`.
- Keep relevant frontend tests passing.
- Update E2E coverage for user-visible workflow changes.

## Scope Expectations

- Cover `app/tests/unit` for contract and logic changes.
- Cover relevant `app/tests/e2e` when user-facing behavior changes.
- Prefer targeted regression coverage over broad speculative tests.

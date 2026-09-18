# Testing And Quality

Last updated: 2026-09-18

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
cd app/server
ruff check server ../tests
pyright --project pyproject.toml
python -m pytest -c pyproject.toml ../tests/unit -q
```

The current unit run emits two known upstream deprecation warnings (Google
GenAI and Starlette/httpx). They remain deferred P3 maintenance work and do
not convert otherwise passing tests into failures.

`app/tests/run_tests.bat` does not start the frontend for a bounded backend
target. Full-suite and E2E targets retain frontend startup because those tests
depend on the UI runtime.

## Development Cache And Artifact Locations

`runtimes/cache` is the only disposable cache root. Its subdirectories are
stable across launchers, CI, development, and tests:

- `uv`, `npm`, `pip`: package-manager caches
- `python`: Python bytecode cache prefix
- `playwright-browsers`: Playwright browser state
- `pytest`, `pytest-tmp`: pytest's cache provider and temporary roots
- `ruff`: Ruff's cache
- `angular`: Angular CLI cache
- `coverage`: Python and Karma coverage output
- `test-runtime`: disposable test databases and migration state

Retained QA evidence is not cache data: screenshots, reports, logs, and
validation notes remain under `assets/QA` and are not removed by cache cleanup.

When `AEGIS_DATA_DIR` is not explicitly supplied, the pytest configuration
assigns a session-scoped temporary runtime directory. Application-startup unit
tests therefore never open or mutate `app/resources/runtime/database.db`.
Source-architecture scans exclude `.venv` and `__pycache__` trees so protected
dependency files cannot turn a test run into an ACL failure.

Run quality commands through `app/tests/run_tests.bat`, the Windows launcher,
or CI so absolute cache environment variables and pytest's canonical
`--basetemp` are supplied. Pytest rejects cache or temporary roots outside
`runtimes/cache`; direct commands must provide the same absolute settings.
Ruff's project configuration is resolved from `app/server`, or can be
overridden with the absolute `RUFF_CACHE_DIR` value for a repository-root
invocation.

The canonical status of local, browser, provider, migration, and hosted-CI
gates is maintained in
[`assets/docs/validation/gate_status.md`](../validation/gate_status.md).
Every entry must identify the exact command/evidence, date, and one of
`PASS`, `PARTIAL`, `FAIL`, `BLOCKED`, or `NOT RUN`; a build or catalog probe
does not promote a completion-path gate.

## Frontend Quality Gates

- Maintain `npm run build` success in `app/client`.
- Keep relevant frontend tests passing.
- Update E2E coverage for user-visible workflow changes.
- Parser tests must cover complete contracts, valid intentional ambiguity,
  sparse/default-only `contract_incomplete` failures, the 75/30-second budgets,
  bounded schema correction, and field-specific clarification questions.
- Structured-probe tests must cover `not_tested`, `passed`, `failed`, `timeout`,
  and `unsupported`, sanitized messages, 15-minute expiry, cache invalidation
  after settings changes, and the absence of conversation/tool/map side effects.
- Browser smoke coverage lives in `app/client/src/app/e2e`; backend/API E2E
  coverage lives in `app/tests/e2e`.

Map-oriented E2E tests must prove the complete controlled path, including
canonical interpretation, location/scope validation, capability execution,
candidate map assembly, persistence, realtime `map_prepared`, MapLibre
settlement, and `map.render_ack`. HTTP 200, a successful provider call, a
non-empty descriptor, or a visible canvas is not sufficient evidence. Each
scenario records request/run/version IDs, expected and actual bounds, required
source/layer IDs, feature or raster evidence, collection revisions,
acknowledgment, screenshot, and sanitized console/failure data under
`assets/QA/`.

Render acknowledgments identify overlay instances directly first. A capability
ID is accepted only as a unique alias for one required instance. Every
non-metadata candidate must prove source, layer presence, loading, and matching
visibility. `layer_present` means only that a MapLibre layer exists with valid
style/zoom; visible feature evidence is required only for feature-bearing
instances expected to be visible, while intentionally hidden instances prove
`visibility_matches`.

Keep controlled fixtures and live-provider runs separate. Controlled fixtures
use meaningful visible vector/raster data and exercise the real frontend and
acknowledgment handler. Live runs use the configured model and providers without
silent substitution; absent credentials, unsupported coverage, or no usable
browser are recorded as limitations or blocked evidence rather than passes. A
decryptable credential or successful model-catalog request is not completion-
path proof. The 20-row provider/parser/map matrix remains unverified until the
selected provider/model completes that exact live path.

## Scope Expectations

- Cover `app/tests/unit` for contract and logic changes.
- Cover relevant `app/tests/e2e` when user-facing behavior changes.
- Prefer targeted regression coverage over broad speculative tests.
- For provider, catalog, clarification, overlay-removal, or run-stream changes,
  assert both the structured response contract and the user-visible failure or
  clarification state.

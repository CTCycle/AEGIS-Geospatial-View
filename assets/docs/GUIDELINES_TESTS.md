# Testing Guidelines

Last updated: 2026-03-28  
Scope: `tests/`, backend/frontend integration flows

This project validates behavior primarily with end-to-end tests that exercise backend + frontend together.

## 1. Test Stack

- Framework: `pytest`
- Browser automation and API client: Playwright for Python (`pytest-playwright`)
- Main test suite location: `tests/e2e`

## 2. Primary Runner

Recommended command on Windows:

```cmd
tests\run_tests.bat
```

`run_tests.bat` performs:
1. Runtime prerequisite checks
2. Playwright browser availability check/install
3. Backend startup
4. Frontend startup/build as needed
5. Pytest execution
6. Cleanup (port/process shutdown)

## 3. Runtime and Ports

- Tests use portable runtimes from `runtimes/`.
- If `AEGIS/settings/.env` exists, host/port values are loaded from it.
- If no `.env` is present, test runner falls back to:
  - backend: `127.0.0.1:8000`
  - frontend: `127.0.0.1:7861`

## 4. Manual Execution

Typical manual invocation from repo root:

```cmd
uv run pytest tests -v --tb=short
```

Common options:
- `--headed`
- `--slowmo 500`
- `-k "name_fragment"`
- `-x`

## 5. Writing Tests

- Place E2E tests in `tests/e2e`.
- Name files `test_*.py`.
- Reuse fixtures from `tests/conftest.py` (`page`, `api_context`, URL fixtures).
- Cover:
  - happy path
  - validation failures
  - external-service degradation behavior where applicable

## 6. External Dependencies

`/maps/search` and related flows call external services (Nominatim, NASA GIBS, OpenAQ, Open-Elevation).

Implications:
- Network availability affects E2E reliability.
- Tests should gracefully skip or assert expected fallback behavior when upstream services are unavailable.

## 7. Troubleshooting

- Connection refused: verify backend/frontend startup logs and resolved ports.
- Browser install issues: run `uv run python -m playwright install`.
- Timeout-heavy runs: check network access and external API responsiveness.

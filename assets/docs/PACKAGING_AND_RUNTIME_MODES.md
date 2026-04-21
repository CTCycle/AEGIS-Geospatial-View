# AEGIS Packaging and Runtime Modes

Last updated: 2026-04-09

## 1. Runtime Strategy

AEGIS uses a single active environment file:
- `AEGIS/settings/.env`

Profiles provided:
- `AEGIS/settings/.env.local.example`
- `AEGIS/settings/.env.local.tauri.example`

Runtime switching is configuration-driven.

## 2. Supported Modes

### Local mode (default for development)
- Start with `AEGIS/start_on_windows.bat`.
- Uses portable runtimes under `runtimes/`.

### Desktop packaging (Tauri)
- Uses local-tauri env profile and desktop build scripts.
- Produces installer and portable artifacts under `release/windows`.

## 3. Environment Keys

| Key | Purpose |
|---|---|
| `FASTAPI_HOST`, `FASTAPI_PORT` | Backend host/port binding |
| `UI_HOST`, `UI_PORT` | Frontend host/port binding |
| `KERAS_BACKEND`, `MPLBACKEND` | Runtime library backend selection |
| `RELOAD` | Backend hot reload toggle |
| `OPTIONAL_DEPENDENCIES` | Optional install behavior in launcher |
| `AEGIS_CREDENTIAL_MASTER_KEY` | Credential encryption master key |
| `AEGIS_CREDENTIAL_KEY_VERSION` | Credential key version tag |

Frontend proxying:
- Angular dev server reads backend host/port from `AEGIS/settings/.env` via `AEGIS/client/proxy.conf.cjs`.
- API requests are served through `/api` and proxied to backend.

## 4. Database Configuration (JSON)

Database behavior is configured only in:
- `AEGIS/settings/configurations.json`

Relevant keys under `database`:
- `embedded_database`
- `engine`
- `host`
- `port`
- `database_name`
- `username`
- `password`
- `ssl`
- `ssl_ca`
- `connect_timeout`
- `insert_batch_size`

## 5. Local Workflow

```cmd
copy /Y AEGIS\settings\.env.local.example AEGIS\settings\.env
AEGIS\start_on_windows.bat
```

## 6. Tauri Workflow

```cmd
copy /Y AEGIS\settings\.env.local.tauri.example AEGIS\settings\.env
AEGIS\start_on_windows.bat
release\tauri\build_with_tauri.bat
```

## 7. Deterministic Build Notes

- Python dependencies are lockfile-backed with `runtimes/uv.lock`.
- Frontend dependencies are lockfile-backed with `AEGIS/client/package-lock.json`.
- Backend runtime dependencies include `langchain-core`, `langchain-openai`, `langchain-google-genai`, and `langchain-ollama`.
- Do not commit environment secrets in `.env` files.

## 8. Ollama Runtime Contract

- AEGIS does not auto-start Ollama.
- Ollama integration is connection-only (health, refresh, pull).
- Browser and desktop behavior are aligned.

## 9. Validation Prerequisites

- Backend unit tests: `uv sync --extra test` then `uv run pytest -q tests/unit`.
- Frontend production validation: install deps in `AEGIS/client`, then `npm run build`.

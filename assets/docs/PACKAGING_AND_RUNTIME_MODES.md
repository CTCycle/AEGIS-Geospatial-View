# AEGIS Packaging and Runtime Modes

Last updated: 2026-04-08

## 1. Runtime Strategy

AEGIS uses a single active environment file:
- `AEGIS/settings/.env`

Profiles provided:
- `AEGIS/settings/.env.local.example`
- `AEGIS/settings/.env.local.tauri.example`
- `AEGIS/settings/.env.cloud.example`

Runtime switching is configuration-driven.

## 2. Supported Modes

### Local mode (default for development)
- Start with `AEGIS/start_on_windows.bat`.
- Uses portable runtimes under `runtimes/`.

### Cloud mode (Docker)
- Uses `docker compose` with env file values.
- Backend and frontend run in separate containers.
- Frontend serves SPA and proxies `/api` to backend.

### Desktop packaging (Tauri)
- Uses local-tauri env profile and desktop build scripts.
- Produces installer and portable artifacts under `release/windows`.

## 3. Environment Keys

| Key | Purpose |
|---|---|
| `FASTAPI_HOST`, `FASTAPI_PORT` | Backend host/port binding |
| `UI_HOST`, `UI_PORT` | Frontend host/port binding |
| `VITE_API_BASE_URL` | Frontend API base path |
| `RELOAD` | Backend hot reload toggle |
| `DB_EMBEDDED` | SQLite vs external DB switch |
| `DB_ENGINE`, `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, `DB_PASSWORD` | External DB connection config |
| `DB_SSL`, `DB_SSL_CA` | External DB TLS options |
| `DB_CONNECT_TIMEOUT`, `DB_INSERT_BATCH_SIZE` | DB runtime tuning |
| `OPTIONAL_DEPENDENCIES` | Optional install behavior in launcher |
| `MPLBACKEND`, `KERAS_BACKEND` | Runtime backend configuration |
| `AEGIS_CREDENTIAL_MASTER_KEY` | Credential encryption master key |
| `AEGIS_CREDENTIAL_KEY_VERSION` | Credential key version tag |

## 4. Local Workflow

```cmd
copy /Y AEGIS\settings\.env.local.example AEGIS\settings\.env
AEGIS\start_on_windows.bat
```

## 5. Cloud Workflow (Docker)

```cmd
copy /Y AEGIS\settings\.env.cloud.example AEGIS\settings\.env
docker compose --env-file AEGIS/settings/.env build --no-cache
docker compose --env-file AEGIS/settings/.env up -d
```

Stop:

```cmd
docker compose --env-file AEGIS/settings/.env down
```

## 6. Deterministic Build Notes

- Python dependencies are lockfile-backed with `runtimes/uv.lock`.
- Frontend dependencies are lockfile-backed with `AEGIS/client/package-lock.json`.
- Do not commit environment secrets in `.env` files.

## 7. Ollama Runtime Contract

- AEGIS does not auto-start Ollama.
- Ollama integration is connection-only (health, refresh, pull).
- Browser and desktop behavior are aligned.

## 8. Validation Prerequisites

- Backend unit tests: `uv sync --extra test` then `uv run pytest -q tests/unit`.
- Frontend production validation: install deps in `AEGIS/client`, then `npm run build`.

# AEGIS Packaging and Runtime Modes

Last updated: 2026-04-03

## 1. Runtime Strategy

AEGIS uses a single active environment file:
- `AEGIS/settings/.env`

Profiles provided:
- `AEGIS/settings/.env.local.example`
- `AEGIS/settings/.env.cloud.example`

Runtime mode switching is configuration-driven (no separate code branches for business logic).

## 2. Supported Modes

### Local mode (default for development)
- Start with `AEGIS/start_on_windows.bat`.
- Uses portable runtimes under `runtimes/`.
- Typical host binding values are loopback (`127.0.0.1`).

### Cloud mode (Docker)
- Uses `docker compose` with env file values.
- Backend and frontend run in separate containers.
- Frontend serves SPA and proxies `/api` to backend.

## 3. Environment Keys

| Key | Purpose |
|---|---|
| `FASTAPI_HOST`, `FASTAPI_PORT` | Backend host/port binding |
| `UI_HOST`, `UI_PORT` | Frontend host/port binding |
| `VITE_API_BASE_URL` | Frontend API base path (keep `/api` for proxied deployments) |
| `RELOAD` | Backend hot-reload toggle for local use |
| `DB_EMBEDDED` | `true`: SQLite embedded mode, `false`: external DB mode |
| `DB_ENGINE`, `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, `DB_PASSWORD` | External DB connection config |
| `DB_SSL`, `DB_SSL_CA` | External DB TLS options |
| `DB_CONNECT_TIMEOUT`, `DB_INSERT_BATCH_SIZE` | DB runtime tuning |
| `OPTIONAL_DEPENDENCIES` | Controls extra dependency install behavior in launcher |
| `MPLBACKEND`, `KERAS_BACKEND` | Runtime backend configuration for plotting/ML dependencies |
| `AEGIS_CREDENTIAL_MASTER_KEY` | Master key for encrypting cloud provider credentials at rest |
| `AEGIS_CREDENTIAL_KEY_VERSION` | Encryption key version tag stored alongside encrypted secrets |

## 4. Local Workflow

1. Populate active env file (copy local example if needed).
2. Run:

```cmd
AEGIS\start_on_windows.bat
```

3. (Optional) Run E2E suite:

```cmd
tests\run_tests.bat
```

## 5. Cloud Workflow (Docker)

1. Populate active env with cloud values.
2. Build images:

```cmd
docker compose --env-file AEGIS/settings/.env build --no-cache
```

3. Start:

```cmd
docker compose --env-file AEGIS/settings/.env up -d
```

4. Stop:

```cmd
docker compose --env-file AEGIS/settings/.env down
```

## 6. Deterministic Build Notes

- Python dependencies are lockfile-backed with `runtimes/uv.lock` and installed via `uv sync`.
- Frontend dependencies are lockfile-backed with `AEGIS/client/package-lock.json` and installed via `npm ci`.
- Do not commit environment secrets in `.env` files.

## 7. Ollama Runtime Contract

- AEGIS does not start Ollama automatically in browser or Tauri mode.
- Ollama integration is connection-only: configure URL, validate health, refresh/pull models via API.
- Desktop and browser behavior are intentionally aligned (no desktop-only process spawn path).

## 8. Validation Prerequisites

- Backend unit tests require project and test extras installed (`uv sync --extra test`).
- Plain `pytest` collection expects repository root on import path (configured in `pyproject.toml`).
- Frontend production validation requires installed npm dependencies in `AEGIS/client` before `npm run build`.

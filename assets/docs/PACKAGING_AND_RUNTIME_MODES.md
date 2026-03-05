# AEGIS Packaging and Runtime Modes

## 1. Strategy

AEGIS uses one active runtime file: `AEGIS/settings/.env`.

- Local mode: run directly on host with `AEGIS/start_on_windows.bat` (default workflow).
- Cloud mode: run with Docker (`backend` + `frontend`).
- Mode switching: replace values in `AEGIS/settings/.env` only.
- Runtime mode switches are configuration-only; business logic does not branch by mode.

## 2. Runtime Profiles

- `AEGIS/settings/.env.local.example`: local defaults (loopback host values, embedded DB enabled).
- `AEGIS/settings/.env.cloud.example`: cloud defaults (bind host values, external DB enabled).
- `AEGIS/settings/.env`: active profile consumed by launcher, tests, and Docker runtime env loading.
- `AEGIS/settings/configurations.json`: non-runtime defaults and service configuration fallback.

## 3. Required Environment Keys

| Key | Purpose |
|---|---|
| `FASTAPI_HOST`, `FASTAPI_PORT` | Backend host/port in local mode and host-published backend port in Docker compose mapping. |
| `UI_HOST`, `UI_PORT` | Frontend host/port in local mode and host-published frontend port in Docker compose mapping. |
| `VITE_API_BASE_URL` | Frontend API base path; keep `/api` for same-origin proxying in cloud mode. |
| `RELOAD` | Enables backend reload when running locally. |
| `DB_EMBEDDED` | `true` uses SQLite; `false` enables external DB settings. |
| `DB_ENGINE`, `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, `DB_PASSWORD` | External DB connection settings when `DB_EMBEDDED=false`. |
| `DB_SSL`, `DB_SSL_CA` | External DB TLS settings. |
| `DB_CONNECT_TIMEOUT`, `DB_INSERT_BATCH_SIZE` | DB connection and write-batching runtime settings. |
| `OPTIONAL_DEPENDENCIES` | Enables optional dependency install path in local launcher. |
| `MPLBACKEND`, `KERAS_BACKEND` | Runtime backend selection for plotting and ML stack. |

## 4. Local Mode (Default)

1. Copy local profile values into active env:
   - `copy /Y AEGIS\settings\.env.local.example AEGIS\settings\.env`
2. Start application:
   - `AEGIS\start_on_windows.bat`
3. Run tests (optional):
   - `tests\run_tests.bat`

Local mode does not require Docker.

## 5. Cloud Mode (Docker)

1. Copy cloud profile values into active env:
   - `copy /Y AEGIS\settings\.env.cloud.example AEGIS\settings\.env`
2. Build images (reproducibility check):
   - `docker compose --env-file AEGIS/settings/.env build --no-cache`
3. Start containers:
   - `docker compose --env-file AEGIS/settings/.env up -d`
4. Stop containers:
   - `docker compose --env-file AEGIS/settings/.env down`

Cloud topology:
- `backend`: FastAPI/Uvicorn container on internal port `8000`.
- `frontend`: Nginx container serving SPA static assets.
- `/api` on frontend origin is reverse-proxied to backend (`http://backend:8000/`).
- Backend host publishing is loopback-bound (`127.0.0.1:${FASTAPI_PORT}:8000`) to reduce direct external exposure.
- Nginx denies direct access to `/api/docs`, `/api/redoc`, `/api/openapi.json`, and `/api/maps/jobs*` in cloud mode.

Cloud security notes:
- Keep `VITE_API_BASE_URL=/api`; production frontend builds fall back to `/api` when given non-relative API bases.
- Do not commit real credentials in `AEGIS/settings/.env`; use environment-specific secrets at deploy time.

## 6. Deterministic Build Notes

- Backend dependency graph is lockfile-backed via `uv.lock` and installed with `uv sync --frozen`.
- Frontend dependency graph is lockfile-backed via `AEGIS/client/package-lock.json` and installed with `npm ci`.
- Docker base images are pinned with explicit tags in `docker/backend.Dockerfile` and `docker/frontend.Dockerfile`.

# AEGIS Geospatial View Architecture

Last updated: 2026-04-08
Scope: `AEGIS/` and `tests/`

## 1. System Overview

AEGIS Geospatial View is a chat-first geospatial application with a React frontend and FastAPI backend. The backend handles geospatial search orchestration, chat orchestration, model/provider settings, and map payload generation.

Main stack:
- Frontend: React 18 + TypeScript 5 + Vite 6 (`AEGIS/client`)
- Backend: FastAPI (`AEGIS/server`)
- Persistence: SQLAlchemy with SQLite (embedded) or PostgreSQL (external)
- Rendering: Folium + Pillow

## 2. Runtime and Deployment

- Python requirement: `>=3.14` (`pyproject.toml`)
- Frontend runtime baseline: Node.js 22 (portable runtime in launcher flow)
- Primary runtime config file: `AEGIS/settings/.env`
- Local launcher: `AEGIS/start_on_windows.bat`
- E2E runner: `tests/run_tests.bat`

Typical local defaults from env examples:
- backend: `127.0.0.1:5002`
- frontend: `127.0.0.1:5000`

## 3. Repository Layout

- `AEGIS/client`: frontend application
- `AEGIS/server`: backend application
- `AEGIS/server/api`: route modules (`search.py`, `chat.py`, `access_keys.py`)
- `AEGIS/server/services`: orchestration, geospatial, jobs, llm/vector services
- `AEGIS/server/repositories`: persistence and serializers
- `AEGIS/server/domain`: request/response models
- `AEGIS/settings`: runtime env and JSON settings
- `AEGIS/resources`: local resources (manifests, runtime artifacts)
- `tests/e2e`: Playwright + pytest end-to-end tests

## 4. API Surface

Routers are mounted at both base and `/api` prefix in `AEGIS/server/app.py`.

Maps router (`/maps`):
- `GET /maps/catalog`
- `POST /maps/search`
- `POST /maps/jobs`
- `GET /maps/jobs/{job_id}`
- `DELETE /maps/jobs/{job_id}`

Chat router (`/chat`):
- `POST /chat/turn`
- `POST /chat/stream`
- `GET /chat/models`
- `GET /chat/settings`
- `PUT /chat/settings`
- `POST /chat/models/ollama/refresh`
- `POST /chat/models/ollama/pull`
- `GET /chat/models/ollama/health`
- `POST /chat/vectors/rebuild`
- `POST /chat/vectors/sync`

Access keys router (`/access-keys`):
- `GET /access-keys?provider=...`
- `POST /access-keys`
- `PUT /access-keys/{key_id}/activate?provider=...`
- `DELETE /access-keys/{key_id}?provider=...`

Root behavior:
- In Tauri packaged mode with built frontend assets, `/` serves SPA files.
- Otherwise, `/` redirects to `/docs`.

## 5. Core Execution Flows

Map search flow:
1. Request validation in API/domain models.
2. Location sanitization and geocoding.
3. Search execution orchestration (`MapSearchExecutionService`).
4. Layer/catalog composition and rendering (`MapRenderingService`).
5. Optional external enrichment (OpenAQ, Open-Elevation, PVGIS).
6. Persisted search session metadata and response payload return.

Chat flow:
1. `chat_turn`/`chat_stream` receives a user turn.
2. Vector index is ensured current (`VectorIndexer`).
3. `AgentOrchestrator` processes parsing, decisioning, tool invocation, and assistant response.
4. Structured/tool/map payloads are returned and persisted through repository-backed services.

## 6. Background Jobs

- In-process, thread-based jobs are managed by `JobManager` (`AEGIS/server/services/jobs.py`).
- Cancellation is cooperative and status is memory-backed.
- Job state is not durable across process restarts.

## 7. Frontend Architecture

- Main shell: `AEGIS/client/src/App.tsx`
- Route views:
  - `/` chat + map workspace (`GeospatialPage.tsx`)
  - `/settings` model/settings workspace (`SettingsPage.tsx`)
- Chat panel drives map updates via assistant turns.
- State persistence and navigation state are session-based (`sessionStorage`), with guardrails documented in `STATE_PRESERVATION.md`.

## 8. Integrations and Constraints

External integrations:
- OpenStreetMap Nominatim
- NASA GIBS
- OpenAQ
- Open-Elevation
- PVGIS

Known constraints:
- Background jobs are process-local.
- External API availability impacts some runtime and test paths.
- Cross-process distributed worker orchestration is not implemented in current architecture.

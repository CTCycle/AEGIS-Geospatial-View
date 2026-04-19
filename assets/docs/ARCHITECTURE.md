# AEGIS Geospatial View Architecture

Last updated: 2026-04-20
Scope: `AEGIS/` and `tests/`

## 1. System Overview

AEGIS Geospatial View is a chat-first geospatial application with an Angular frontend and FastAPI backend. The backend handles geospatial search orchestration, chat orchestration, model/provider settings, and map payload generation.

Main stack:
- Frontend: Angular 19 (standalone APIs) + TypeScript 5 (`AEGIS/client`)
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
- `AEGIS/server/common`: shared constants, logger, and type coercion helpers
- `AEGIS/settings`: runtime env and JSON settings
- `AEGIS/resources`: local resources (manifests, runtime artifacts)
- `tests/e2e`: Playwright + pytest end-to-end tests

## 4. API Surface

Routers are mounted at both base and `/api` prefix in `AEGIS/server/app.py`.

Maps router (`/maps`):
- `GET /api/maps/catalog`
- `POST /api/maps/search`
- `POST /api/maps/jobs`
- `GET /api/maps/jobs/{job_id}`
- `DELETE /api/maps/jobs/{job_id}`

Chat router (`/chat`):
- `POST /api/chat/turn`
- `POST /api/chat/stream`
- `GET /api/chat/models`
- `GET /api/chat/settings`
- `PUT /api/chat/settings`
- `POST /api/chat/models/ollama/refresh`
- `POST /api/chat/models/ollama/pull`
- `GET /api/chat/models/ollama/health`
- `POST /api/chat/vectors/rebuild`
- `POST /api/chat/vectors/sync`

Access keys router (`/api/access-keys`):
- `GET /api/access-keys?provider=...`
- `POST /api/access-keys`
- `PUT /api/access-keys/{key_id}/activate?provider=...`
- `DELETE /api/access-keys/{key_id}?provider=...`

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
2. App startup wiring builds app-scoped service dependencies (`app.state`) consumed by API handlers.
3. Startup lifecycle bootstraps SQLite (first run) and vector index bootstrap (`VectorIndexer.bootstrap_if_missing`) when enabled by `vectors.auto_sync_on_start`.
4. `AgentOrchestrator` processes parsing, raw-prompt retrieval, retrieval-availability annotation, decisioning, tool invocation, and assistant response.
5. Structured/tool/map payloads are returned and persisted through repository-backed services.

Vector subsystem responsibilities:
- `ManifestPreparationService` composes one embedding chunk per basemap/overlay manifest entry.
- `VectorIndexer` owns bootstrap, rebuild, sync, and startup-oriented metadata (`manifest_index_metadata.json`).
- `VectorRetriever` performs similarity search and uses bootstrap as defensive fallback only.
- `EmbeddingFactory` enforces one provider/model selection per persisted index build.

Agent tool awareness:
- `AgentTools.describe_tools()` exposes `location_to_coordinates` and `map_search` descriptions to decisioning.
- Direct geocode execution path is first-class and can complete without map search execution.

## 6. Background Jobs

- In-process, thread-based jobs are managed by `JobManager` (`AEGIS/server/services/jobs.py`).
- Cancellation is cooperative and status is memory-backed.
- Job state is not durable across process restarts.

## 7. Frontend Architecture

- Main shell: `AEGIS/client/src/app/app.component.ts`
- Route views:
  - `/` chat + map workspace (`geospatial-page.component.ts`)
  - `/settings` model/settings workspace (`settings-page.component.ts`)
- Router config: `AEGIS/client/src/app/app.routes.ts`
- API and persistence core modules: `AEGIS/client/src/app/core`
- Chat panel drives map updates via assistant streaming events.
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

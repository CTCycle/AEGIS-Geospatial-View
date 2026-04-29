# Architecture

Last updated: 2026-04-27
Scope: `AEGIS/`, `tests/`, `release/`

## System Overview

AEGIS Geospatial View is a two-tier application:
- Frontend: Angular 19 standalone SPA in `AEGIS/client/src`
- Backend: FastAPI application in `AEGIS/server`

The backend provides chat orchestration and geospatial search APIs. The frontend consumes `/api` endpoints and renders chat + map workflows.

## Directory and File Structure

This structure documents source and operational files (generated caches like `node_modules`, `dist`, `.angular`, and `__pycache__` are intentionally excluded).

### Repository root

```text
AEGIS Geospatial View/
  AEGIS/
    client/
      src/
      src-tauri/
      package.json
      proxy.conf.cjs
    resources/
      manifests/
      database.db
    scripts/
    server/
      api/
      common/
      configurations/
      domain/
      repositories/
      services/
      app.py
    settings/
      .env
      .env.local.example
      .env.local.tauri.example
      configurations.json
    start_on_windows.bat
    setup_and_maintenance.bat
  tests/
    e2e/
    unit/
    run_tests.bat
  release/
    tauri/
    windows/
  pyproject.toml
  README.md
```

### Backend files (`AEGIS/server`)

```text
api/
  chat.py
  search.py
common/
  constants.py
  logger.py
  types.py
configurations/
  environment.py
  management.py
  startup.py
domain/
  chat.py
  geographics.py
  gibs.py
  job_state.py
  jobs.py
  layers.py
  settings.py
  updater.py
  agent/decision.py
  agent/task_scope.py
  extraction/models.py
  llm/model_settings.py
repositories/
  chat_history.py
  credentials.py
  manifest_embeddings.py
  model_settings.py
  session_catalog.py
  session_details.py
  database/backend.py
  database/initializer.py
  database/postgres.py
  database/sqlite.py
  database/utils.py
  queries/manifest_embeddings.py
  queries/session_catalog.py
  queries/session_details.py
  schemas/models.py
  serialization/serializer.py
services/
  cryptography.py
  jobs.py
  sanitization.py
  startup_validation.py
  agent/candidate_ranker.py
  agent/capability_retriever.py
  agent/executor.py
  agent/location_memory.py
  agent/location_resolver.py
  agent/orchestrator.py
  agent/parser_service.py
  agent/policy_engine.py
  agent/tool_registry.py
  agent/tool_handlers/air_quality.py
  agent/tool_handlers/coordinates.py
  agent/tool_handlers/poi.py
  agent/tool_handlers/weather.py
  chat/composition.py
  chat/history_buffer.py
  chat/maintenance_service.py
  chat/model_library.py
  chat/plain_responder.py
  chat/settings_service.py
  geospatial/capability_registry.py
  geospatial/catalog.py
  geospatial/coverage.py
  geospatial/elevation.py
  geospatial/gibs_errors.py
  geospatial/gibs_runtime.py
  geospatial/gibs.py
  geospatial/layers.py
  geospatial/manifest_loader.py
  geospatial/maps.py
  geospatial/nominatim.py
  geospatial/openaq.py
  geospatial/openmeteo.py
  geospatial/osm_tiles.py
  geospatial/overpass.py
  geospatial/pvgis.py
  geospatial/rainviewer.py
  geospatial/rendering.py
  geospatial/runtime_registry.py
  llm/base.py
  llm/cloud_catalog.py
  llm/context_budget.py
  llm/context_builder.py
  llm/errors.py
  llm/factory.py
  llm/google_provider.py
  llm/langchain_runtime.py
  llm/ollama.py
  llm/openai_provider.py
  llm/prompts.py
  llm/response_serialization.py
  llm/structured.py
  llm/types.py
  search/composition.py
  search/errors.py
  search/execution.py
  search/orchestrator.py
  search/request_builder.py
  updater/gibs.py
  vector/chroma_store.py
  vector/embedding_factory.py
  vector/indexer.py
  vector/manifest_preparation.py
  vector/retriever.py
app.py
```

### Frontend files (`AEGIS/client/src`)

```text
main.ts
styles.css
app/
  app.component.ts
  app.config.ts
  app.routes.ts
  components/
    map-preview.component.*
    model-role-actions.component.*
    settings-icon-action.component.*
    settings-modal-shell.component.*
  core/
    api.ts
    app-state.ts
    app-state-store.service.ts
    constants.ts
    model-selection.ts
    types.ts
    user-facing-error.service.ts
    view-state-sync.service.ts
  pages/
    geospatial-page.component.*
    settings-page.component.*
```

### Manifest files (`AEGIS/resources/manifests`)

- `index.json`
- `runtime_profiles.json`
- `providers/*.json`
- `basemaps/*.json`
- `overlays/*.json`
- `tools/*.json`

### Tests

- E2E: `tests/e2e/*.py`
- Unit: `tests/unit/**/*.py`
- Runner: `tests/run_tests.bat`

## Entry Points

### Backend

- Import/runtime entry: `AEGIS/server/app.py`
- ASGI app object: `app = create_app()`
- Standard startup invocation:
  - PowerShell: `uv run python -m uvicorn AEGIS.server.app:app --host 127.0.0.1 --port 5002`
  - CMD: `uv run python -m uvicorn AEGIS.server.app:app --host 127.0.0.1 --port 5002`

### Frontend web app

- Browser bootstrap: `AEGIS/client/src/main.ts`
- Root component: `AEGIS/client/src/app/app.component.ts`
- Routes: `AEGIS/client/src/app/app.routes.ts`

### Desktop packaging

- Tauri config: `AEGIS/client/src-tauri/tauri.conf.json`
- Packaging script: `release/tauri/build_with_tauri.bat`

## API Endpoints

All routers are mounted with prefix `/api` in `AEGIS/server/app.py`.

### Search endpoints (`AEGIS/server/api/search.py`)

- `GET /api/maps/catalog`  
  Returns `GeospatialCatalogResponse`.

- `GET /api/maps/basemaps/osm/{z}/{x}/{y}.png`  
  Proxies OSM basemap tiles.

- `POST /api/maps/search`  
  Synchronous location search (`LocationSearchRequest` -> `SearchByLocationResponse`).

- `POST /api/maps/jobs`  
  Starts async search job (`LocationSearchRequest` -> `JobStartResponse`, HTTP 202).

- `GET /api/maps/jobs/{job_id}`  
  Polls async job status (`JobStatusResponse`).

- `DELETE /api/maps/jobs/{job_id}`  
  Requests async job cancellation (`JobCancelResponse`).

### Chat/settings/model endpoints (`AEGIS/server/api/chat.py`)

- `POST /api/chat/turn`  
  Executes chat turn and returns structured turn response.

- `POST /api/chat/stream`  
  NDJSON event stream for progressive chat output.

- `GET /api/chat/models`  
  Returns cloud/local model library.

- `GET /api/chat/settings`  
  Reads model/provider settings.

- `PUT /api/chat/settings`  
  Updates model/provider settings and credentials.

- `POST /api/chat/models/ollama/refresh`  
  Refreshes local Ollama model list.

- `POST /api/chat/models/ollama/pull`  
  Pulls requested Ollama model.

- `GET /api/chat/models/ollama/health`  
  Checks Ollama health.

- `POST /api/chat/vectors/rebuild`  
  Rebuilds vector index.

- `POST /api/chat/vectors/sync`  
  Syncs vector index with manifests.

## Layered Architecture and Responsibilities

### Backend request flow

- API layer: `AEGIS/server/api/*.py`
- Service/orchestration layer: `AEGIS/server/services/**`
- Persistence layer: `AEGIS/server/repositories/**`
- Contracts/domain models: `AEGIS/server/domain/**`

Representative path:
- endpoint (`chat.py` / `search.py`) -> service composition (`services/*/composition.py`) -> orchestration/execution (`services/agent`, `services/search`, `services/geospatial`) -> repository/database operations (`repositories/*`)

Layering constraints:
- API routes translate service exceptions into HTTP responses.
- Services do not import FastAPI.
- Repositories remain the persistence boundary.

### Chat orchestration pipeline

1. `AgentOrchestrator` receives chat turn.
2. `ParserService` produces structured parse output.
3. `PolicyEngine` resolves decision and execution plan.
4. Execution branch:
   - direct tool via `ToolRegistry` handlers, or
   - map search via `RequestBuilder` + `LocationSearchOrchestrator`.
5. Response payload persisted through repositories (chat history/session tables).

### Geospatial capability pipeline

- `manifest_loader.py` reads manifests.
- `capability_registry.py` builds capability catalog.
- `runtime_registry.py` applies runtime/credential availability.
- `catalog.py` and `search/orchestrator.py` consume resolved capabilities.

## Data Persistence

### Relational storage

- Runtime selector: `AEGIS/server/repositories/database/backend.py`
- Modes:
  - SQLite (`database.embedded_database: true`) via `sqlite.py`
  - PostgreSQL (`embedded_database: false`) via `postgres.py`
- Settings source: `AEGIS/settings/configurations.json`

Core tables (defined in constants/schema layer) include:
- chat sessions/messages
- model provider settings
- encrypted model credentials
- geospatial metadata/session data

### Vector persistence

- Vector services in `AEGIS/server/services/vector/*`
- Index lifecycle managed by `VectorIndexer` and maintenance endpoints.

### Frontend persistence

- `sessionStorage` state snapshot key: `aegis:webapp-state:v3`
- TTL: 6 hours
- Tab ownership guard via heartbeat keys in `localStorage`
- Implementation: `AEGIS/client/src/app/core/app-state.ts`

## Async vs Sync Behavior

### Async

- FastAPI route handlers are predominantly `async`.
- `POST /api/chat/stream` uses streaming NDJSON responses.
- Search endpoints can run asynchronously through job APIs (`/api/maps/jobs`).

### Sync/Threaded

- Job runtime is in-process threaded (`JobManager` with `threading.Thread`).
- `MapSearchExecutionService.start_search_job` uses synchronous runner bridge (`asyncio.run(...)`) inside job threads.
- Cancellation is cooperative (`stop_requested` flag), not forceful thread termination.

### Constraints

- Job state is memory-backed and process-local (lost on restart).
- High-concurrency/distributed workloads require external queue/worker replacement.
- Async endpoints must avoid blocking CPU-bound work on the event loop.

## Frontend Architecture

- Route-level pages:
  - `GeospatialPageComponent` (`/`) for chat + map workspace
  - `SettingsPageComponent` (`/settings`) for model/provider and credential management
- API client + response normalization: `core/api.ts`
- Persisted view/application state: `core/app-state.ts` + store service
- Map rendering surface: `components/map-preview.component.*`

## External Integrations

External providers are used through service modules and manifests:
- OpenStreetMap/Nominatim
- NASA GIBS
- OpenAQ
- Open-Meteo
- Overpass
- PVGIS
- Rainviewer
- LLM providers: Ollama, OpenAI-compatible, Google-compatible


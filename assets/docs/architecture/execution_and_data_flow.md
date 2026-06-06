# Execution And Data Flow

Last updated: 2026-06-06

## Layering

AEGIS uses these main backend layers:

- API routes: `app/server/api/*.py`
- Services and orchestration: `app/server/services/**`
- Persistence: `app/server/repositories/**`
- Domain contracts: `app/server/domain/**`
- Configuration models: `app/server/configurations/**`

## Layering Rules

- API routes translate service exceptions into HTTP responses.
- Services do not import FastAPI.
- Repositories remain the persistence boundary.
- `app/server/repositories/database/contracts.py` defines the shared database backend contract.
- `domain/` holds request, response, and domain contracts.
- Runtime job state is owned by `app/server/services/job_state.py`.
- Shared SQLAlchemy table operations are centralized in `app/server/repositories/database/orm_table_operations.py`.
- Static reference catalog loading, lookup, and seeding live under `app/server/repositories/catalog/`.

## Representative Request Flow

- endpoint (`chat.py` or `search.py`)
- composition/orchestration service
- execution and provider services
- repository or database operations

Geospatial routes typically flow:

- `geospatial.py`
- `GeospatialApiService`
- provider/runtime services
- manifest or database repositories when required

Geospatial API services are composed during application startup and accessed through `app.state.geospatial_runtime`.

## Chat Orchestration Pipeline

1. `AgentOrchestrator` receives the turn.
2. `ParserService` produces structured parse output.
3. `PolicyEngine` builds constraints and authorization checks.
4. `AgentToolCatalogService` exposes stable catalog, describe, and execute tools.
5. `NativeToolLoop` sends native tool definitions to the selected provider.
6. `ToolRegistry` validates and executes exact emitted tool names.
7. The response is persisted through chat repositories.

## Geospatial Capability Pipeline

- `manifest_loader.py` reads manifests from `app/resources/catalog`.
- `capability_registry.py` builds the catalog.
- `runtime_registry.py` applies runtime and credential availability.
- `catalog.py` and `search/orchestrator.py` consume resolved capabilities.
- `provider_registry.py` binds fetchable manifests to concrete provider adapters.

Provider metadata manifests are registered only when a backend adapter exists. Basemap tile URLs stay manifest-backed and are served through proxy paths where applicable.

## Async And Threaded Behavior

### Async

- FastAPI route handlers are predominantly `async`.
- `POST /api/chat/stream` uses streaming NDJSON.
- Search jobs can run asynchronously through `/api/maps/jobs`.

### Threaded

- Long-running map jobs currently use `InProcessJobBackend`, which wraps in-process `threading.Thread`.
- `MapSearchExecutionService.start_search_job` bridges async work inside job threads with `asyncio.run(...)`.
- Cancellation is cooperative through `stop_requested`.

## Runtime Constraints

- Job state is process-local and memory-backed.
- `app/server/services/jobs.py` defines the `JobBackend` boundary for future durable backends.
- Distributed or high-concurrency workloads would require an external queue/worker model.
- Async endpoints must avoid blocking CPU-heavy work on the event loop.

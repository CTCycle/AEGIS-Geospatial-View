# Execution And Data Flow

Last updated: 2026-06-24

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
- Runtime job state is owned by `app/server/services/jobs.py`.
- Shared SQLAlchemy table operations are centralized in `app/server/repositories/database/orm_table_operations.py`.
- Static reference catalog file loading lives under `app/server/services/catalog/loader.py`; lookup and seeding live under `app/server/repositories/catalog/`.

## Representative Request Flow

- endpoint (`chat.py` or `geospatial.py`)
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

1. `AgentOrchestrator` loads volatile conversation task and visualization state.
2. `ParserService` produces structured intent, relationship, entities, layers, visualization changes, and ambiguities.
3. `ConversationTaskStateService` creates or updates the current task record.
4. `CapabilityResolver` converts semantic layer concepts into enabled executable manifest IDs or returns a structured clarification when no temporally compatible capability exists.
5. `DeterministicAgentRouter` selects one specialist group.
6. `DeterministicToolPlanner` creates a typed, deduplicated dependency plan.
7. `PolicyEngine` restricts native tools and capability IDs to the routed scope.
8. `ToolPlanExecutor` applies timeouts, bounded transient retries, validation, and partial-failure tracking.
9. `NativeToolLoop` remains the bounded fallback when catalog discovery is required.
10. Verified results become a map session, direct answer, clarification, or diagnostic response.
11. Successful and partial outcomes are passed to the configured agent model through a validated `GroundedSynthesisResult` structured-output schema; deterministic prose remains the fallback.
12. Task status, failure details, and active visualization are updated before persistence.

Conversation task state is process-local, keyed by conversation ID or direct-chat
session ID, and expires after six hours of inactivity. It is not durable user memory.

## Geospatial Capability Pipeline

- `manifest_loader.py` reads manifests from `app/resources/catalog`.
- `capability_registry.py` builds the catalog.
- `runtime_registry.py` applies runtime and credential availability.
- `catalog.py` and `search/orchestrator.py` consume resolved capabilities.
- `provider_registry.py` binds fetchable manifests to concrete provider adapters.

Provider metadata manifests are registered only when a backend adapter exists. Basemap tile URLs stay manifest-backed and are served through proxy paths where applicable.

Live provider-native layer discovery flows through:

- `geospatial.py`
- `GeospatialApiService`
- `ProviderRegistry`
- provider adapter such as `NASAGIBSProvider`
- XML capability parsing and normalized provider layer descriptors

Renderable map overlays are produced by `RenderDescriptorService` and then placed in `MapSession.overlays`. The frontend should consume those descriptors directly rather than constructing provider-specific WMS or WMTS defaults.

## Async And Threaded Behavior

### Async

- FastAPI route handlers are predominantly `async`.
- `POST /api/chat/stream` uses streaming NDJSON.
- Chat jobs run asynchronously through `/api/chat/jobs` and are observed through `/api/jobs/{job_id}`.
- Conversation runs use `POST /api/conversations/{conversation_id}/runs` for creation and `GET /api/conversations/{conversation_id}/runs/{run_id}/events` for SSE delivery.
- User steering during an active run is aggregated into the same run through `POST /api/conversations/{conversation_id}/runs/{run_id}/steering`; it does not create a child task or queue.

### Threaded

- Long-running chat and map jobs use one in-memory `BackgroundJobService` worker and a shared job/event contract.
- Map job execution uses the current location-search orchestrator from the shared background job worker.
- Cancellation is cooperative through `stop_requested`.

## Runtime Constraints

- Job state is process-local and memory-backed.
- `app/server/services/jobs.py` defines the single in-memory `BackgroundJobService` used for chat and map jobs.
- Distributed or high-concurrency workloads would require an external queue/worker model.
- Async endpoints must avoid blocking CPU-heavy work on the event loop.
- Run event fanout is in-process in v1, with persisted event replay as the reconnect source of truth.
- Run cancellation is cooperative and terminal; stale agent results after a version change are persisted as internal diagnostics and discarded from user-visible completion.
- Agent availability is application-level. Run progress begins with `understanding_request`; creating a run does not restart the agent or emit an `agent_started` event.

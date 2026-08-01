# Execution And Data Flow

Last updated: 2026-07-30

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
- `app/server/app.py` is the sole composition root: it builds settings,
  persistence, repositories, and services, then stores the composed runtimes
  on `app.state`.
- Stateful dependencies are explicit constructor arguments. The shared
  conversation repository is passed to both chat and run-lifecycle services.
- `app/server/repositories/database/contracts.py` defines the shared database backend contract.
- `domain/` holds request, response, and domain contracts.
- Runtime job state is owned by `app/server/services/jobs.py`.
- Shared SQLAlchemy table operations are centralized in `app/server/repositories/database/orm_table_operations.py`.
- Static reference catalog file loading lives under `app/server/services/catalog/loader.py`; lookup and seeding live under `app/server/repositories/catalog/`.

Run-service errors are translated once at the API boundary by
`app/server/api/run_errors.py`. Run lifecycle and stream services translate
repository failures into `RunServiceError` subclasses; conversation endpoints
catch that service-level hierarchy and delegate status mapping to the shared
translator. Run streams always receive an `AgentRunRepository` and verify the
conversation-to-run relationship before opening the SSE response.

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

Geospatial API services are composed during application startup and accessed through `app.state.geospatial_runtime`. Routes do not construct a fallback geospatial runtime at request time.

## Chat Orchestration Pipeline

1. `AgentOrchestrator` loads volatile conversation task and visualization state.
2. `ParserService` produces structured intent, relationship, entities, layers, visualization changes, and ambiguities using the selected agent model.
3. `ConversationTaskStateService` creates or updates the current task record.
4. `CapabilityResolver` converts semantic layer concepts into enabled executable manifest IDs or returns a structured clarification when no temporally compatible capability exists.
5. `DeterministicAgentRouter` selects one specialist group.
6. `DeterministicToolPlanner` creates a typed, deduplicated dependency plan.
7. `PolicyEngine` restricts native tools and capability IDs to the routed scope.
8. `ToolPlanExecutor` applies timeouts, bounded transient retries, validation, and partial-failure tracking.
9. `NativeToolLoop` remains the bounded fallback when catalog discovery is required.
10. Verified results become a map session, direct answer, clarification, or diagnostic response.
11. Successful and partial outcomes are passed to the same selected agent model through a validated `GroundedSynthesisResult` structured-output schema; deterministic prose remains the fallback.
12. Task status, failure details, and active visualization are updated before persistence.

Direct responses (parser failures, capability questions, failure inquiries, and
preflight rejection/clarification) are handled by
`DirectTurnResponseService`. The orchestrator delegates these branches while
retaining the normal tool execution path.

`AgentOrchestrator` remains the chat-turn entrypoint, while helper services keep non-routing responsibilities isolated:

- `AgentTurnHistoryService` owns request-id idempotency, prior-message lookup, and conversation-state memory merging.
- `AgentTurnStateAssembler` owns map-session reconstruction, memory snapshot updates, and partial clarification map-state application.
- `AgentTurnSupport` owns static fallback helpers for direct rejection, general capability answers, parser-failure classification, and native-tool loop prompt assembly.

The composition root constructs `DeterministicAgentRouter`,
`DeterministicToolPlanner`, and `ToolPlanExecutor` and passes them explicitly
to `AgentOrchestrator`; the orchestrator does not construct fallback
dependencies internally.

Conversation task state is keyed by conversation ID, hydrated from the durable
conversation-context snapshot before each run, and persisted with optimistic
revision checking after each completed turn.

Run-based chat history is isolated by `conversation_id`. Each conversation owns its
context revision, active instructions, task snapshot, memory snapshot, summary state,
message sequence, and active-run relationship directly. Runs and events carry the
conversation identity explicitly, and request/mutation access is validated against
that conversation. There is no global or recently used chat session to resolve.

Every model phase receives freshly assembled conversation directives, task state,
map memory, summarized older turns, recent verbatim turns, verified tool outcomes,
and policy constraints. The current user message is supplied exactly once.

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

- Long-running chat jobs use one in-memory `BackgroundJobService` worker and a shared job/event contract.
- Cancellation is cooperative through `stop_requested`.

## Runtime Constraints

- Job state is process-local and memory-backed.
- `app/server/services/jobs.py` defines the single in-memory `BackgroundJobService` used for chat jobs.
- Distributed or high-concurrency workloads would require an external queue/worker model.
- Async endpoints must avoid blocking CPU-heavy work on the event loop.
- Run event fanout is in-process in v1, with persisted event replay as the reconnect source of truth.
- Run cancellation is cooperative and terminal; stale agent results after a version change are persisted as internal diagnostics and discarded from user-visible completion.
- Agent availability is application-level. Run progress begins with `understanding_request`; creating a run does not restart the agent or emit an `agent_started` event.
- `RunLifecycleService.create_run()` returns a transport-neutral
  `AgentRunCreateResult`; the HTTP route adds the SSE `stream_url` when it
  constructs the API response.
- Application shutdown cancels tracked lifecycle tasks and awaits them before
  the FastAPI lifespan exits, including startup-failure paths.

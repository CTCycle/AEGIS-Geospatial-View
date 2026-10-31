# Execution And Data Flow

Last updated: 2026-10-31

## Layering

AEGIS uses these backend layers:

- API routes: `app/server/api/*.py`
- Prompt declarations/builders: `app/server/prompts/*.py`
- Services and orchestration: `app/server/services/**`
- Persistence: `app/server/repositories/**`
- Application contracts: `app/server/contracts/**`
- Domain behavior and policies: `app/server/domain/**`
- Configuration models: `app/server/configurations/**`

## Layering rules

- API routes translate service exceptions into HTTP responses.
- Services do not import FastAPI.
- Repositories remain the persistence boundary.
- `app/server/app.py` is the composition root; it builds settings,
  repositories, provider runtimes, agent services, and lifecycle services.
- Stateful dependencies are explicit constructor arguments.
- Provider adapters normalize protocol responses and failures at the LLM or
  geospatial boundary; agent services consume provider-neutral contracts.
- `services/agent/` owns the native route, loop, policy, validation, evidence,
  map, and response boundaries. It does not define free-form model prompts.
- `services/llm/` owns provider invocation and protocol translation.
- `app/server/prompts/` is the sole source of free-form model instructions.
- Conversation run state, checkpoints, and events are owned by the run and
  conversation repositories.

The composition boundary is intentionally explicit:

```mermaid
flowchart LR
    API[API routes] --> SERVICES[Native agent and geospatial services]
    SERVICES --> CONTRACTS[contracts/ and domain/]
    SERVICES --> REPOS[Repositories]
    REPOS --> DB[(SQLiteRepository)]
    START[app_lifespan] --> INIT[database initializer]
    INIT --> SEED[manifest and catalog startup]
    SEED --> REPOS
```

Run-service errors are classified at the realtime protocol boundary. The
realtime service verifies the conversation-to-run relationship before starting,
steering, cancelling, or acknowledging a run.

## Representative request flow

Chat requests flow through:

1. `chat.py` validates the request and conversation identity.
2. `ChatRuntime` supplies the composed native orchestrator and repositories.
3. `NativeAgentOrchestrator` hydrates `ConversationState`, history, directives,
   map memory, and relevant evidence summaries. History is read once per turn
   as a text-only projection (id, turn index, request id, role, content); the
   turn index comes from a count query, and structured, tool and map payloads
   are not loaded.
4. `AgentContextAssembler` builds one bounded `AgentContextPackage`.
5. `AgentStateFactory` creates the canonical checkpointable `AgentRunState`.
6. `AgentLoop` routes, compiles the goal, exposes tools, calls the model,
   executes typed actions, projects observations, and evaluates completion.
7. `NativeAgentOrchestrator` writes the next canonical conversation state and
   assistant history with optimistic revision control.
8. `AgentRunOrchestrator` completes a data-only run or hands a map candidate
   to `RenderCompletionService` for browser acknowledgment. A render
   acknowledgment is a continuation event, not an implicit terminal result.

The geospatial runtime is composed once at startup and accessed through
`app.state.geospatial_runtime`. Routes do not construct a fallback runtime at
request time.

## Native agent loop

Each new run snapshots the saved `agent_execution` policy. Checkpoint resumes
restore that policy before context assembly and execution. Request-scoped model,
tool, and provider policies avoid mutating the shared runtime. Google native
continuation preserves ordered SDK parts and signatures in private checkpoints;
transport projections omit those fields. Completion separately checks execution,
validity, relevance, and requested spatial/temporal coverage. Preparing a map or
loading a raster source cannot substitute for those checks. Unknown raster
visibility remains unsatisfied and enters the existing bounded render recovery.

See the [2026-09-30 implementation report](../../QA/native-reliability-report-20260930.md)
for validation and remaining live-render/benchmark limitations.

There is one application execution path. It has no legacy/shadow/native mode
switch:

```text
conversation state
      ↓ hydrate
route_request
      ↓ deterministic route validation and capability narrowing
goal/completion contract
      ↓
build bounded context view
      ↓
model decision
      ↓
typed tool call → schema/semantic/policy validation → ToolExecutor
      ↓
ToolResult → bounded ModelObservation → canonical state update
      ↓
completion evaluation
      ├─ continue with a new model view
      ├─ ask for clarification
      ├─ await browser render acknowledgement
      │       ↓
      │   RenderObservation → same checkpoint → correction/retry or finalization
      └─ finalize a grounded response
```

`AgentRunState` owns route, goal, requirements, locations, evidence refs,
observations, provider continuation, counters, traces, and terminal reason.
`AgentContextView` is rebuilt before each model decision. Raw datasets are
stored in `agent_evidence` and are never copied into the model context.

The native bootstrap route distinguishes:

- accepted route with a deterministic shortlist;
- discovery-required route when no confident shortlist exists;
- clarification for missing/ambiguous user information; and
- no-capability after explicit or bounded discovery has been exhausted.

The model selects semantic actions. AEGIS binds validated location references,
coordinates, bbox/radius, temporal boundaries, provider argument names, and
task-owned filters at the execution boundary.

## Canonical state and context

`ConversationState` is the revisioned durable state for a conversation. It
contains active directives, summary, goal/route/constraints, resolved
locations, evidence references, committed map session, and unresolved
questions.

`AgentRunState` is the mutable state for one run and is JSON-checkpointable.
`AgentContextView` is ephemeral. `AgentEvidence` is durable external data, and
`AgentTrace` is append-only operational metadata.

`AgentContextAssembler` owns semantic reduction. It preserves mandatory goal,
directive, map, task, and policy fields; ranks evidence by current goal,
scope, explicit references, and recency; skips oversized messages while
continuing to inspect later smaller items; and serializes only valid bounded
objects. Provider context preparation may enforce a final protocol limit but
does not choose semantic history.

Every model request records estimated and provider-reported usage, tool-schema
tokens, output reserve, usable limit, compaction, and cumulative run usage.
Provider continuation items are kept separately from semantic context and are
bounded to the most recent protocol window.

## Tool and manifest boundaries

`ToolRegistry` is the only registry and exposes the small permanent tool set:

- `resolve_geospatial_location`
- `discover_geospatial_capabilities`
- `describe_geospatial_capability`
- `execute_geospatial_capability`
- `inspect_evidence`
- `transform_evidence`
- `measure_geospatial`
- `apply_map_plan`

`search_conversation_history` is registered when a history repository is available.
Provider-layer discovery stays behind the generic capability-discovery tool.
Multi-target completion retains each execution's location binding through compact
checkpoints, including the browser render/resume boundary. A single bounded
terminal synthesis call may use one reserved model slot when the ordinary call
budget is exhausted; the run deadline and cancellation still apply.

`route_request` is an internal bootstrap definition. `ToolExecutor` is the
only execution boundary; it validates input, applies policy, counts attempts,
records timeout/trace metadata, invokes the handler, and normalizes one
`ToolResult`.

`manifest_loader.py` reads schema-v2 entries from `data/catalog`.
Agent-facing entries must declare `agenticUse.domains` and an explicit
`executionContract`. `CapabilityRegistry` applies runtime availability,
coverage, temporal, scope, operation, render, and relevance filters without
inferring a second contract from free text or capability kind.

Provider-layer discovery and capability descriptions are canonical native
handlers. Both return bounded descriptors, deterministic pagination, and
evidence references where external metadata is persisted.

## Evidence, observations, and responses

`ToolResult` is the canonical application result. `ModelObservation` is its
model-facing projection. It preserves bounded tool-specific result data,
provider identity, freshness, observation time, resolution, units, coverage,
warnings, pagination, evidence refs, truncation, and recovery. Valid-empty is
distinct from failure and can drive a wider query, alternate source, or a
grounded zero-result answer.

`ChatTurnResponse` is the public native response. It contains the assistant
message, operation, route, goal, completion contract, tool summaries, trace,
context usage, conversation state, and optional map candidate. Parser/planner
projection fields are not part of the contract.

Settings readiness reads the selected model's tool-support capability from the
provider catalog. It does not send a test inference; missing metadata remains
unverified. Actual route behavior is observed during the user's normal run.

## Map completion flow

`apply_map_plan` creates a typed candidate and suspends the run only while the
browser verifies it. For realtime runs:

1. the candidate is persisted as `awaiting_render`;
2. `map_prepared` publishes the exact run version, session ID, collection
   revision, and required render checks;
3. the browser validates the candidate in MapLibre and sends `map.render_ack`
   with bounded check and failure metadata;
4. `RenderCompletionService` verifies ownership, identities, revision, and
   completion requirements, then normalizes the outcome into a bounded
   `RenderObservation`;
5. the observation is persisted and reinjected into the same checkpoint. A
   failed render discards the candidate, preserves the last-known-good map,
   and resumes the model for a revised action; a ready render atomically
   promotes the candidate and resumes the run for a tools-disabled final
   answer (or for any remaining completion requirement); and
6. after three bounded render attempts, one finalization-only model call
   explains the failure and the run terminates as
   `render_recovery_exhausted`.

The last committed map remains active while a candidate is pending. Failed,
stale, conflicting, or superseded acknowledgments cannot replace it. Duplicate
identical acknowledgments are idempotent; stale or mismatched acknowledgments
remain protocol errors. A failed candidate/action fingerprint is not treated
as a reusable success, and exact failed repetition is rejected as non-progress.
Metadata-only products finalize as data responses without an impossible render
wait.

Location resolution is hierarchical and explicit. Ambiguous candidates produce
a clarification transition. Invalid location references produce semantic
validation; another available location is never silently substituted.

## Provider and timeout flow

The native run has one absolute deadline and bounded model, tool, transition,
retry, and stage limits. The timeout hierarchy is:

```text
run deadline
  > model decision
  > tool execution
  > provider operation
  > HTTP connection/read/write
```

Each child operation is capped by its parent. `ProviderRegistry` owns bounded
transport retries, rate limiting, provider deadlines, and circuit breaking.
After those retries are exhausted, the normalized failure returns to the
native loop for semantic recovery.

Terminal reasons remain distinct: `model_budget_exhausted`,
`tool_budget_exhausted`, `transition_budget_exhausted`,
`run_deadline_exhausted`, `no_progress`, `context_limit`, `provider_failure`,
`cancelled`, `superseded`, and `render_recovery_exhausted`.

## Async and threaded behavior

### Async

- FastAPI handlers are predominantly async.
- `POST /api/chat/turn` starts or executes a conversation run. Accepted runs
  are observed through `GET /api/conversations/{conversation_id}/runs/{run_id}`.
- The `/api/conversations/{conversation_id}/realtime` WebSocket supports
  session resume, run commands, steering,
  render acknowledgments, heartbeats, and ordered durable events.
- Render continuation publishes bounded `run_suspended`, `render_observed`,
  `run_resumed`, `completion_decision`, and (when needed)
  `render_retry_exhausted` trace events. These events expose operational state
  and sanitized outcomes without private model reasoning.
- Cancellation and version checks occur before/after external work and before
  durable commits. Per-trace, per-checkpoint and run-state checks use
  `AgentRunRepository.get_run_control()`, a single-row read of version, state
  and cancellation that never scans the event log; full snapshots remain for
  API responses and checkpoint restoration. Tracked lifecycle tasks are directly cancelled on request.

### Threaded

- Native run lifecycle tasks are tracked by the application and their status,
  checkpoints, and ordered event history are persisted in SQLite. Realtime
  event replay is the reconnect source of truth.
- Distributed workers, shared fanout, and external metrics are not part of the
  current local Windows runtime.

## Runtime constraints

- Active work executes in the current backend process; durable run state and
  event history survive process restarts in SQLite.
- The Windows launcher/manual-start workflow is the supported local deployment.
- Async endpoints must avoid blocking CPU-heavy work on the event loop.
- Each native run persists bounded iteration checkpoints in the internal run
  event log and reloads the latest checkpoint when an active run is resumed.

## Regional discovery within the native harness

The route carries required `location_mode` and optional structured analysis.
Static macro-region aliases bind to the same bbox-bearing `ResolvedLocation`
used by ordinary targets. `MapSession`, location references, execution extents,
and coverage policy retain their existing contracts. Search-area availability
requires the explicit requested area, rather than a prior map or unrelated ref.

The server binds `sampling=area` and recent day/week/month windows. Provider
parameters include sampling only for manifests declaring `grid_sample`; other
sources report `coverage.area_sampling=single_point_center`. A route with
several `capability_queries` compiles them (at most four) into
`CompletionContract.data_obligations`. Each execution records the queries its
manifest covers (`metadata.covered_queries`); an obligation is met by validated,
eligible evidence from any covering source, so one source may satisfy several
and the model still picks sources and order. The registry keeps `execute`
exposed while an obligation is uncovered. Analysis retrieval needs at least one
valid numeric (non-raster) execution; raster descriptors and transforms do not
count as retrieval.
Derived evidence stores `features`, spatial bounds, numeric value fields, and
parent provenance. Completion requires located derived records or valid-empty
analysis before map preparation. Graduated/heatmap encodings include validated
numeric min/max; the browser renders unclustered value-driven layers.

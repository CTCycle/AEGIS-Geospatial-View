# Native AEGIS harness status and completion plan

Last updated: 2026-09-15

## Purpose

This document is the implementation record for the native-agent consolidation
described in the original architecture audit. The target is deliberately
small and in-process:

```text
conversation state
        │ hydrate
        ▼
canonical AgentRunState
        │ route and compile goal
        ▼
bounded AgentLoop
        │ model → typed action → observation → state update
        ▼
conversation state + evidence + trace
```

AEGIS does not need LangGraph, the OpenAI Agents SDK, or another external
agent runtime. The geospatial catalog, provider registry, evidence store, map
handshake, and run lifecycle remain application-owned invariants.

## Baseline and current status

- Audit baseline: `c6809755e1ea2dafdc09e45f0f4c574d5327f04f`.
- Work is being resumed on `develop`; the current consolidation changes are
  intentionally kept in the working tree until the final validation gate.
- `app/assets/` is pre-existing untracked work and is out of scope. Never
  stage, delete, or reset it.
- Native execution is now the only application execution path. There is no
  runtime mode switch for legacy or shadow execution.
- The `native_v2_*` filenames are historical names for the native tool and
  turn adapters; they do not represent a second runtime or compatibility
  branch.

## Covered implementation slices

### Native semantics and feedback

- `AgentLoop` performs the complete iterative cycle: route, expose, model,
  validate, execute, normalize, update state, evaluate, and continue.
- `AgentRunState` is the checkpointable native state. It carries the request,
  route, compiled `AgentGoal`, `CompletionContract`, directives, task/map
  context, resolved locations, evidence references, observations, traces,
  counters, and terminal reason.
- `AgentContextAssembler` hydrates the full bounded conversation package into
  the run state. `AgentContextView` is rebuilt before each model decision and
  is never the durable source of truth.
- `ModelObservation` is the deliberate projection of `ToolResult`; discovery
  descriptors, evidence samples/statistics, provider metadata, warnings,
  coverage, freshness, pagination, errors, recovery, and valid-empty results
  survive in bounded form. Raw provider payloads remain in `agent_evidence`.
- Recovery values are actionable: correction returns an observation to the
  model, alternate-source and replan recovery reopen the eligible tool set,
  transport retry remains provider-owned, and clarification becomes an
  explicit user-input outcome.
- Route validation distinguishes accepted, clarification, no-capability, and
  discovery-required outcomes. An empty deterministic shortlist can therefore
  enter `discover_geospatial_capabilities` before insufficiency is reported.
- The route is compiled into deterministic location, temporal, spatial,
  evidence, operation, and map obligations. The model chooses semantic
  actions; server-owned binding supplies geography, time, radius, bbox, and
  task invariants.
- Requested location references resolve exactly. An unavailable reference or
  ambiguous location cannot silently fall back to another geography.

### One state and persistence model

- `ConversationState` is the revisioned durable conversation state: directives,
  summary, goal/route/constraints, resolved locations, evidence references,
  committed map, and unresolved questions.
- `AgentRunState` is the mutable/checkpointable state for one run.
- `AgentContextView` is ephemeral model input. `AgentEvidence` is durable raw
  and normalized external data. `AgentTrace` is append-only operational data.
- Conversation persistence uses one canonical `conversation_state` JSON field;
  the old task, memory, instruction, and summary columns are backfilled by
  migration and then removed from the active schema.
- The native orchestrator hydrates, executes, and writes that state with an
  optimistic revision. Assistant history is persisted inside the same bounded
  persistence stage as the conversation-state write.

### One tool and catalog model

The application registry exposes one typed boundary:

```text
route_request                         internal bootstrap
resolve_geospatial_location           model-facing
discover_geospatial_capabilities     model-facing
discover_geospatial_provider_layers   model-facing
describe_geospatial_capability       model-facing
execute_geospatial_capability        model-facing
inspect_evidence                      model-facing
transform_evidence                    model-facing
apply_map_plan                        model-facing
```

`ToolRegistry.register`, `expose`, and `get` are the only registry APIs.
`ToolExecutor` is the only execution boundary and owns schema validation,
semantic validation, policy, tool-call accounting, timeout measurement, trace
metadata, and result normalization.

Manifest routing is schema-v2 authoritative. Agent-facing manifests declare
`agenticUse.domains` and an explicit `executionContract`; routing no longer
infers behavior from capability kind or free text. Runtime-enabled catalog
entries were given explicit contracts for supported operations, scopes,
temporal modes, rendering, and fallback/coverage metadata.

Provider-layer discovery and capability description now sit behind the native
catalog handlers. Discovery and provider-layer pages have deterministic
cursors, bounded descriptors, and evidence persistence.

### One observation, context, and budget policy

- Semantic context reduction belongs to `AgentContextAssembler`. Provider
  context preparation remains a final protocol safety boundary.
- History and evidence are selected by bounded fields and relevance; an
  oversized item does not prevent later smaller relevant items from fitting.
  Structured working state is compacted as valid objects, never by slicing a
  serialized JSON string.
- Each model invocation records estimated/reported usage, tool-schema cost,
  output reserve, usable limit, compaction, and cumulative trace data.
- `AgentExecutionBudget` owns the run deadline, model/tool/transition limits,
  retries, profile promotion, stage observations, and distinct terminal
  reasons. Model calls use the model stage limit; tool calls use the tool
  stage limit; map preparation uses the map stage limit.
- Provider request settings are injected into one `ProviderExecutionPolicy`.
  Source-specific timeouts are never cut short by an unrelated lower global
  default, and provider retries remain below the agent semantic-recovery
  layer.
- Run cancellation and version supersession are checked before and after
  model/tool work and before durable commits. Lifecycle cancellation directly
  cancels the tracked in-flight task.
- OpenAI/Responses protocol continuation items remain opaque to the semantic
  state and are retained only in a bounded provider continuation window.

### Public result and map contracts

`ChatTurnResponse` and `AgentTurnResponse` are native contracts containing the
assistant message, operation, route, goal, completion contract, tool-result
summaries, context usage, trace, conversation state, and optional map
candidate. Removed parser/planner/task/migration projections are not accepted
by the response models or client parsers.

Map preparation is a candidate operation. Realtime runs persist the candidate
as `awaiting_render`, retain the last committed map, and promote only after a
matching browser `map.render_ack`. Metadata-only results finalize as data
responses without an impossible render wait. Failed or stale acknowledgments
cannot replace the last-known-good map.

## Original plan coverage

| Plan area | Current status | Evidence or boundary |
| --- | --- | --- |
| P0 observations and recovery | Covered | `ModelObservation`, recovery policy, discovery/alternate-source trajectories |
| P0 native context hydration | Covered | canonical assembler, state factory, conversation migration |
| P0 goal/completion contract | Covered | route compiler, deterministic pending requirements, map requirements |
| P0 exact location binding | Covered | semantic validator and location-reference tests |
| P1 state/context consolidation | Covered | `ConversationState`, `AgentRunState`, `AgentContextView`, structured compaction |
| P1 budgets/timeouts/cancellation | Covered | shared settings, provider policy injection, stage telemetry, run controls |
| P1 provider continuation | Covered in harness | bounded opaque continuation; provider-specific live proof remains a gate |
| P2 tool registry and manifest contracts | Covered | one registry/executor and strict runtime catalog validation |
| P2 live provider discovery transfer | Covered locally | canonical provider-layer handler; live upstream coverage remains environment-dependent |
| P3 legacy/shadow runtime deletion | Covered | old execution files, parser/planner chain, shadow path, mode switch, and migration response fields deleted |
| P4 trajectory/evaluation suite | Covered locally | core native trajectories and focused contracts pass, including discovery, replan, valid-empty, malformed-call correction, 10-turn bounded context, in-flight cancellation, durable checkpoint retrieval/resume, duplicate suppression, and MapLibre acknowledgement; live/provider coverage remains an external validation gate |

## Remaining validation gates

The implementation is not declared production-complete solely from local
synthetic success. The following evidence is now recorded:

- Full server unit suite: `730 passed, 2 warnings` with the checkpoint/resume
  tests included.
- Ruff: passed with no findings. The managed workspace still reports
  access-denied cache warnings while scanning protected cache residue.
- Client build: passed.
- Client tests: `217 SUCCESS`.
- E2E collection: `51 tests collected`.
- Controlled browser-driven MapLibre render acknowledgement: `1 passed`.
- Durable native checkpoint callback/retrieval and active-run startup-resume
  tests pass; checkpoints are stored as bounded internal run events.

The remaining external validation gates are explicitly blocked for this local
run. No live backend/provider credential session was available, and the
available environment variables do not establish a callable provider/model.
The gates are:

1. Provider-specific tool serialization and continuation proof for OpenAI
   Responses, Ollama, and OpenCode Go using the configured provider/model.
2. Full browser/API E2E execution against a running backend, including
   external-provider credentials where required. The controlled MapLibre
   contract is proven locally, but it is not a substitute for that live gate.

The local trajectory suite now covers the core synthetic cases, including
valid-empty recovery, malformed-call correction, cancellation during model and
tool work, duplicate replay, bounded multi-iteration context, and checkpoint
restoration from the durable run event log. The broader external-provider and
full application matrix remains separate evidence.

Historical QA reports may still mention the removed parser and old tool names;
they are retained as historical evidence and are not runtime documentation.

## Final completion gate

The native consolidation is complete only when the remaining validation gates
are either executed with evidence or explicitly recorded as environment-
blocked, and reference searches confirm that no runtime configuration/import
path can select legacy or shadow execution. The final architecture must remain
one model-directed loop, one canonical state model, one registry, one context
and observation policy, one timeout/budget policy, and one public response
contract.

# Native AEGIS harness status and completion plan

Last updated: 2026-09-17

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
- Repository baseline before this remediation series: `4d55d16c` on `develop`.
- Remediation is staged in the shared local worktree on `develop`; no push or
  pull request is part of this task.
- `app/assets/` is pre-existing untracked work and is out of scope. Never
  stage, delete, or reset it.
- Native execution is now the only application execution path. There is no
  runtime mode switch for legacy or shadow execution.
- The native tool and turn adapters use the canonical `native_tools.py` and
  `turn_runner.py` filenames. No `native_v2_*` compatibility runtime remains.

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
- Undated `recent`, `latest`, `live`, and near-real-time intent is normalized to
  the `current` temporal mode; explicitly dated historical requests remain
  historical.
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

### Render continuation and completion

- `apply_map_plan` persists a realtime candidate as `awaiting_render` and
  emits `map_prepared`; preparation is a suspension point, not completion.
- `map.render_ack` is normalized by `RenderCompletionService` into a bounded
  `RenderObservation` carrying candidate identity, collection revision,
  attempt, viewport/check outcomes, overlay results, failure metadata, and a
  recovery class.
- The observation is persisted and reinjected into the same checkpoint. Ready
  acknowledgments atomically commit the candidate and trigger a tools-disabled
  finalization call (or continue for remaining requirements). Failed
  acknowledgments preserve the last-known-good map, discard the candidate, and
  resume the model for correction.
- Three render attempts are allowed by default. Failed action fingerprints are
  invalidated and exact failed repetition is rejected as non-progress.
  Exhaustion produces one finalization-only response and the terminal reason
  `render_recovery_exhausted`.
- Render continuation is observable through `run_suspended`,
  `render_observed`, `run_resumed`, `completion_decision`, and
  `render_retry_exhausted` events/traces.

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
- Every run has a typed root task and current iteration. Compound routes add
  requirement/target children, and task status is derived from observations and
  completion checks rather than model prose.
- Tool selection and normalized results emit linked internal trace events with
  run version, iteration, task ID, call ID, safe arguments/results, timing,
  recovery, and evidence references. The trace reader redacts credentials and
  reasoning fields; raw provider payloads remain in `agent_evidence`.

### Public result and map contracts

`ChatTurnResponse` and `AgentTurnResponse` are native contracts containing the
assistant message, operation, route, goal, completion contract, tool-result
summaries, context usage, trace, conversation state, and optional map
candidate. Removed parser/planner/task/migration projections are not accepted
by the response models or client parsers.

HTTP turns, NDJSON streams, background jobs, and realtime runs all create or
observe the same persisted `AgentRun` lifecycle. Conversation listing/search,
recent-run summaries, and the access-checked redacted run-trace endpoint reuse
the existing conversation, run-event, and evidence tables.

Map preparation is a candidate operation. Realtime runs persist the candidate
as `awaiting_render`, retain the last committed map, and resume the same native
run after a matching browser `map.render_ack`. A successful render observation
promotes the candidate before finalization and stores the committed candidate
on the durable assistant message, so reloads cannot regress to transient
“awaiting render” text. Failed acknowledgments preserve the last-known-good
map and return a structured observation to the model. Metadata-only results
finalize as data responses without an impossible render wait. Failed, stale,
conflicting, or superseded acknowledgments cannot replace the last-known-good
map.

## Original plan coverage

| Plan area | Current status | Evidence or boundary |
| --- | --- | --- |
| P0 observations and recovery | Covered | `ModelObservation`, recovery policy, discovery/alternate-source trajectories |
| P0 native context hydration | Covered | canonical assembler, state factory, conversation migration |
| P0 goal/completion contract | Covered | route compiler, deterministic pending requirements, map requirements |
| P0 exact location binding | Covered | semantic validator and location-reference tests |
| P1 state/context consolidation | Covered | `ConversationState`, `AgentRunState`, `AgentContextView`, structured compaction |
| P1 budgets/timeouts/cancellation | Covered | shared settings, provider policy injection, stage telemetry, run controls |
| P1 provider continuation | Covered in harness; OpenCode Go exercised | bounded opaque continuation; OpenAI Responses and Ollama remain unrun |
| P2 tool registry and manifest contracts | Covered | one registry/executor and strict runtime catalog validation |
| P2 durable traces and bounded task state | Covered | typed task ledger, iteration exhaustion category, paired context, redacted run trace |
| P2 conversation history and run inspection | Covered | conversation page/search, scoped history tool, recent runs, trace endpoint |
| P2 transport lifecycle consolidation | Covered | HTTP/NDJSON/jobs use `RunLifecycleService`; realtime already used it |
| P2 live provider discovery transfer | Covered locally | canonical provider-layer handler; live upstream coverage remains environment-dependent |
| P3 legacy/shadow runtime deletion | Covered | old execution files, parser/planner chain, shadow path, mode switch, and migration response fields deleted |
| P4 trajectory/evaluation suite | Covered locally | core native trajectories and focused contracts pass, including discovery, replan, valid-empty, malformed-call correction, 10-turn bounded context, in-flight cancellation, durable checkpoint retrieval/resume, duplicate suppression, and MapLibre acknowledgement; live/provider coverage remains an external validation gate |

## Remaining validation gates

The implementation is not declared production-complete solely from local
synthetic success. Current evidence is recorded in
`assets/QA/native-agent-loop-remediation-20260917/final-report.md`:

- Server unit suites: `798 passed, 2 warnings`.
- Focused native/render suites: `43 passed`; the render-completion subset is
  `12 passed` and includes same-run resume, last-known-good preservation, and
  backend-check rejection normalization.
- Targeted Pyright over changed backend modules: `0 errors, 0 warnings,
  0 informations`. Full strict Pyright remains blocked by pre-existing
  provider Optional-access, maintenance-service, transport, and AgentLoop
  complexity diagnostics.
- Ruff passed; the managed workspace still reports access-denied warnings for
  protected cache residue.
- Angular production build passed. The targeted Karma process was unavailable
  after the restart and is recorded as blocked rather than inferred from build
  success.
- A full repository test attempt during integration (before the final focused
  contract fixes) was not a clean gate (`699 passed, 147 failed, 4 skipped,
  75 warnings`); the failures include unavailable backend services/browser E2E
  and provider/integration suites outside the focused orchestration proof.
- Browser-driven MapLibre and live-provider validation were not rerun in this
  continuation because the required services/credentials were unavailable; no
  provider or browser success is claimed here.

The remaining validation gates are explicitly separated from the local proof.
The configured OpenCode Go credential was live for the run above; other lanes
and hosted infrastructure were not silently substituted. The gates are:

1. Provider-specific serialization and continuation proof for OpenAI Responses
   and Ollama. OpenCode Go has a live structured probe and the browser run
   above, but this does not establish parity for the other providers.
2. Hosted CI was not rerun after the local commits. The last exact-HEAD CI run
   (`34967001626`) failed its stale Pyright job before this remediation.
3. The full browser/API E2E matrix was not executed locally because its backend
   services on ports `8000` and `8001` were unavailable. The controlled
   MapLibre contract is proven locally, but it is not a substitute for that
   broader gate.

The local trajectory suite covers the core synthetic cases, including
valid-empty recovery, malformed-call correction, render acknowledgement
continuation, cancellation during model and tool work, duplicate replay,
bounded multi-iteration context, and checkpoint restoration from the durable
run event log. The broader external-provider and full application matrix
remains separate evidence.

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

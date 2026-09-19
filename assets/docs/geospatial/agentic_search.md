# Native Geospatial Agent Harness

Last updated: 2026-09-19

## Summary

AEGIS uses one native, bounded agent harness for geospatial chat. A run is
hydrated from revisioned `ConversationState` into a canonical `AgentRunState`,
compiled into a typed route and completion contract, and then advanced by the
iterative native loop:

```text
route -> expose -> model decision -> typed tool call -> observation
      -> state update -> completion evaluation -> continue, render, or finish
```

The model chooses semantic actions. AEGIS owns validation, geographic and
temporal binding, tool eligibility, budgets, retries, evidence persistence,
map commit, and terminal-state rules. There is no runtime legacy/native mode
switch and no shadow execution path.

The exact implementation status and remaining environment-gated validation are
tracked in `assets/docs/geospatial/native_harness_bootstrap.md`.

## Prompt and state boundaries

`app/server/prompts/` is the sole source of free-form model instructions.
`prompts/agent.py` builds the native system prompt, route instructions, and
bounded state view. Typed route, goal, completion, tool, and observation
contracts live under `domain/agent/` and `contracts/`; services own policy and
execution rather than embedding prompt text.

`AgentContextAssembler` is the semantic context owner. It hydrates the full
conversation package, applies relevance and structured per-field bounds, and
produces an ephemeral `AgentContextView` before each model call. Provider
adapters may perform a final protocol-safety check, but they do not independently
decide which semantic history to discard.

Durable state is separated from the model view:

- `ConversationState` owns revisioned conversation directives, summary, goal,
  committed map state, durable evidence references, and unresolved questions.
- `AgentRunState` owns one run's route, completion obligations, resolved
  locations, candidate capabilities, observations, counters, deadlines, and
  terminal state.
- `AgentContextView` is rebuilt for one model decision and is not canonical
  state.
- `agent_evidence` stores raw or normalized external data outside the prompt.
- trace events record model calls, tool calls, observations, retries, context
  compaction, transitions, and stop evaluations.

Render acknowledgments use the same state boundary as tool results. The
browser's bounded checks are normalized into `RenderObservation`, appended to
`AgentRunState`, and fed back to the model. A failed candidate therefore
supports `render -> observation -> revised map plan -> render` in one user
turn; a ready candidate is committed before the final answer is generated.

## Route, goal, and completion

`route_request` is the internal bootstrap boundary. It produces a typed
`CapabilityRoute`; the native goal compiler derives an `AgentGoal` and
`CompletionContract` from the request, route, verified locations, explicit
scope/time requirements, requested operation, and presentation requirement.
The model may choose among eligible capabilities, but it cannot remove
application-owned completion obligations.

Location resolution is hierarchical and deterministic where evidence permits:
coordinates take precedence, followed by address/POI/street, district or
neighborhood, city or municipality, region/state, and country. A requested
location reference must resolve exactly. Ambiguous candidates become an
explicit clarification transition; an unavailable reference is a typed
validation/replan outcome and never silently falls back to another geography.

Plain map-oriented place wording has a bounded server-owned route rescue when
the model's route bootstrap misses the request. The rescue is limited to
non-data display/navigation language and still enters the normal location
resolver, so it cannot select a place or suppress a required clarification.

The completion contract can require location resolution, data retrieval,
spatial and temporal filtering, renderable geometry, map-state commit, viewport
evidence, and final response readiness. A valid empty result remains data with
an explicit no-results outcome, not a provider failure.

Provider-data is an explicit obligation, not a synonym for every execute route.
Named-place display and basemap requests can therefore resolve a location and
prepare a map candidate without inventing a POI/data dependency. Requests that
actually ask for provider data compile `data_requirement=provider_data` and are
not complete until an intended, bounded capability returns `success`,
`valid_empty`, or an explicitly supported `partial` result.

Semantic scopes such as an administrative area are retained for intent and
provenance, but are lowered once into the concrete `ExecutionExtent` required
by the selected capability. Provider adapters receive only that concrete
point, bbox, radius, or viewport; they never receive the raw semantic scope
label. Location resolution automatically refreshes the capability shortlist so
the model does not spend a second planning turn rediscovering candidates that
were unavailable before geography was known.

## Capability catalogue and tools

Manifest v2 metadata is authoritative. Agent-facing entries must declare an
explicit execution contract and routing metadata; capability kind or free-text
heuristics are not used to infer agent domains.

Deterministic routing narrows candidates by runtime eligibility, geographic
coverage, temporal compatibility, required inputs, supported operation,
rendering support, known limitations, and semantic relevance. If no confident
candidate is available but the request may be supported, the route enters
`discovery_required` and exposes discovery rather than stopping prematurely.

The native runtime has one fixed typed registry, but the model-visible surface
is progressive rather than fixed. `route_request` is the internal bootstrap
tool. The model-visible action names are:

- `resolve_geospatial_location`
- `discover_geospatial_capabilities`
- `describe_geospatial_capability`
- `execute_geospatial_capability`
- `inspect_evidence`
- `transform_evidence`
- `apply_map_plan`
- `search_conversation_history` (conditional history-repository registration)

`transform_evidence` is the runtime name. `discover_geospatial_capabilities`
is the single model-facing capability-discovery boundary. Provider-layer
discovery remains a server-owned internal handler used to enrich that generic
result; it is not a second model-facing catalog choice.

The registry has one `RegisteredTool` contract and one `ToolExecutor` boundary.
The executor validates policy and arguments, binds server-owned geography/time
parameters, checks and accounts for budgets, applies the resolved timeout,
records a trace span, invokes the handler, and normalizes the result.

### Responsibility-driven exposure

At every model decision, `ToolRegistry.expose(state)` should project only the
tools needed by the currently unmet route and completion responsibilities.
Registration alone does not make a tool available:

```text
route bootstrap
  -> route_request (internal only)

plain answer, clarification, or finalization
  -> no model-facing tools

location required and unresolved
  -> resolve_geospatial_location

shortlist missing after required locations are resolved
  -> discover_geospatial_capabilities

shortlist selected
  -> describe_geospatial_capability (only when detail is needed)
  -> execute_geospatial_capability (when data is required)

evidence analysis or transformation required
  -> inspect_evidence, transform_evidence

map presentation pending
  -> apply_map_plan

history recall explicitly required
  -> search_conversation_history
```

This is a state projection, not a mandatory linear workflow. After each typed
tool result, the loop updates the run state, reevaluates the completion
contract, and rebuilds the eligible set. Location-dependent discovery is not
offered alongside unresolved location resolution, and stored evidence or
history does not by itself justify exposing the corresponding tools.

After each tool batch the loop evaluates the completion contract before asking
the model to plan again. When all non-presentation obligations are satisfied,
one finalization-only model turn is reserved and the run terminates; successful
provider work is not replayed until the action budget is exhausted.

The model selects a capability, operation, evidence references, and allowed
user-semantic filters. AEGIS binds resolved coordinates, canonical bbox/radius,
temporal boundaries, task-owned filters, and provider argument names.

Discovery responses implement bounded deterministic pagination. Provider-layer
descriptors, where required by the catalog contract, remain bounded normalized
observations behind the generic discovery responsibility. They are never
unrestricted provider browsing, and the model is not offered two
interchangeable discovery choices for the same unmet responsibility.

## Observations and evidence

`ToolResult` is the canonical application result. Before the next model call,
`ModelObservation` projects it into a bounded, tool-specific view containing
status, summary, result metadata, evidence references, provenance, warnings,
coverage, pagination, errors, recovery semantics, truncation, and continuation
information.

Discovery descriptors, evidence samples, statistics, schema, provider freshness,
units, spatial resolution, coverage, partial state, and stale state remain
available when relevant. Large feature collections and raw provider payloads
remain in the evidence store and are never inserted wholesale into model
context.

`RenderObservation` is the corresponding bounded projection for the browser
render phase. It identifies the candidate/session and collection revision,
attempt number, ready/failed status, verified viewport, required checks,
overlay outcomes, safe failure code/stage/summary, and deterministic recovery
class. It is operational evidence rather than chain-of-thought and is retained
alongside tool observations in the checkpoint.

Recovery is semantic rather than a blind repeat:

- transport retry is owned by the provider registry;
- `correct_arguments` returns an actionable observation;
- `choose_alternate_tool` exposes alternatives;
- `replan` re-evaluates route and candidates;
- `request_user_input` enters clarification;
- `terminal` ends the run.

Equivalent successful calls are replay-protected, and repeated failing
fingerprints are suppressed. Tool timeouts normally become observations so an
alternate source can be selected; only the run deadline necessarily terminates
the whole run.

## Provider and budget boundary

One settings block feeds the native execution budget and provider execution
policy. The timeout hierarchy is:

```text
run deadline > model step > tool execution > provider operation
             > HTTP connect/read/write
```

Child operations are clamped to the remaining parent deadline, while a valid
source-specific timeout is not accidentally shortened by a smaller global
default. Model, tool, transition, wall-clock, context, retry, and persistence
usage are recorded in the canonical trace with distinct terminal reasons.

Provider adapters own protocol continuation details. The harness retains a
bounded portable message history plus opaque provider continuation metadata so
stateless reasoning/tool protocols can continue without putting provider
wire-format objects into durable agent state.

Cancellation and steering are checked at safe boundaries before and after
model/tool work, evidence mutation, map preparation, and final persistence.
Changed run versions stop stale work with `superseded`; cancellation produces a
terminal cancelled run without committing stale state.

## Map and response contract

`apply_map_plan` creates a typed candidate only. A direct synchronous response
can report `prepared_unverified`; the realtime browser path requires a matching
`map.render_ack` containing the run version, map session, collection revision,
and bounded rendering checks. The acknowledgment becomes a render observation
and resumes the same bounded run: only a verified ready observation promotes
the candidate to the committed map, while a failed observation leaves the
last-known-good map untouched and gives the model a correction opportunity.
Three render attempts are allowed by default, with duplicate failed action
fingerprints rejected and a finalization-only response after exhaustion.

The public `ChatTurnResponse` is canonical and contains the assistant message,
operation, bounded tool summaries, route, goal, completion contract,
conversation state, context usage, execution trace, and optional map session.
Operation kinds are `map_session`, `direct_answer`, `capability_catalog`,
`clarification`, `rejection`, and `error`; operation status distinguishes
success, partial, pending, and failed outcomes.

## Validation boundary

The unit and trajectory suites cover the native loop, observations, recovery,
discovery, context bounds, location safety, map acknowledgement semantics,
budget accounting, cancellation/version checks, public response shape, and
strict manifest contracts. Full provider-specific Responses/Ollama protocol
proof, credentialed geospatial provider runs, and full browser/API execution
remain explicit validation gates where the environment is required. Native
iteration checkpoints are persisted in the internal run event log and active
runs are requeued on application startup.

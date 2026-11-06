# Native Geospatial Agent Harness

Last updated: 2026-11-06

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
  committed map state, durable evidence references, unresolved questions, and
  the conversation task ledger (see *Conversation task ledger and reuse*).
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

An unqualified place name is not ambiguous when one candidate clearly
dominates: the geocoder's own importance gap (at least 0.25 with confidence
0.8, or at least 0.15 with confidence 0.7 and a rival under three quarters of
the leader's importance) selects it, and a named object (landmark, POI,
station) is never rivalled by a road of the same name unless a street, road or
address was requested. The resolved label names the chosen candidate; comparable
candidates (Springfield) still ask.

Coordinates are resolved without geocoder egress, except a coordinate
target that an `identification` obligation names: `resolve_geospatial_location`
then calls `LocationResolver.reverse_geocode`, which asks the same keyless
Nominatim service (its request pacing, User-Agent and cache follow the
provider usage policy; the parameters match `reverse_place`, so both share a
cached response) for the settlement, region and country at settlement zoom.
The names become the location's `city`, `country` and hierarchy parents with
source `reverse_geocoder` (`ResolvedLocation.reverse_geocoded_name()`), and
the tool result says `Resolved 46.0037, 8.9511: Lugano, Ticino, Switzerland.`
The identification obligation is met only by that evidence, never by the
coordinates alone.

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

A narrower deterministic fast route runs before `route_request` and skips the
routing model call. It accepts only one display verb (`show`, `display`,
`locate`) followed by a single coordinate pair, or a single place of at most
five words, optionally followed by "on the map". It defers to model routing
when the message:

- contains a conjunction, preposition, pronoun or deictic word;
- contains a data, weather or map-operation word, or the word "centre";
- uses any word a catalog entry is named or tagged by;
- arrives with an attached image.

The fast route is validated by `CapabilityRouter.validate_route` like a model
route, and resolution still runs normally, so "Show Springfield" still asks
which Springfield. The choice is recorded as `route_source` (`model`, `fast`
or `fallback`) on the run state and in the execution trace.

### Request obligations and intent verification

A route can be internally valid and still drop part of the request, because
tool exposure follows the route. Intent verification is therefore a
deterministic step between route validation and the first tool call.

- `route_request` accepts an optional `obligations` list in which the routing
  model declares every explicit part of the request as a `RouteObligation`
  (`kind`, `target_refs`, `variable`, `required`).
- `AgentGoal.obligations` holds the server-normalized `RequestObligation`
  list (`id`, `kind` in `location|data|analysis|presentation|identification`, `target_ids`,
  optional `variable`, optional per-target `temporal_scope`, `required`;
  at most 32). `derive_request_obligations` builds it from the validated
  route: one location obligation per target, one data obligation per target
  and variable when provider data is required, an analysis obligation for a
  route analysis or measurement, and a map presentation obligation. A
  coordinate-pair target of a route that answers in text (`text` or `both`)
  also gets an `identification` obligation: an answer about bare coordinates
  must say where they are. The routing model can declare `identification`
  for any place it is asked to name or describe. A declared part that none of
  these expresses is kept as its own obligation.
  Map-state targets name map content, not places, and get no location
  obligation.
- `CapabilityRouter.validate_route` drops a declared part only when one of
  its own normalizations replaced it (a catalog name removed from the places,
  a map request answered in text, a cleared analysis, a marking route), and
  each such rule is already in the decision's reason codes.
- Before any tool runs, `unrouted_obligations` checks that every required
  obligation names route targets and maps to a completion requirement or to
  the route's presentation/analysis, and the loop checks that a place already
  resolved in the conversation and named again in the message is a target.
  A violation (`obligation_target_missing`, `<kind>_obligation_unrouted`,
  `compound_obligation_dropped`, `known_place_missing_from_targets`) uses the
  single bounded route revision, with the missing obligations in the request.
  The step adds no planner and no extra model call type.
- Any route revision, whether a tool result or this check triggered it,
  must keep the prior goal's required obligations: every location and data
  place, and the analysis and presentation kinds. `dropped_obligations`
  otherwise rejects the revision, restores the prior route, goal, contract,
  task ledger and shortlist, and records `outcome: "rejected"` with the
  dropped ids.
- `AgentTaskState.create` seeds its child tasks from the same obligations,
  and the per-target coverage helpers (`uncovered_route_targets`,
  `uncovered_map_targets`, per-target scope checks) read the data and
  presentation obligation targets. Tasks, coverage and completion therefore
  share one source.

### Presentation contract and grounded answers

A map that rendered is not a request that was fulfilled, and an answer is not
true because it sounds finished. Two server-owned structures separate the two.

- `PresentationContract` (`domain/agent/presentation_contract.py`) is built by
  `presentation_contract(state, map_session)` when a candidate is prepared and
  stored on the run presentation. Its `targets` are the places of the
  presentation obligation (none for map-state edits); its `findings` are the
  candidate verdicts: a compared place with no layer (`uncovered_map_targets`),
  a layer outside the requested time window (`assess_evidence`), a requested
  transform that failed, and requested values shown only as bare place markers.
  A marker counts as carrying data only with an `annotation` (the optional
  `mark_locations.annotations` value labels, which `apply_map_plan` rejects when
  a number is not in the run's evidence).
- `RenderCompletionService.acknowledge` evaluates the contract against the
  browser viewport of a `ready` acknowledgment: every point target's centre must
  be inside the view, while an area or global scope (`AREA_LOCATION_TYPES`) is
  judged by `results_in_viewport` of the rendered result extent (at least 0.5),
  never by its arbitrary centre; and a fine place (landmark, address, station, street...) or local one
  (district, neighbourhood) must be framed at its own scale rather than as its
  parent city. A violation turns the acknowledgment into a failed observation
  (`failure_stage: "presentation_contract"`) with a compact reason, which
  re-enters the loop through the ordinary `revise_map` recovery and its render
  attempt budget. Vision capture stays conditional.
- A render acknowledgment decides presentation obligations only. Data,
  analysis and location obligations read their own completion requirements.
- `build_completion_summary` derives a `CompletionSummary` (per obligation:
  status `met|unmet|failed`, evidence ref, leading verified values; map state
  `rendered|failed|none`; presentation findings; layers truncated by a
  `transform_evidence` `limit`, recorded as `truncated_from`). It is appended
  as a system message to the tools-disabled final-answer call and checked by
  `check_final_answer`, which additionally flags: undisclosed unmet
  obligations, map content described without a verified map, temperature,
  wind, pressure and magnitude values the evidence does not support (a datum,
  a difference of two data or a unit conversion), undisclosed truncation, and
  an identified place the answer never names (a met `identification`
  outcome carries the full name in `values` and its spellings in
  `answer_must_name`, which feed `required_targets`; an unmet one is
  undelivered and must be disclosed), and
  a count of mapped records ("all 205 events") in a map sentence that exceeds
  the rendered feature count or equals a truncated layer's total.
  A rejected answer is replaced by deterministic text, and the finalizers
  append the summary's disclosure.
- Once every requested data query is verified empty (`data_verified_empty`),
  the loop stops and answers honestly instead of mapping empty data.
- A live `current` reading is accepted within two hours of the routed instant,
  so a pure information answer no longer waits on `temporal_scope_applied`.

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

### Conversation task ledger and reuse

`ConversationState.tasks` (at most 32 `ConversationTask` entries) is the
single record of what earlier turns verifiably established. Each entry is one
request obligation's outcome: `task_id` (the obligation id, e.g.
`data:paris:temperature`), `description`, `kind`, `status`
(`in_progress|completed|failed`), `dependencies`, `target_ids`,
`capability_id`, `variable`, `temporal_scope`, `filters`, `evidence_refs`,
`map_revision` (content fingerprint of the prepared or shown map),
`source_request_id` and `completed_at`.

- **Writes.** `ledger_outcomes` (`services/agent/completion.py`) turns the
  run's `CompletionSummary` and its own tool results into entries: a met
  obligation completes, a failed one fails, an unmet one is not recorded
  except a map awaiting the browser (`in_progress`). Cancelled or superseded
  runs record nothing; model text is never read. The native orchestrator
  folds them in at the commit with `merge_ledger` (a newer outcome replaces
  the same `task_id`, a failure never erases a completed result, the oldest
  completed entries are evicted first). A map commit, in the orchestrator or
  at the render acknowledgment (`ConversationState.with_committed_map`),
  completes the presentation task whose `map_revision` matches. A data
  entry's `completed_at` is the evidence fetch time, so reuse never extends
  freshness.
- **Projection.** The pre-route context carries `conversation_tasks` (the
  latest request's entries plus known places, at most 12, compact) in place
  of the previous turn's `goal` and `route`, which are no longer projected:
  a follow-up is routed afresh instead of copying a stale route.
- **Compatibility.** Once the goal is compiled, `compatible_tasks` narrows
  `AgentRunState.prior_tasks` to completed places the goal names and fresh
  evidence whose geography, variable, time window (bounds may drift by the
  evidence lifetime) and filters agree with the goal. Freshness is the
  manifest `cachePolicy.ttlSeconds` plus `staleWhileRevalidateSeconds` when a
  positive TTL is declared, else 900 s. The working-state message lists the
  survivors as `reusable_evidence`.
- **Evidence reuse gate.** Every evidence record stores its bound request
  (`provenance.request`). Before a provider call,
  `CapabilityExecutionService.reuse_evidence` answers an identical bound
  request from a compatible entry's stored evidence (same capability, place,
  filters and arguments; time bounds within the lifetime; still fresh) and
  returns a `reused_evidence_ref` result without a provider request. A changed
  window, filter or place makes a normal provider call.
- **Map no-op gate.** When a prepared candidate's `map_fingerprint` (basemap,
  viewport, payload and overlays; ids, timestamps and revisions excluded)
  equals the committed map and the client-reported view still contains its
  centre, `apply_map_plan` prepares no candidate, records the render as
  verified and returns `render_status: already_shown`; the presentation
  obligation is met by the map already shown.
- **Route carry-over.** Besides the projection change, the pre-tool intent
  check rejects a route whose target is an earlier turn's data subject (for
  example "weather radar" after "Remove that layer and just show Tokyo")
  with `prior_subject_used_as_place`. A map-state route with no map yet whose
  targets are only layers ("Never mind, just show Tokyo" after the radar was
  unavailable) becomes a new map of the already resolved places the message
  names again (`places_named_in` over the conversation's resolved locations,
  shared with the `known_place_missing_from_targets` check) instead of asking
  which place to show; the single route revision is asked for
  place targets only, and the misread target is not counted as a dropped
  obligation.

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
- `discover_geospatial_provider_layers` (explicit provider-discovery routes only)
- `describe_geospatial_capability`
- `execute_geospatial_capability`
- `inspect_evidence`
- `transform_evidence`
- `measure_geospatial`
- `apply_map_plan`
- `search_conversation_history` (conditional history-repository registration)

`inspect_evidence` pages accept `sort_by`/`ascending`, so a top-k or "strongest"
question over stored evidence is one inspection, with no derived dataset.
`apply_map_plan` removes a committed layer when the plan adds a layer of the
same capability whose evidence has the same query subject (operation, place,
bbox, radius) but another time window or filter; a plan with `remove_layer`,
`keep_only_layers` or several layers of one capability keeps its own choice.

`transform_evidence` is the runtime name. `discover_geospatial_capabilities`
is the generic model-facing capability-discovery boundary.
When the request's terms name a capability's subject (id, name, keywords,
tags, planner hints, variables, label), capabilities that match only through
descriptive prose ("rainfall hotspot identification") are dropped from the
shortlist, so a fire request never offers a precipitation raster.
A raster descriptor is renderable imagery, not records: `transform_evidence`
on it fails at once. For a request for values (`needs_numeric_values`) the
error is terminal (`unsupported_evidence_records`) and the run answers in prose
that only imagery exists and can be shown; otherwise the error points to
`apply_map_plan`.

`discover_geospatial_provider_layers` is also model-facing, but only when the
route explicitly requests provider-native discovery and the generic manifest
catalog is insufficient. It is not an interchangeable discovery alternative
for ordinary capability discovery or a named provider-layer map request.

The registry has one `RegisteredTool` contract and one `ToolExecutor` boundary.
The executor validates policy and arguments, binds server-owned geography/time
parameters, checks and accounts for budgets, applies the resolved timeout,
records a trace span, invokes the handler, and normalizes the result.

A capability whose declared coverage (`executionContract.coverage`, else
`coverage`) excludes the resolved place is rejected by `PolicyEngine` with the
same `coverage_matches` rule the shortlist applies (code
`unavailable_coverage`, recovery `request_user_input`). The reason is the
user-facing answer, not a policy string: it names the source, the area it
covers, and the place. It also offers the next eligible source for the same
phenomenon, which is the first of the manifest's `fallback_ids` and then the
run's ranked shortlist that is enabled, accessible, not excluded, covers the
place, and shares a `plannerHints` entry ("NOAA Radar only covers United
States, so it has no data for Tokyo, Japan. RainViewer Recent Precipitation
Radar covers Tokyo, Japan for the same kind of data. Should I use it
instead?"). Without one, the reply says no other shortlisted source covers
the place.

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

explicit provider-native discovery route
  -> discover_geospatial_provider_layers

shortlist selected
  -> describe_geospatial_capability (only when detail is needed)
  -> execute_geospatial_capability (when data is required)

evidence analysis or transformation required
  -> inspect_evidence, transform_evidence

resolved-location measurement requested
  -> measure_geospatial

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
descriptors are bounded normalized observations on an explicit provider-native
discovery route. They are never unrestricted provider browsing, and ordinary
catalog discovery remains a separate generic responsibility.

### Spatial operations, multi-target completion, and current view

`measure_geospatial` computes WGS84 ellipsoidal distances and bearings between
resolved centres, bounding-box dimensions/area (not administrative polygon area),
and point country membership against simplified Natural Earth polygons.
`transform_evidence` supports `distance_from`, `country_tag`, projection that
retains geometry, and provenance tags when combining evidence sets. Near-border
country assignments inherit the reference geometry's simplification limits.

Comparisons require successful data retrieval for every resolved route target.
Compact checkpoints retain the execution's `query.location_ref` even when the
model-facing weather projection omits query arguments. Analysis follow-ups can
resolve a result point within the requested region, query another source there,
and include that located source alongside the derived result on the map.

Each browser request may carry bounded `map_view` state: viewport bounds, centre,
zoom, basemap and overlay visibility/opacity. It is explicitly client-reported,
not a render acknowledgment. Resolving `current map view` uses that viewport as
an area and retains the existing provider-specific minimum-extent safeguards.
Structured state is preferred for identity, visibility and viewport questions;
screenshots remain subject to the configured vision policy and add value for
visual quality or failure diagnosis that structured checks cannot establish.

Render errors identify source and HTTP status where available. Overlay/style
errors fail a candidate; an isolated basemap tile error does not discard useful
overlays. The basemap selector is locked while a candidate awaits acknowledgment.
A server watchdog expires an unacknowledged candidate and is cancelled on runtime
shutdown. `results_in_viewport` is a planar bounding-box overlap fraction, not a
count of visible features or proof of visible raster pixels.

After a verified nearest-result rendering defect, distinct nearby derived points
use their actual display extent with the existing 0.001° landmark presentation
floor. Single or coincident points retain the 0.25° broad evidence view. This
presentation exception does not lower provider query bounding-box constraints.

A run gets at most one reserved terminal model call beyond its ordinary model
call cap, within the remaining deadline. If synthesis fails, a bounded summary of
successful tool results remains available. Exhaustion preserves failure/pending
requirements; it cannot promote an incomplete run to successful completion.

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

Equivalent successful calls are replay-protected only for tools registered
`idempotent` (discovery, description, inspection, measurement, history); live
or state-changing tools such as `execute_geospatial_capability` and
`transform_evidence` always re-execute. Repeated failing fingerprints are
suppressed. A capability excluded after an alternate-source or
replan failure is rejected by policy for the rest of the run. Calls beyond the
per-step batch limit are not executed and receive a typed
`tool_call_not_executed` observation, so every model call ID is answered. A
terminal signal during a parallel batch cancels the sibling calls. Route
filters are task-owned; model filters may add keys but not override them. Tool timeouts normally become observations so an
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

### Basemap and viewport control

Basemap changes, zoom, pan and recentring of the shown map are `map_state`
routes. A centre phrase that names the shown place ("the city centre") is not
resolved as a new place. `set_viewport` supports `fit_location`,
`fit_evidence`, `preserve_current`, `zoom_in`, `zoom_out` and `pan`. The model
picks only `steps` (1–4 zoom levels or half-view moves), `direction` (pan) and
`anchor` (`current_view` or the shown place). The server computes the new
bounds from the client-reported view, and the browser fits to them. A request
that names a centre always zooms on the shown place. Bounds are clamped to the
renderable world (±85° latitude). A location-only map of several named places
takes one `fit_location`; the harness then widens the view to the padded union
of every resolved place, and `apply_map_plan` is rejected (`targets_not_in_view`)
only if a place still cannot be framed.

Marking places is an annotation of the shown map, not a new subject. "Mark",
"pin" or "point out" requests route as operation `mark_locations` (domain
`map_rendering`, `location_mode=target`, each place in `target_refs`, no
provider query; a marking route without places asks which places to mark).
When the user lets the model choose ("by your knowledge"), the model may name
the places from general knowledge, but every position comes from
`resolve_geospatial_location` and the answer must call them suggestions. The
`mark_locations` map action builds one server-owned `place-markers` GeoJSON
layer (instance `place-markers`, replaced on the next marking) from the
resolved refs; the browser draws red points with HTML name labels, because
raster basemap styles carry no glyphs. Marking keeps the shown place and the
client-reported view, drops any `fit_location` in the same plan, and widens
the view only when a marker falls outside it. A marking route requires the
`locations_marked` obligation: a plan without `mark_locations` is rejected, and
the run is not complete until the marker layer holds every requested place.
If the model stops after resolving them, the server issues the marking itself.

Dated rasters report their own temporal coverage. NASA GIBS compares the
requested day with the layer's catalog time extent: a covered day marks the
temporal scope satisfied, an uncovered day (not yet published or never
published) returns `valid_empty` with the layer's latest available date, and an
upstream tile 404 is answered as HTTP 404 (no data), not 502 (provider fault).

Analytical contract (Phase 3). `requested_attributes` that the Open-Meteo
adapter offers (for example `cloud_cover`) are fetched and reported: grid
features carry `<variable>_mean` over the window, point forecasts keep the
variable in the hourly rows the model sees; an attribute a weather/air-quality
source lacks is listed in `unmet_requested_attributes` with a warning.
`transform_evidence` fails (`invalid_transform`, naming the numeric fields that
exist) when it sorts, filters or aggregates on a field no record has, and drops
located records that fall in another country than the single requested country
(`excluded_outside_scope_count`). A request that asks for a maximum, minimum,
average or similar over a period is a request for values: raster imagery never
satisfies it, and the stop text says that only imagery was available. Data
obligations derived from the route's queries ignore paraphrases no catalog
entry names. A catalog-discovery answer falls back to the discovered sources,
a forecast answer to the variable ranges, and a multi-place answer must name
every resolved place (`check_final_answer`, `required_targets`). A radius
request ("around Lugano") is served by point sources, generic words such as
"measurements" no longer block a subject match, and a city name is not made
ambiguous by a longer name that only lists it as an alternate name.

A basemap style named by the user outranks the model's choice. Conflicting
styles, unsupported commercial styles (Google, Bing, Mapbox, Apple, Yandex,
hybrid) and mismatches are disclosed in the final answer. A `map_state` request
with no map yet asks which place to show. If the next turn names a place, that
starts a new map in the style named in the previous turn. "Which basemaps…"
questions list the catalog basemaps only.

Route robustness for weaker tool-calling models: `location_mode` defaults to
`none` (the router upgrades it when a place is needed). A final route attempt
with a map presentation but no `task_mode` executes. A model question while the
place is still unresolved ends as a clarification. A Chat Completions response
with reasoning but no answer or tool call is resampled once. A text-only answer
route may use the reserved terminal call when its ordinary calls returned no
text.

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

## Intent-driven regional investigation

Routes separate geography (`location_mode`: `none`, `target`, `search_area`) from
analysis (`rank`, `hotspot`, `threshold`, with metric, order and top_k 1–25).
The place is the subject in target mode; in search-area mode the investigation
finds result locations inside the requested area. An unspecified area becomes
World. A static alias-only macro-region catalog binds an ordinary
`ResolvedLocation` with a bbox at bootstrap. Countries such as Italy retain the
normal resolver; ambiguous city names still require clarification. Earlier
location references cannot satisfy a different search area.

Analysis uses existing tools: retrieve evidence, sort and limit for ranks,
`grid_aggregate` for hotspots, or `attribute_filter` for thresholds, then map the
derived reference with `value_encoding` and `fit_evidence`. Provider operations
remain retrieval primitives; analysis names are not provider operations.
`search_area_bound` and `result_locations_derived` are server-owned completion
obligations. A map is unavailable until a located or valid-empty transform exists.

Macro regions list their member countries (ISO alpha-2). Area sampling masks
the bbox with simplified Natural Earth 1:50m country shapes (0.05° coastal
buffer): only land of member countries is sampled, so Europe excludes North
Africa and Anatolia and sea cells are never requested. The grid densifies until
masked land points approach a 300-point budget, fetched as cached Open-Meteo
calls of at most 100 locations (World spacing about 8.6°). A refinement pass
re-samples a 3×3 neighbourhood at one third of the spacing around the five
strongest coarse cells per metric (`sample_stage: refined`). Hourly
accumulation excludes future hours; numeric values retain units and per-point
local time windows. Coverage identifies model estimates, region, mask source,
requested, refined and usable samples, spacing, excluded out-of-region points,
and missing data.

Earthquakes: `emsc_earthquakes` (EMSC SeismicPortal FDSN) declares an
`executionContract.preferred_bbox` over Europe, the Mediterranean and the
Middle East and outranks the global `usgs_earthquakes` there; USGS still wins
elsewhere and whenever named. Both accept `filters.min_magnitude`, report
truncation and a catalog completeness note (EMSC: about M2.5–3 in Europe), and
for a macro region keep only events within 0.5° of member countries.

`transform_evidence` reverse-geocodes up to ten leading coordinate-only result
points through Nominatim (`place_label`, `label_kind:
nearest_reverse_geocoded`); answers say "near <place>" and keep coordinates.
Final answers must disclose these boundaries and describe sampled extrema as
sampled, not verified regional maxima.

Visual clues: the composer uploads one image (downscaled to 1024 px JPEG) to
`POST /api/chat/attachments`; `run.start` references its `attachment_id`. The
image is held in the in-memory capture store (900 s TTL) and attached to every
model call of that run when the model reports vision; otherwise the model is
told it cannot view images. Image-inferred places are hypotheses with named
cues. The resolver collapses local ordinals (7e, 1er) when matching geocoder
candidates.

Remaining limitations: Open-Meteo values are model estimates and sampling can
still miss extremes between samples. Earthquake catalogs remain incomplete
below their completeness magnitude. Masks are simplified 1:50m shapes, so
islands under about 5 km and fine coastlines are approximate. Attached images
live in memory only and are lost on restart; only one image per request.

Ingestion-only sources (runtime `availability_mode: ingestion_only`, currently
OurAirports) are never shortlisted for live execution; discovery reports them
as only available through dataset ingestion. Overpass POI search covers
airports (`aeroway=aerodrome`) and attractions (`tourism=attraction|museum|
viewpoint`, `historic=monument`) without credentials, and keeps results of any
queried OSM key instead of only amenity-style keys.

Recovery keeps failures visible. A route revision re-compiles the goal and is rejected if it drops a required obligation of the earlier goal (a data obligation included), so a bare location fit cannot satisfy a data request. Exhausted model-transport retries end with a model-service-outage message, distinct from geospatial provider outages and from invalid tool calls. Nominatim retries DNS, 429 and 5xx failures (not timeouts); an Open-Meteo grid batch retries once on a 5xx, and a still-missing batch makes the result `partial` with a warning naming the cause. A dated raster whose layer publishes no imagery for that day (`temporal_scope_satisfied` false with a `latest_available_date`) stops the run at once with that disclosure. A tool the step did not expose is rejected with a hint to issue it in the next step; `fit_evidence` on evidence without a bbox fits the target location.

# Native geospatial agent-loop remediation report

Date: 2026-09-17
Repository: AEGIS Geospatial View
Branch: `develop`
Implementation commit: `c3b009bf` (`feat(agent): resume native loop after render acknowledgements`)
Documentation/evidence commits: `d3c8514d`, `7c97e484`, `6aa253d5`

## Executive summary

AEGIS already had a genuine bounded native tool loop: the model selected typed
actions, deterministic code executed them, bounded observations were persisted,
and the next model decision used the updated checkpoint. The foundational gap
was the MapLibre handshake. `apply_map_plan` suspended the run, but a ready or
failed `map.render_ack` ended the reasoning path instead of becoming model
input. A failed render could therefore not drive a revised map plan in the same
user turn, and a prepared candidate was too close to being treated as success.

The remediation keeps the Angular/FastAPI/SQLite/MapLibre architecture and makes
rendering a resumable phase of the same run. Acknowledgments are normalized into
bounded `RenderObservation` objects, stored with the checkpoint, and reinjected
into the native loop. Failed candidates preserve the last-known-good map and
resume model reasoning; ready candidates are committed atomically and then use a
tools-disabled finalization call. Three render attempts and two no-progress
corrections are configurable defaults. Operational traces now describe
suspension, observation, resumption, completion decisions, and retry exhaustion.

## 1. Current architecture map

```text
GeospatialPageComponent
  -> RealtimeConnection (WebSocket protocol/parsers)
  -> RunLifecycleService (start/steer/cancel/render-ack routing)
  -> AgentRunOrchestrator (durable run worker and completion persistence)
  -> NativeAgentOrchestrator (conversation hydration and turn boundary)
  -> AgentContextAssembler + AgentStateFactory
  -> AgentLoop
       -> route_request / capability narrowing
       -> ToolRegistry + ToolExecutor
       -> native handlers and provider registry
       -> evidence store and bounded ModelObservation
       -> checkpoint, trace, completion evaluation
  -> ChatTurnResponse / lifecycle events
  -> map_prepared candidate
  -> MapLibre candidate staging and deterministic browser checks
  -> map.render_ack
  -> RenderCompletionService
       -> RenderObservation persisted to the same AgentRun checkpoint
       -> failed: discard candidate, keep last-known-good map, resume AgentLoop
       -> ready: atomically commit candidate, resume finalization/requirements
```

Important ownership boundaries:

- `ConversationState` is revisioned durable multi-turn state; it holds
  directives, summary, resolved locations, evidence references, and the
  committed map.
- `AgentRunState` is the checkpointable state for one turn, including goal and
  completion contract, observations, render attempts, fingerprints, counters,
  and terminal reason.
- `AgentContextView` is rebuilt before each model decision. Raw provider data is
  kept in `agent_evidence`; only bounded summaries and references enter prompts.
- `ToolRegistry` and `ToolExecutor` own discovery exposure, schema/policy
  validation, deterministic execution, timeout accounting, and result
  normalization.
- The LLM owns semantic intent interpretation, ambiguity resolution,
  capability choice, observation interpretation, and strategy changes.
- Application code owns coordinates, CRS/bounds/time binding, provider calls,
  persistence, map commands, rendering checks, retries, cancellation, and
  iteration enforcement.

## 2. Agent-loop audit

### Correctly implemented before and retained

- Model-directed native routing over a small meta-tool surface rather than a
  provider-specific hardcoded workflow.
- Typed `AgentRunState`, `CompletionContract`, capability registry, executor,
  and bounded `ModelObservation` projections.
- Durable checkpoints and run-event traces, with large geospatial payloads kept
  outside prompt history.
- Deterministic geographic binding, validation, timeout hierarchy, cancellation,
  optimistic revisions, and last-known-good map persistence.
- Capability discovery, provider-layer descriptors, pagination, and evidence
  references as application-owned contracts.

### Concrete defects found in the baseline

1. **Render was outside the loop.** Acknowledgment was effectively terminal;
   the model never saw whether a layer, viewport, tiles, or geometry rendered.
2. **Prepared state was over-counted as completion.** A map candidate/fingerprint
   could look successful before browser verification, and completion tracked
   preparation rather than `render_verified`.
3. **Resume accounting restarted.** A resumed checkpoint could reset iteration
   numbering and exceed the original turn budget.
4. **Resume/history contamination.** Resumable runs could hit completed-response
   short-circuits, and provisional assistant rows could be replayed as model
   history or duplicated on resume.
5. **Recovery was brittle.** Map/location vocabulary and server-fabricated map
   plans partially pre-empted model strategy; valid-empty or incompatible
   shortlist outcomes did not consistently reopen discovery.
6. **Context policy was too rigid.** Fixed message retrieval and an unconditional
   64k ceiling could discard useful older state independently of the selected
   model profile; summary replacement could lose facts.
7. **Render observability was weaker than tool observability.** Failures lacked
   structured stage/summary data, retry reasons, and a reconstructable terminal
   trace.

### Resulting architecture decision

Repair the existing native harness rather than introduce an external agent
framework. Rendering is now a first-class resumable phase, while deterministic
execution remains outside the model and semantic decisions remain model-owned.

## 3. Prioritized remediation plan

### P0 — same-run render feedback

- Domain: add bounded `RenderObservation`, render attempt state, fingerprints,
  and `render_verified` completion semantics in
  `app/server/domain/agent/capability_route.py` and context contracts.
- Lifecycle: route matching acknowledgments through
  `app/server/services/agent_runs/lifecycle.py` and
  `render_completion.py`; persist observation, resume the same checkpoint,
  atomically commit only ready candidates, and preserve the previous map on
  failure.
- Loop: let failed observations trigger correction, prevent exact failed action
  repetition, cap render attempts, and finalize once with
  `render_recovery_exhausted` when bounded recovery is exhausted.
- Frontend contract: send structured failure stage/summary and consume
  `render_observed` progress while keeping the last-known-good map visible.

### P1 — completion, replay, and responsibility

- Resume from cumulative checkpoint counters and one turn deadline.
- Bypass completed-response short-circuiting for `awaiting_render` runs.
- Upsert provisional assistant records by run/request identity and exclude that
  row while reconstructing model history.
- Replace map-vocabulary fallback with structured pending-requirements
  correction and bounded no-progress correction.

### P2 — context, discovery, contracts, and observability

- Use selected-model context profiles plus a configurable safety reserve; load
  history by watermark and token budget and merge summaries with deduplication.
- Reopen capability discovery after valid-empty, incompatible, or failed
  shortlist results while preserving exclusions/pagination.
- Extend realtime acknowledgments with bounded failure metadata and add
  `run_suspended`, `render_observed`, `run_resumed`, `completion_decision`, and
  `render_retry_exhausted` trace/event kinds.
- Keep OpenAPI and Angular parser/type contracts synchronized.

## 4. Implemented changes

The first incremental commit (`c3b009bf`) implements the P0/P1/P2 runtime slice:

- Render observation domain/state/context/prompt contracts and completion checks.
- Same-run render acknowledgment resume, atomic commit/rollback, idempotent
  duplicate handling, stale/superseded protocol protection, and backend check
  rejection normalization.
- Cumulative iteration/budget resumption, render retry/no-progress limits,
  action-fingerprint invalidation, tools-disabled finalization, and structured
  completion decisions.
- Provisional assistant upsert/history exclusion, discovery reopening after
  valid-empty results, dynamic render progress/retry events, and structured
  frontend failure reporting.
- Updated realtime/OpenAPI contracts, settings defaults, trace kinds, and tests.

## 5. Evaluation matrix

The matrix deliberately samples orchestration classes rather than every
provider.

### Single-turn scenarios

| Class | Representative input | Expected loop proof |
| --- | --- | --- |
| City | Rome | resolve, optional map plan, verified completion |
| Coordinates | Tokyo coordinates | coordinate binding without geocoding ambiguity |
| Landmark | Acropolis Museum | POI/monument resolution and map centering |
| Small town | Hallstatt | hierarchical place resolution |
| Mountain | Kilimanjaro | natural-feature resolution and bounds |
| Lake/hierarchy | Lake Titicaca in Peru/Bolivia | disambiguation plus scoped retrieval |
| Island | Jeju | island geometry/viewport handling |
| Park/reef | Serengeti; Great Barrier Reef | natural-feature capability choice |
| Ambiguous | Georgia | clarification rather than silent fallback |
| Misspelling | “Reykjavick” | correction/replan after no or poor result |
| Multilingual | Spanish request for Mexico City | intent and location preservation |
| Basemap | Sicily in satellite mode | map command and verified viewport/style |
| Heterogeneous data | vegetation, weather, earthquakes, US demographic/infrastructure | multiple capability classes in one loop |
| Multi-capability | locate a region, retrieve data, render a layer | more than one tool before render/finalization |

### Multi-turn scenarios

1. Rome → satellite → Lake Bracciano → environmental layer → remove it →
   vegetation layer.
2. Springfield → clarify Illinois → weather → indirect “there” reference.
3. Place → hazard layer → replace with infrastructure → nearby landmark.
4. Wrong geographic interpretation → user clarification → corrected map while
   preserving unrelated base-map state.
5. Previous-location and previous-layer references after intervening turns.

### Controlled recovery trajectories

Provider timeout/alternate capability; valid-empty/broader retrieval;
malformed arguments/corrected call; missing layer/revised map plan; viewport
mismatch/recenter; repeated failed action/non-progress rejection; render retry
exhaustion; cancellation or supersession while awaiting acknowledgment.

For each run, capture request, interpreted intent, context watermark and bounds,
exposed/selected tools, iteration sequence, bounded observations, render checks,
retry reasons, map state, final answer, call counts, completion status, and
termination reason. No chain-of-thought is captured.

## 6. Validation results

### Passing local gates

- `app/tests/unit`: **798 passed, 2 warnings**.
- Focused native/render suites: **43 passed**; render-completion subset:
  **12 passed**.
- Targeted Pyright over changed backend modules: **0 errors, 0 warnings,
  0 informations**.
- Ruff over server/tests: **passed** (only access-denied warnings for protected
  cache residue).
- Angular production build: **passed**.
- OpenAPI contract regeneration and contract tests: **passed**.

### Blocked or non-clean gates

- A full repository test attempt during integration (before the final focused
  contract fixes) reported **699 passed, 147 failed, 4 skipped, 75 warnings**.
  Failures include unavailable backend/browser services and provider/integration
  suites outside the focused native proof; this is not represented as a
  successful full gate.
- Full strict Pyright still reports baseline diagnostics in provider optional
  accesses, maintenance-service typing, transport checks, and an AgentLoop
  complexity cascade. The changed-module target is clean; the repository-wide
  baseline is not.
- The post-restart targeted Karma process was unavailable, so no Angular test
  pass is inferred from the build. The earlier historical client result is not
  reused as current evidence.
- Browser-driven MapLibre and live-provider validation were not rerun after the
  restart because the required services/credentials were unavailable. No
  current provider or browser success is claimed.

### Defect separation

The focused server tests prove orchestration behavior with deterministic fake
models/providers. Any unavailable upstream provider, credential, hosted CI, or
browser service is an environment/provider gate, not silently converted into
agent success. The remaining repository-wide typing and integration failures
are tracked separately from the render-loop implementation.

## 7. Final architecture assessment

The native runtime now satisfies the foundational acceptance properties: tool
and render observations re-enter one bounded run; failed rendering can trigger
a revised action; verified rendering precedes completion; multi-turn state and
last-known-good map state are durable; capability discovery can reopen; and
terminal outcomes are reconstructable from sanitized traces.

Remaining risks are provider-specific protocol parity (OpenAI Responses/Ollama),
full strict typing cleanup, complete Angular/Karma execution after restart,
browser/API E2E, and credentialed live-provider coverage. Next validation should
start the supported backend/frontend services, run the matrix through actual
MapLibre, correlate WebSocket events with SQLite checkpoints and trace records,
then exercise the configured provider lanes without substitution. Protected
pytest/cache directories remain outside this remediation scope.

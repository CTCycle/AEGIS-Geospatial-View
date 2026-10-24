# AEGIS agentic loop audit and implementation

Last updated: 2026-10-24

## Scope and provenance

Continued Opus's uncommitted implementation and supplied F1–F14 plan from
`develop@24bad37d`. Created `loop-dev` at the user's subsequent instruction;
no worktree, new agent framework, multi-agent system, or provider substitution.
The baseline JSON is inherited evidence, not a baseline independently reproduced
by this continuation. New runs use the saved `opencode-go / deepseek-v4.1-flash`
configuration in an isolated SQLite backup at `runtimes/cache/test-runtime/agent-loop-audit`.
The original application on 7059 and unrelated listeners were not terminated by this task. The user rebooted the computer on October 24; only the isolated audit runtime was restarted afterwards.

Overall audit status remains **PARTIAL**: the fixes have deterministic coverage
and selected real provider/browser evidence; this is not certification of every
provider, all visual fault paths, or every unconstrained geospatial question.

## Architecture assessment

AEGIS already has the appropriate basic architecture: one model-directed loop
with deterministic contracts and geography binding. Keep it.

| Boundary | Owning implementation | Assessment |
| --- | --- | --- |
| API / run lifecycle | `api/chat.py`, `api/realtime.py`, `services/agent_runs/lifecycle.py` | Persisted runs, cancellation, revisions, WebSocket events and browser continuation; no alternate execution harness needed. |
| Routing / goal | `services/agent/capability_router.py`, `agent_loop.py:_compile_native_goal` | Typed semantic route and application-owned completion obligations; remaining one-shot routing and lexical subject matching can constrain autonomy. |
| Decisions / recovery | `services/agent/agent_loop.py:run`, `_execute_calls`, `_terminal_synthesis` | Progressive tools, bounded budgets, parallel independent tool batches, replay protection, consecutive failure correction and one tools-disabled terminal synthesis. |
| Tool contracts | `services/agent/native_tools.py`, `tool_definitions.py`, `tool_executor.py`, `policy_engine.py` | One validated execution boundary. Shared execution eligibility avoids offering tools that policy immediately rejects. |
| Context / state | `services/agent/context_assembler.py`, `domain/agent/capability_route.py:AgentRunState`, conversation/evidence repositories | Durable evidence stays out of model messages; pair-safe history and bounded projections. Checkpoints must retain application state even when model projections omit it. |
| Geospatial operations | `tool_handlers/measure.py`, `tool_handlers/evidence.py`, `services/geospatial/spatial_constraints.py`, `land_mask.py` | Deterministic WGS84 measurements, evidence transformations and simplified country membership; no LLM coordinate arithmetic. |
| Providers | `services/geospatial/provider_registry.py`, `providers/`, `services/llm/` | Existing normalized adapters and exact configured model identity retained. Live parity across all LLMs remains unverified. |
| Map candidate / commit | `services/agent/map_plan_service.py`, `services/agent_runs/render_completion.py`, `repositories/agent_runs.py` | Candidate is distinct from committed map. A real browser acknowledgment feeds back into the same loop; failure retains the last committed map. |
| Browser / map | `components/map-preview.component.ts`, `pages/geospatial-page.component.ts`, `core/realtime.service.ts` | MapLibre settlement, source/layer/visibility checks, revision identity, viewport state, and configurable vision capture. Opacity precedence required correction. |

Data flow: user request plus optional bounded client viewport → typed route →
location resolution/catalog tools → provider/evidence/measurement operations →
typed map plan → staged MapLibre rendering → render observation → atomic commit
or bounded correction → grounded terminal answer. A provider success or canvas
alone never proves a geospatial task or map is correct.

## Findings and implemented improvements

The original findings were checked against the supplied baseline and code;
additional defects below were reproduced in the running application.

| ID / severity | Root cause and impact | Change / evidence boundary |
| --- | --- | --- |
| F1–F2 HIGH | Ordinary model budget could end before synthesis and discard useful results. | One reserved terminal slot within remaining deadline; generic tool-summary fallback; pending requirements remain explicit and incomplete runs remain incomplete. Backend budget/trajectory tests. |
| F3 HIGH | First city's successful data execution could satisfy a comparison. | Per-target coverage in completion and exposure. Live two-city Open-Meteo retrieval and map; additional checkpoint fix below. |
| F4 HIGH | Distance requests had no reachable deterministic tool. | `measure_geospatial`: geodesic distance/bearing, bbox dimensions/area, country of point. Live Rome–Milan now returns 477 km instead of discovery failure. Extent measures a bounding box, not an administrative polygon. |
| F5 MED | Unrelated invalid calls accumulated even after progress. | Correction counter resets after successful progress; consecutive-invalid protection remains. Backend regressions. |
| F6 MED | Exposure and execution eligibility used different domain rules. | Shared `route_allows_capability_execution` predicate. Existing provider contracts preserved. |
| F7 MED | Only server map memory was available; panning/local visibility was missing. | Bounded `map_view` on chat/realtime requests, explicitly client-reported; current-view resolver uses actual submitted viewport. Existing minimum extents retained. |
| F8 MED | Every MapLibre error killed a candidate with a generic message. | Overlay/style errors remain fatal and identify source/status when present; isolated basemap-source errors do not discard valid overlays. Actual overlay fault matrix remains incomplete. |
| F9 MED | An absent render acknowledgment could leave a permanent pending run. | Server watchdog plus basemap-selector lock. Real absent-ack run terminates `render_timeout` in 95.173 s with the saved 90 s acknowledgment limit, including preceding work. Watchdogs cancel on runtime shutdown. |
| F10 LOW | Vision captions used cleared candidate state and the wrong collection field. | Captions use candidate/committed session instances. Policy unchanged; no claim of new live vision-provider parity. |
| F11 MED | Overpass cut results before nearest-distance sorting. | Fetch up to four times the requested count, bounded at 2,000; sort then trim; expose upstream truncation. This cannot guarantee a global nearest result if the upstream result is truncated. |
| F12 LOW | GeoJSON projection ignored `properties`; negative values and missing grid metrics sorted incorrectly; discovery lost useful fields. | Geometry-preserving projection, correct numeric ordering, richer discovery projection; `distance_from`, `country_tag`, source tags across combined evidence. Regression tests. |
| F13 LOW | Duplicated route/native prompts, dropped correction messages, duplicated provider preference. | Route-only bootstrap prompt, latest correction retained, typo and redundant preference removed. |
| F14 MED | No keyless city population/area facts. | Wikidata entity adapter via Nominatim QIDs, dated population, area/elevation, source attribution and valid-empty missing-QID behavior. Real Paris/Berlin entity comparison succeeds with different dates/admin units explained. Discovery manifest needed additional subject declarations. |
| C1 HIGH | Weather result projection discarded `query.location_ref` during checkpointing. Both live layers rendered, but render validation rejected missing target coverage. | Preserve only the bounded target binding outside model projection. Round-trip regression and real successful rerun. |
| C2 MED | Analysis map validator required every layer to be ranked using the first source's metric. Weather at a derived epicentre was rejected after successful investigation. | Admit located follow-up evidence at an in-scope resolved result point; still reject raw unranked analysis inputs. Discovery uses the follow-up point rather than the original continent extent. Real USGS → transform → resolve → Open-Meteo → render path passes. |
| C3 MED | A third map-state operation allowlist remained in map-plan location selection. `hide` was routed and exposed but treated the layer name as a place. | Reuse the shared map-update predicate in map-plan location selection. Parametrized canonical/`hide` regression; live hide rerun passes. |
| C4 MED | Browser retained old local opacity when a new canonical session/revision changed it. Text and stored state said 40%, browser viewport reported full opacity. | New revisions apply canonical opacity; same-revision echoes/restores retain saved preferences. Updated meaningful frontend regression and real visual follow-up. |
| C5 LOW | New viewport store was not cleared/expired consistently and watchdog tasks were not part of shutdown. | Expire unread viewport entries, clear capture/attachment/view state, cancel and await watchdogs before repositories close. Focused lifecycle regressions. |
| C6 HIGH | Current-day granularity synthesized a start 24 hours ago. The live rainfall answer included yesterday in its declared window. | Preserve calendar-day semantics for current/day requests. The live rerun starts at local midnight and changes the sampled winner from Chichester to Maizières; it still discloses model estimates and sampling limits. |
| C7 MED | Strong subject matching discarded Wikidata when demographics/statistics were only hinted. The agent selected Eurostat boundary metadata with no population figures. | Declare demographics and population-statistics aliases in the manifest; test both natural subject variants. Explicit and natural-language Wikidata live comparisons both pass. |
| C8 MED | A layer-hide route requested text-only presentation, leaving the map tool hidden even though it was a map mutation. | Validated active-map mutations normalize to a browser-verified presentation; regression covers text/map route variants. |
| C9 MED | A fixed city-scale minimum viewport made the five nearest pharmacies within 320 m overlap visually despite a ready acknowledgment. | Fit distinct nearby derived results to their actual extent with the existing 0.001° landmark presentation floor. Single/coincident result sets retain the 0.25° broad view. Provider query minimum extents and all spatial-execution safeguards are unchanged. The narrower presentation exception addresses an observed defect, with single-point and coincident-point regressions. |

Credential UI work inherited from Opus is a separate commit: explicit Save key
button/Enter, disabled during writes, no blur/timer credential writes, retained
noncredential autosave and actionable failures. No credentials are recorded here.

## Engineering guidance comparison

- [Anthropic, Building effective agents](https://www.anthropic.com/research/building-effective-agents): keep the existing simple loop, explicit tool interfaces, real environment feedback and bounded stopping. The audit addresses blocked tool paths rather than adding orchestration layers.
- [OpenAI, A practical guide to building agents](https://cdn.openai.com/business-guides-and-resources/a-practical-guide-to-building-agents.pdf): preserve one agent, deterministic tool contracts and explicit exit conditions; add complexity only when task evidence requires it.
- [OpenAI agent evaluation guidance](https://developers.openai.com/api/docs/guides/agent-evals) and [trace grading](https://developers.openai.com/api/docs/guides/trace-grading): assess decisions/tools/verification from operational traces, not polished final text alone. Failed runs remain in the evidence.
- [MapLibre lifecycle documentation](https://maplibre.org/maplibre-gl-js/docs/API/type-aliases/MapEventType/): `load`, source events, `idle`, and `error` describe distinct lifecycle boundaries. Source existence alone does not establish loaded/visible results. The installed renderer remains MapLibre 4.x; no dependency upgrade was introduced from current online documentation.

Structured map state is sufficient for layer identities, opacity/visibility and
viewport requests. Screenshot vision is justified for visual failure diagnosis,
appearance, or tasks whose answer depends on pixels. Keep configured policies;
do not capture every iteration. `results_in_viewport` measures planar bounding-box
overlap, not visible feature percentage or geodesic area.

## Validation and performance

See `scenarios.tsv`, `post-change-runs.json`, `baseline/runs.json`, screenshots
and bounded gate logs in this directory. `collect_runs.py` collected sanitized
operational summaries from the isolated runtime during the campaign; it saves no system prompts, credentials
or private model continuation. Provider/model identity is the configured exact
lane; some public responses were cached. Latency samples are not a controlled
benchmark, and baseline/post-change samples differ in time and upstream data.

Useful measured changes: distance goes from failure (3 model/4 tool calls) to a
correct result (4 model/4 tool calls); the successful multi-source investigation
uses 9 model/8 tool calls, compared with the inherited failure's 7/7. A meaningful
extra step that completes the task is preferable to the shorter failed run.
The fresh two-city map uses 6 model/6 tool calls, matching the inherited successful
baseline. Layer hide and opacity each need one tool call. No broad speedup is claimed.

Quality gates and precise scenario outcomes are recorded in the final ledger
entry. Deterministic tests exercise provider errors, budget boundaries,
cancellation, protocol continuation, bbox safeguards and render failure without
pretending those are live-provider or browser-pixel evidence.

## Remaining opportunities and limitations

- Live parity across other configured cloud and local model families, vision-policy
  combinations, genuine provider outage recovery and actual overlay transport/pixel
  fault injection still need separate campaigns. This run does not promote them.
- One-shot routing and strict lexical subject matching remain brittle; catalog
  declarations should improve before introducing a replanning architecture.
- EMSC's inherited baseline used a rolling month instead of a strict calendar month;
  that discrepancy was disclosed in its answer but is not resolved by this work.
- Continental rainfall is a sampled forecast/model maximum with a stated time window,
  not a verified maximum among all rain gauges. Country membership uses simplified
  reference shapes and cannot settle disputed boundaries or precise coastlines.
- Wikidata dates and administrative definitions differ. The adapter is not a
  harmonized current-population database; missing quantities/QIDs remain missing data.
- A run may be lifecycle `completed` after an honest no-answer/clarification. Evaluate
  scenario correctness and task completion separately from that transport state.
- Checkpoint compaction retains bounded recent results; extremely long investigations
  still need targeted coverage-retention evaluation beyond the conversation tested.
- `agent_loop.py` remains large. Decompose only behind validated contracts in a
  separate maintenance change; no speculative planner or framework was added here.

## Final quality gates (implementation through `79ac8c60`)

| Gate | Result | Evidence |
| --- | --- | --- |
| Backend unit suite | PASS — 1,184 tests, three deprecation warnings | `backend-tests-final.log` |
| Strict Pyright across the complete server | PASS — zero errors/warnings | `pyright-final.log` |
| Ruff across server and tests | PASS; pre-existing protected QA-cache directories emit access warnings | `ruff-final.log` |
| Angular production build | PASS | `build-final.log` |
| Angular/Karma | PASS — 304 tests | `frontend-tests-final.log` |
| Strict production manifest audit | PASS — zero errors/warnings | `manifests-final.log` |
| Live exact model lane | Selected scenario PASS/PARTIAL outcomes, not provider parity | `post-change-runs.json`, `scenarios.tsv` |
| Hosted CI | UNRUN — workflow push triggers cover main/develop, not loop-dev | `.github/workflows/ci.yml` |

The reboot preserved the database, committed map, transcript, and saved evidence.
The long chat was restored through the actual conversation-history UI and the
basemap correction then completed in one tool call. This validates ordinary
persisted continuity; it does not establish million-token context compaction.

## Evidence limits found during the long chat

The panned map's reported bounds were correctly reflected in the agent's text.
However, "Show earthquakes in the area currently visible on the map" failed in
that long conversation: the route correctly targeted `current map view` and the
resolver was exposed, but the model declined retrieval rather than invoking it.
The committed rainfall layer was preserved and no earthquake results were invented.
This is **PARTIAL** current-view support, not an end-to-end retrieval pass. Tool
exposure alone is insufficient; a future bounded route correction should be
justified by a larger set of such traces rather than another keyword rescue.

## Scenario roll-up (34 new live runs, including failures and retests)

The 34 runs include 25 lifecycle completions, seven failures, and two cancellations.
These are not a success-rate estimate: the campaign deliberately included negative
cases and retained intermediate failures. One cancellation was setup interruption;
one was an explicit cancellation acceptance check. Task outcomes are reviewed
separately in `scenarios.tsv`. The longest restored conversation contains 11 runs.

| Requested scenario | Reviewed outcome | Map / iteration evidence |
| --- | --- | --- |
| 1. Simple place | PASS — Colosseum | Ready acknowledgment and inspected landmark rendering; 3 model / 2 tool calls. |
| 2. Multiple places | PASS after checkpoint correction — Paris/Berlin current temperature | Two provider results, two visible layers, viewport includes both; 6 model / 6 tool calls. |
| 3. Ambiguity | PASS — Springfield clarification then Illinois | No guessed place; selected Illinois map rendered; 2/1 then 3/2 model/tool calls. |
| 4. Multi-source investigation | PASS — ranked USGS earthquake then weather at epicentre | Source limitations disclosed, derived point plus weather layer acknowledged and visually inspected; 9 model / 8 tool calls. |
| 5. Measurements / nearest | PASS after presentation correction — 477 km Rome/Milan and five nearest pharmacies | WGS84 measurement; live Overpass → distance/sort/limit → 5 features. Nearest-map bounds improve from 0.25° × 0.25° to about 0.00379° × 0.00415°, separating the results. Final nearest run: 7 model / 5 tool calls, 6.899 s. |
| 6. Unknown regional extreme | PARTIAL for the literal observational question; bounded investigation succeeds | Open-Meteo model grid with local refinement, current-day windows and explicit non-exhaustiveness; it cannot verify all European rain gauges. Original rolling-day defect retained as a before case. |
| 7. Layer interaction | PASS for history-to-map, hide/show, 40% opacity and Dark basemap; PARTIAL for current-view retrieval | Actual 40% browser control and matching narration; one tool per map mutation. Panned viewport correctly described, but subsequent earthquake lookup was not executed. |
| 8. Failure / interruption | PASS absent-ack expiry and explicit live cancellation; broader fault matrix PARTIAL | 90 s render-ack policy expires without ack (95.173 s including preceding work); cancellation preserves pharmacy map. Provider/transport/argument failures are covered deterministically, not promoted to live outage proof. |
| 9. Continuity / budgets | PARTIAL overall; ordinary 11-run persistence and recall PASS | Chat/history/map restored after reboot; original winning country and model-vs-gauge distinction recalled. Model-limit synthesis and deadline/cancellation boundaries pass deterministic tests; actual context-limit compaction and steering were not forced live. |
| 10. Answer/evidence/map agreement | Selected journeys PASS after fixes; full matrix PARTIAL | Before/after checkpoint, opacity and viewport defects were caught by real rendering. Screenshots plus acknowledgments supplement textual answers; neither alone establishes all-task correctness. |
| Extra: population | PASS — natural Paris/Berlin request, no provider named by user | Real Wikidata Q90/Q64 values, source dates, mismatched administrative definitions; one malformed call recovered before both successful entity queries. 7 model / 7 tool calls, 21.554 s. |

`nearest-pharmacies.png` records the visually inadequate before case;
`nearest-pharmacies-fitted.png` records the corrected display. `rainfall-before-calendar-fix.png`
and `rainfall-calendar-day.png` document the temporal correction. Other screenshots
cover Colosseum, Springfield, two-city weather, cross-source earthquake/weather,
opacity, restored Dark basemap, and Wikidata comparison.

## Commits and cleanup

Implementation was pushed incrementally on `loop-dev`: `c145fcc0` (inherited
agent improvements), `60072613` (explicit key saving), `76499fe0` (checkpoint and
follow-up map evidence), `e5106b00` (calendar-day/opacity/map-routing fixes),
`5f7798cc` (map presentation and basemap alias), and `79ac8c60` (visually verified
nearby-result viewport correction). Documentation and selected sanitized evidence
are committed separately. No merge or release was performed.

Task-owned runtime, browser tab and isolated credential-bearing SQLite backup
are removed during final cleanup. Pre-existing historical QA and application
state are preserved; duplicate intermediate logs from this audit are removed.

The collector requires the isolated audit database and a running audit server. After cleanup, the retained JSON/TSV and screenshots are the evidence; do not point the collector at the production database.

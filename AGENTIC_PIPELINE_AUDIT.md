# AEGIS Geospatial View — Agentic Pipeline E2E Technical Audit

Date: 2026-09-08  
Repository: G:\Projects\Repositories\Active projects\AEGIS Geospatial View  
Branch / commit: develop / e0f95a49a0df9609c39f0c411e058fbea1885104  
Audit mode: investigation only

## 1. Scope, constraints, and evidence model

This audit covers the complete request path:

natural-language geospatial request → interpretation → location resolution → capability/tool planning → provider/data access → map assembly → persistence → WebSocket/browser render acknowledgement → visible map

The audit objective was to diagnose the current implementation without changing application source, configuration, prompts, schemas, dependencies, tests, or existing runtime data. The only repository artifact created by this audit is this file. Audit-generated runtime conversations and the audit-started backend process were removed before completion.

Evidence is separated as follows:

- L — Live: current backend/frontend and the configured opencode-go / deepseek-v4-flash lane.
- C — Controlled: deterministic test fixtures exercising the API, WebSocket, MapLibre, and render acknowledgement path.
- S — Static: current source, tests, contracts, and documentation at the audited commit.
- H — Historical: prior AEGIS evidence retained only as context; it was not substituted for current verification.

The live lane was run through the existing API and the existing Chrome tab. The controlled lane was run through the repository’s existing E2E test. No raw provider credentials, secrets, or full provider payloads were recorded.

## 2. Executive verdict

The configured live agentic map path is not operational for ordinary geospatial requests at this commit.

In a 20-request live matrix, every request stopped before capability execution:

- 13 returned a generic task-class clarification/rejection.
- 5 hit the bounded structured-extraction deadline.
- 2 reached location resolution and then falsely rejected an explicitly supplied country.
- 0 native geospatial tool calls were observed.
- 0 map sessions were prepared.
- 0 live browser renders were produced.

The frontend and render-acknowledgement path is independently functional. The controlled E2E passed with a visible MapLibre canvas, one loaded earthquake overlay, valid viewport evidence, and a successful map.render_ack. The current primary failure is therefore upstream of rendering: the live provider/parser contract does not reliably produce a usable task-class/action/location contract within the parser budget.

### Priority summary

| Priority | Finding | Effect |
|---|---|---|
| P0 | The configured provider produces either an effective task_class=unclear contract or misses the 20-second parser-stage deadline for common requests. | The core live map workflow is unusable; planning, tools, and rendering are never reached. |
| P1 | Country resolution requires a strict geocoder result_type=country, rejecting valid country candidates returned as administrative. | Explicit requests for Japan and Iceland fail after successful parsing. |
| P1 | Parser schema defaults are permissive enough for sparse/default structured output to validate while retaining unclear/unknown semantics. | The system cannot distinguish a deliberate ambiguity from an unusable provider response and asks the wrong generic question. |
| P2 | The direct /api/chat/turn route returns HTTP 500 for a missing conversation instead of a client-contract error. | Direct callers that omit the frontend’s create-conversation step receive an internal error. |
| P2 | The render-ack alias branch appears to compare overlay_id twice and never compare the documented capability ID alias. | Some otherwise valid acknowledgement evidence may be rejected. |
| P2 | Frontend evidence treats visibility as part of layer_present, while backend required-overlay selection includes non-metadata instances regardless of intentional hidden state. | A hidden-but-valid overlay may be reported as missing; this is a static risk requiring a targeted regression test. |
| P2 | Model catalog health reports ok=true and reachable=null. | Catalog availability is not proof that the selected model can complete the structured parser contract. |

## 3. Reconstructed architecture and end-to-end flow

### 3.1 Composition

The composition root in app/server/app.py:115-153 creates the settings, repositories, geospatial catalog/services, search runtime, RenderCompletionService, and AgentRunOrchestrator. The application stores the resulting runtime and includes chat, conversations, realtime, jobs, and geospatial routers in app/server/app.py:175-214.

The frontend is an Angular SPA. The main geospatial page is /; the geodata catalogue is /geodata; settings and access configuration are separate routes. The interactive map uses MapLibre and the realtime conversation path uses a versioned WebSocket.

### 3.2 Pipeline diagram

~~~text
User
  │
  ▼
Angular geospatial page
  ├─ POST /api/conversations              (create conversation)
  └─ WebSocket /api/conversations/{id}/realtime
        │
        ├─ run.start / assistant / progress / clarification / map_prepared
        └─ map.render_ack
  │
  ▼
FastAPI chat/runtime
  │
  ├─ AgentExecutionBudget: 45 s absolute run budget
  ├─ context assembly: 2 s stage
  ├─ ParserService: structured extraction, 20 s orchestrator stage limit
  │     └─ LLMRequest to configured provider/model
  ├─ deterministic intent recovery only for provider-error results
  ├─ PolicyEngine: task/location/ambiguity preflight
  ├─ LocationResolver → Nominatim/reference data
  ├─ canonical interpretation / capability resolution
  ├─ DeterministicToolPlanner
  │     └─ native capabilities and provider-native layer steps
  ├─ ToolPlanExecutor or NativeToolLoop
  │     └─ retries, duplicate-call/no-progress guards, output validation
  ├─ verified results → OverlayCollection / map session
  ├─ AgentRunOrchestrator persists candidate as awaiting_render
  └─ RenderCompletionService validates browser evidence
  │
  ▼
MapLibre candidate map
  ├─ sources/layers/styles/zoom/feature evidence
  ├─ viewport bounds and required overlay checks
  └─ client sends matching map.render_ack
  │
  ▼
SQLite atomic acknowledgement
  ├─ candidate → ready
  ├─ conversation/task/memory promotion
  └─ durable terminal events
~~~

The intended single-owner map state is the revisioned OverlayCollection. A map candidate is not committed to the durable conversation until the browser acknowledgement matches the run, conversation, map session, presentation ID, collection revision, required overlays, and viewport checks.

## 4. Runtime configuration and contract inventory

### 4.1 Live configuration

The active local settings were:

| Setting | Observed value |
|---|---|
| Backend | 127.0.0.1:7059 |
| Frontend | 127.0.0.1:4512 |
| Reload | false |
| Selected provider | opencode-go |
| Selected model | deepseek-v4-flash |
| Credential health | api_key=healthy |
| Provider protocol | openai-chat-completions |
| Provider model count | 35 |
| Selected model supports tools | true |
| Selected model supports structured output | true |
| Selected model disabled reason | null |

The model catalogue endpoint reported provider ok=true but reachable=null. That is a catalogue/credential state, not completion-path proof.

The static direct-tool catalogue exposes four direct API tools (get_air_quality_forecast, get_nearby_poi, get_weather_forecast, and location_to_coordinates). The native LLM geospatial runtime exposes five tools in app/server/services/agent/agent_tool_catalog_service.py: capability listing, capability description, capability execution, provider-layer discovery, and provider-layer rendering.

### 4.2 Request and response contracts

ChatTurnRequest in app/server/contracts/chat.py:33-42 accepts message, conversation_id, request metadata, and defer_map_commit. POST /api/chat/turn in app/server/api/chat.py:87-98 calls the orchestrator directly and assumes the conversation already exists; it does not create one.

The response contract distinguishes map_session, direct_answer, capability_catalog, clarification, rejection, error, and failure_diagnostic operation kinds. Status is success, partial, or failed. A successful HTTP response is therefore not equivalent to a successful map.

## 5. Live end-to-end scenario matrix

All rows below were submitted through the current live API with a newly created conversation. The exact assistant response is quoted where it was stable. “No tool/render” means no native tool invocation, map preparation, or browser acknowledgement was observed for that row.

| # | Exact input | Expected behavior | Actual live response | Diagnosis |
|---:|---|---|---|---|
| 1 | Show a map of Italy | Resolve Italy and prepare a country map. | Can you clarify whether you want a map search or a direct answer? | Clearly unnecessary generic clarification; parser/policy contract failure. |
| 2 | Show Rome | Resolve Rome and prepare a location map. | AEGIS reached its bounded execution deadline while extracting the request. The provider call was stopped without restarting the full workflow. | No clarification was required; parser-stage deadline. |
| 3 | Show the boundary of Switzerland | Resolve Switzerland and request boundary geometry. | Same bounded extraction deadline message. | No clarification was required; parser-stage deadline. |
| 4 | Show 46.9480, 7.4474 | Parse coordinates and show the point/area. | Can you clarify whether you want a map search or a direct answer? | Clearly unnecessary generic clarification; coordinate evidence did not promote task class. |
| 5 | Show a point at 40.7128, -74.0060 | Parse coordinates and show a New York point. | Same bounded extraction deadline message. | No clarification was required; parser-stage deadline. |
| 6 | Show airports in Switzerland | Resolve Switzerland and execute airport overlay. | Can you clarify whether you want a map search or a direct answer? | Clearly unnecessary generic clarification. |
| 7 | Show the capitals of France, Germany, and Italy | Preserve all three targets and execute a compound point query. | Can you clarify whether you want a map search or a direct answer? | Clearly unnecessary generic clarification; compound intent was not reached. |
| 8 | Show volcanoes in Iceland | Use explicitly supplied Iceland target and execute volcano overlay. | I could not safely resolve Iceland. Can you provide a city, country, or coordinates? | False negative in country resolution; target was already a country. |
| 9 | Show rivers in Switzerland | Resolve Switzerland and execute river overlay. | Can you clarify whether you want a map search or a direct answer? | Clearly unnecessary generic clarification. |
| 10 | Show earthquakes in Japan | Resolve Japan and execute earthquake overlay. | I could not safely resolve Japan. Can you provide a city, country, or coordinates? | False negative in country resolution; target was already a country. |
| 11 | Show airports within 100 km of Zurich | Resolve Zurich, preserve the 100 km radius, and execute nearby-airport query. | Can you clarify whether you want a map search or a direct answer? | Clearly unnecessary generic clarification; explicit distance was not reached. |
| 12 | Show cities along the Rhine | Preserve the river relationship and execute a relational query. | Bounded extraction deadline message. | No clarification was required; parser-stage deadline. |
| 13 | Show recent earthquakes in Japan | Execute with the product’s documented recent default, or ask specifically for a time window. | Can you clarify whether you want a map search or a direct answer? | Policy-dependent clarification may be valid, but this generic task-class question is not the required temporal question. |
| 14 | Show cities in Europe by population | Execute a documented ranking/default limit, or ask for a result limit. | Can you clarify whether you want a map search or a direct answer? | Result-limit clarification could be valid, but the actual question was unrelated and generic. |
| 15 | Show the area and points and bounds for Switzerland | Preserve all requested output products and return them for Switzerland. | Can you clarify whether you want a map search or a direct answer? | Clearly unnecessary generic clarification; compound output was not reached. |
| 16 | Map Zurich | Resolve Zurich and prepare a map. | Can you clarify whether you want a map search or a direct answer? | Clearly unnecessary generic clarification. |
| 17 | Where is Rome? | Either show a map or ask a targeted map-versus-direct-answer question. | Can you clarify whether you want a map search or a direct answer? | A targeted presentation clarification can be justified, but this does not demonstrate that the parser understood the location. |
| 18 | Italy | Ask what the user wants done with the location. | Can you clarify whether you want a map search or a direct answer? | Clarification is justified because the input is only a place name. |
| 19 | Show nearby airports | Ask for the missing anchor location, or use a documented current context. | Bounded extraction deadline message. | A clarification would be justified, but the parser timed out before producing it. |
| 20 | Show the strongest earthquakes in Japan | Ask for a threshold/top-N if no product default exists, or use the documented default. | Can you clarify whether you want a map search or a direct answer? | A targeted threshold/top-N clarification can be justified; generic task-class clarification is the wrong question. |

### 5.1 Live result counts

| Result | Count |
|---|---:|
| Generic task-class clarification/rejection | 13 |
| Structured extraction deadline | 5 |
| Country location-resolution clarification | 2 |
| Native tool calls | 0 |
| Map sessions prepared | 0 |
| Final live renders | 0 |

At least eight rows (1, 4, 6, 7, 9, 11, 15, and 16) are clearly actionable map/data requests for which the generic question is unnecessary. Rows 13, 14, 17, and 20 may require a product-policy clarification, but the question must identify the missing temporal, ranking, presentation, or threshold field. Row 18 is a legitimate clarification case. Rows 2, 3, 5, 12, and 19 did not reach the point where the system could ask the right question.

## 6. Live request traces and timing

The first direct call used a nonexistent conversation ID and returned HTTP 500 with ValueError: Conversation not found. from app/server/repositories/conversations.py. Repeating the call after creating the conversation returned the structured operation response as expected. This is a secondary API precondition issue, not evidence of provider failure.

Observed direct examples:

| Request | HTTP | Elapsed | Operation outcome |
|---|---:|---:|---|
| Show Rome on a map | 200 | 22.09 s | failed/rejection with generic clarification |
| Same request with detailed trace | 200 | 19.69 s | task_class=unclear, action_id=unknown, generic clarification |
| Show a map of Italy | 200 | 21.71 s | failed/rejection with generic clarification |

The backend log showed the following live UI trace for Show a map of Italy:

~~~text
chat_turn_start request_id=run_0a1009... conversation_id=conv_171... message_length=19
agent_stage context_assembly success duration_ms=2581 remaining_ms=42413
agent_stage structured_intent_extraction success duration_ms=18035 remaining_ms=24376
agent_stage persistence success duration_ms=0 remaining_ms=24372
~~~

The parser stage returned sufficiently quickly in that run to be labelled success, but the resulting task snapshot remained task_kind=unclear, task_status=failed, with no resolved location and no map session. “Parser stage success” therefore does not mean “usable interpretation.”

The five timeout traces were logged at approximately the 20-second boundary. The backend explicitly classified them as origin=application_deadline, including request IDs for matrix rows 2, 3, 5, 12, and 19. The timeout response states that the provider call was stopped without restarting the full workflow.

## 7. Budget, loop, state, retry, and termination audit

### 7.1 Budgets

app/server/domain/agent/reliability.py:12-22 defines a 45-second default run budget and stage budgets of approximately:

| Stage | Budget |
|---|---:|
| Context assembly | 2 s |
| Structured extraction | 20 s |
| Location resolution | 12 s |
| Planning | 2 s |
| Tool execution | 20 s |
| Map assembly | 8 s |
| Synthesis | 8 s |
| Persistence | 3 s |

AgentExecutionBudget enforces the absolute deadline and records bounded stage observations. The orchestrator wraps structured extraction in the 20-second stage deadline in app/server/services/agent/orchestrator.py:698-792. ParserService declares a 35-second parser timeout in parser_service.py:56-71, but the orchestrator’s 20-second stage deadline wins in the observed live path.

### 7.2 Live termination

All 20 live requests terminated before the planner or native loop. There was therefore no live loop iteration, tool retry, duplicate-call decision, no-progress decision, or render retry to observe. The actual live state transition was:

~~~text
request accepted → context assembled → structured extraction
  ├─ effective unclear → policy rejection/clarification → persistence
  ├─ application deadline → bounded parser failure → persistence
  └─ parsed target → location resolution → unresolved-country clarification → persistence
~~~

### 7.3 Static native-loop safeguards

app/server/services/agent/native_tool_loop.py:39-69 defines bounded safeguards: maximum eight iterations, six model calls, twelve tool calls, sixteen state transitions, a 180-second loop budget, and a no-progress limit of two. Duplicate call fingerprints and repeated no-progress states terminate the loop. Tool results are bounded to 12,000 characters and individual tool calls have a 30-second timeout.

ToolPlanExecutor in app/server/services/agent/tool_plan_executor.py:116-314 retries eligible steps within the shared budget, applies per-step limits, and validates tool output. These safeguards are good containment, but they cannot help when parsing ends the run before the plan exists.

The parser can attempt schema correction/provider-failure retry only while budget remains (parser_service.py:1604-1635). The orchestrator does not restart the full workflow after a parser-stage deadline; that is appropriate for bounded execution, but it means provider latency and parser contract quality are release-critical.

## 8. Prompt and structured-schema audit

The structured interpreter prompt in app/server/prompts/parser.py:8-72 correctly instructs the provider to preserve compound actions, explicit locations, hierarchy, relationships, and temporal semantics, and to return structured JSON rather than an answer. The problem is not an absent instruction alone.

LLMParserExtraction in app/server/domain/agent/extraction_schemas.py:201-269 gives permissive defaults:

- task_class defaults to unclear.
- action_id defaults to unknown.
- requires_location defaults to true.
- parser confidence defaults to 0.5.
- list fields default to empty arrays.
- presentation mode defaults to map.

This makes a sparse JSON object technically valid while still being operationally unusable. The current contract does not expose a required-field completeness score or distinguish:

1. an intentional user ambiguity,
2. a provider response that omitted required semantic fields,
3. a provider response that was truncated or structurally degraded, and
4. an application-generated default.

The parser’s provider-error path intentionally refuses to infer a location/action/map from a failed provider call (parser_service.py:1023-1108). That safety behavior is correct, but the effective-unclear path is not classified as a provider-contract failure, so it falls into the generic policy question.

The provider integration sends a JSON-object request and validates the result with Pydantic. deepseek_provider.py:438-628 embeds the schema instruction and validates the returned JSON. opencode_provider.py:369-384 routes the structured request through the OpenAI-compatible chat-completions protocol. The live model catalogue declares structured-output support, but the observed behavior demonstrates that capability metadata is insufficient to prove semantic contract reliability.

## 9. Policy and clarification audit

The policy engine has explicit checks:

- app/server/services/agent/policy_engine.py:280-289 rejects an unknown task class with the reason Task class is unclear.
- policy_engine.py:292-322 handles missing or deictic locations.
- policy_engine.py:325-383 handles semantic ambiguity and allows resolver-backed hierarchy signals.
- orchestrator.py:1012-1084 includes intentional ambiguity rules for missing thresholds/top-N, distance, recent time windows, and flood comparisons.

The detailed Show Rome on a map response contained the following decision shape:

~~~text
state: reject
action_id: unknown
clarification: generic map-search/direct-answer question
reason: Task class is unclear
missing_fields: ["task"]
trace: ["1.validate_task_class"]
~~~

This is a policy-valid response to an unclear parser contract, but it is not a valid interpretation of the user’s explicit “show ... on a map” instruction. The policy engine is acting as designed; the upstream parser/provider contract is feeding it the wrong state.

The clarification surface should be made field-specific. For example:

- Show recent earthquakes in Japan should produce a time-window question only if no documented recent default exists.
- Show the strongest earthquakes in Japan should produce a threshold/top-N question only if no documented default exists.
- Show nearby airports should ask for an anchor location.
- Italy should ask what operation the user wants.

The generic map-search/direct-answer question is acceptable only for genuinely presentation-ambiguous requests such as Where is Rome?, and even there it should be driven by a successfully parsed location rather than by task_class=unclear.

## 10. Capability, planner, and tool-loop audit

The deterministic planner in app/server/services/agent/tool_planner.py:18-135 maps canonical interpretations to exact capability IDs and creates one step per canonical target. _target_specs in tool_planner.py:139-175 prevents a peer target from inheriting the primary point. This is important for the compound capitals case.

The native tool catalog has five geospatial tools, while the API’s direct-tool catalogue has four separate direct operations. The separation is intentional, but both surfaces need contract tests that assert the same canonical target and scope semantics.

The planner and executor implement:

- dependency-aware parallel groups;
- bounded retries;
- capability/result-status validation;
- geometry and target validation;
- scope and temporal validation;
- required renderable-geometry checks.

No live request reached these components, so their current production behavior is not proven by the live matrix. The controlled and focused unit suites cover the failure and acknowledgement contracts, not live provider semantic reliability.

## 11. Geospatial resolution and data-access audit

LocationResolver uses explicit signals, reference data, and Nominatim. It has special handling for city administrative boundaries in location_resolver.py:634-649, but the country branch in location_resolver.py:728-731 requires result_type=country.

The live log recorded:

~~~text
Rejecting geocoder candidate that does not match target=Iceland
  type=administrative display=Iceland
Rejecting geocoder candidate that does not match target=Japan
  type=administrative display=Japan
~~~

The returned candidate display names exactly matched the requested countries, but the strict type check rejected them. This is a deterministic false negative rather than an absence of a country signal or a provider outage.

### Root cause chain for rows 8 and 10

~~~text
explicit country in user request
  → parser supplies a country location signal
  → Nominatim returns matching display name with administrative type
  → country resolver requires exact country type
  → candidate rejected
  → no ResolvedLocation
  → safe location clarification
~~~

The resolver should accept a verified country administrative candidate when its country code/name and requested-target match are strong enough, while retaining protection against similarly named regions. This should be implemented only with tests for country, region, city, and ambiguous names; no implementation change was made during this audit.

## 12. Map assembly, persistence, and render-ack contract

The orchestrator builds map overlays from verified tool results in app/server/services/agent/orchestrator.py:1315-1475. Provider failures do not create successful empty layers. Metadata-only products may complete without browser acknowledgement; renderable overlays require it.

AgentRunOrchestrator persists a candidate as awaiting_render and publishes map_prepared in app/server/services/agent_runs/orchestrator.py:292-365. RenderCompletionService validates the map/session/revision and decides whether browser acknowledgement is required (app/server/services/agent_runs/render_completion.py:58-172).

agent_runs.py:319-626 uses an immediate SQLite transaction to validate the run, conversation, session, revision, required overlays, viewport bounds, source/layer evidence, and completion requirements before promoting the candidate. This is a sound single-commit boundary.

Two static issues require focused follow-up:

1. agent_runs.py:401-409 comments describe a stable capability-ID alias, but the fallback comparison appears to compare candidate.overlay_id to the same overlay ID again. The capability-ID branch therefore appears unreachable.
2. The frontend evidence in map-preview.component.ts:1252-1333 treats layer_present as including visibility. The backend can select all non-metadata instances as required overlays. If users intentionally hide a valid overlay before acknowledgement, a valid render may fail its evidence check. This is a static risk, not a live failure observed in this audit.

## 13. Controlled renderer and browser evidence

The controlled test was:

~~~text
app/tests/e2e/test_agentic_map_completion.py
result: 1 passed in 4.96 s
~~~

External report:

C:\Users\Thomas V\.codex\visualizations\2026\09\08\01a080a2-1cc7-7d20-815f-f7d137dc1534\controlled-e2e\reports\controlled-map-completion.json

Recorded controlled evidence:

| Evidence | Value |
|---|---|
| Scenario | recent earthquakes around Rome |
| Run | controlled-map-run-1 |
| Map session | rome-earthquake-session |
| Collection revision | 7 |
| Acknowledgement | ready |
| Viewport bounds | [12.276163154800713, 41.78872434628582, 12.72383684520139, 42.01123841234292] |
| Required sources loaded | true |
| Layers present | true |
| Viewport valid | true |
| Overlay | earthquake-rome-1 |
| Source/layer/loaded/style/zoom valid | all true |
| Rendered feature count | 1 |
| Canvas | 888 × 593 |
| Console errors | none |

The screenshot at:

C:\Users\Thomas V\.codex\visualizations\2026\09\08\01a080a2-1cc7-7d20-815f-f7d137dc1534\controlled-e2e\screenshots\test_agentic_map_completion.py__test_controlled_map_completion_requires_and_records_visible_rendering[chromium]\controlled-map-completed.png

showed the actual AEGIS UI, MapLibre canvas, OpenStreetMap fixture tile, one red earthquake point, the visible layer panel, “Map ready.”, header “Rome, Italy”, and status “Verified”.

This proves the render path under deterministic fixture inputs. It does not prove live provider retrieval, live parser semantics, or production geocoder availability.

## 14. Frontend and realtime UX audit

The existing Chrome tab was tested at http://127.0.0.1:4512/. A new chat was started and the exact input Show a map of Italy was sent.

Live browser result:

- user message displayed;
- assistant displayed Can you clarify whether you want a map search or a direct answer?;
- map canvas remained empty with Ask for a location or map data to load the workspace.;
- header remained ready for a location/data request;
- model status showed Needs attention;
- browser console error/warning query returned no entries.

The frontend realtime service has sensible safeguards in app/client/src/app/core/realtime.service.ts:162-253: WebSocket subprotocol negotiation, session resume, one-send-per-generation protection, acknowledgement timeout, and reconnect handling. The geospatial page filters stale/duplicate events and validates map session/presentation/revision identity in geospatial-page.component.ts:887-1042.

The visible UX is therefore consistent with the backend result: it correctly shows no map when no map session is prepared. The main UX defect is the misleading generic clarification for explicit map requests; the browser had no render failure to report.

## 15. Failure-injection and test evidence

No source-level failure injection or test modification was introduced. Existing focused failure-path and render-contract tests were executed:

~~~text
app/tests/unit/services/test_render_completion.py
app/tests/unit/services/test_agent_runs.py
app/tests/unit/services/agent/test_native_tool_loop.py
app/tests/unit/services/agent/test_orchestrator_messages.py
app/tests/unit/test_agentic_geospatial_map_session.py
app/tests/unit/test_geospatial_provider_hardening.py
app/tests/unit/test_geospatial_api_contracts.py
app/tests/unit/test_provider_registry.py

110 passed, 2 warnings in 81.54 s
~~~

The broader focused services/API suite passed:

~~~text
398 passed, 2 warnings in 11.58 s
~~~

The first sandboxed attempt showed 45 failures caused by permission errors reading the installed tzdata package and protected pytest cache paths, not by application assertions. The same suite passed when run with the required elevated test environment. The two warnings were an upstream Google GenAI deprecation warning and a Starlette/httpx deprecation warning.

The controlled E2E pass and the focused failure-path pass establish a healthy deterministic test lane. They do not contradict the live matrix: they exercise different providers/fixtures and different evidence boundaries.

## 16. Observability and diagnostic quality

Current logs record useful stage names, durations, remaining budget, timeout origin, request IDs, and run IDs. They do not expose enough safe semantic telemetry to answer why a structured extraction was accepted as a successful-but-unusable unclear result.

Observed diagnostic gaps:

- structured_intent_extraction success can be logged even when the persisted task kind is unclear;
- the normalized parser contract is not summarized at the stage boundary with required-field completeness, raw-field presence, or default-field counts;
- the live response did not provide the provider response category that would distinguish sparse JSON from an explicit ambiguity;
- the model catalogue’s reachable=null state does not indicate whether a structured completion probe has passed;
- there was no compact per-request event showing parser → policy → resolver → planner → tool → map reachability; this had to be reconstructed from logs and conversation snapshots;
- no live tool invocation means provider/data-access health cannot be inferred from these request outcomes.

Recommended safe telemetry fields:

~~~text
parser_contract:
  provider
  model
  protocol
  response_parse_status
  task_class
  action_id
  location_signal_count
  required_field_presence
  defaulted_field_count
  parser_confidence
  provider_error_category
  stage_duration_ms
  timeout_origin
pipeline_reach:
  context
  parse
  policy
  resolve
  plan
  tool
  map_prepare
  render_ack
~~~

Do not log raw credentials or unrestricted provider payloads. Hash or redact user content and retain only the semantic fields needed to diagnose contract quality.

## 17. Root-cause chains

### 17.1 Primary live failure

~~~text
configured provider/model declares structured-output support
  → parser requests JSON object through OpenAI-compatible transport
  → returned contract is either slow or sparse/default-valid
  → sparse/default-valid output retains task_class=unclear/action_id=unknown
  → policy rejects with generic map-search/direct-answer question
  → explicit map request never reaches location resolution/planning
~~~

### 17.2 Deadline failure

~~~text
20-second orchestrator extraction stage limit
  → provider response/transport does not complete within the stage
  → application_deadline_exceeded / provider_timeout classification
  → no full-workflow restart because absolute budget is nearly exhausted
  → safe bounded diagnostic
  → no location/action inference, tool call, or map
~~~

### 17.3 Country-resolution failure

~~~text
country signal is present
  → geocoder returns matching country display with administrative result type
  → resolver requires exact country result type
  → valid candidate rejected
  → explicit country becomes unresolved
  → user is asked for a country that was already supplied
~~~

### 17.4 Render path separation

~~~text
controlled canonical result
  → candidate overlay collection
  → MapLibre source/layer/viewport evidence
  → matching render acknowledgement
  → atomic ready promotion
  → visible verified map
~~~

The fourth chain is passing under controlled evidence and is not the cause of the first three.

## 18. Findings register

| ID | Priority | Finding | Evidence | User impact | Confidence |
|---|---|---|---|---|---|
| F-01 | P0 | Live parser/provider contract is not reliable for ordinary requests. | L: 13 unclear/rejection rows; 5 extraction deadlines; 0 tools/maps. S: parser defaults and 20 s stage budget. | Core geospatial workflow unavailable with configured provider. | High |
| F-02 | P1 | Sparse/default-valid structured output is not distinguished from intentional ambiguity. | L: detailed trace task_class=unclear, action_id=unknown; S: extraction schema defaults. | Wrong generic clarification and loss of explicit user intent. | High |
| F-03 | P1 | Parser stage deadlines are reached for common prompts. | L: five application_deadline traces at approximately 20 s. S: orchestrator budget. | Requests fail without a recoverable structured result. | High |
| F-04 | P1 | Country resolver rejects matching administrative candidates. | L: exact Iceland/Japan log warnings; S: location_resolver.py:728-731. | Country-scoped requests ask for already supplied locations. | High |
| F-05 | P2 | Direct chat route has an HTTP 500 missing-conversation path. | L: nonexistent ID reproduced; S: api/chat.py:87-98. | API clients receive an internal error instead of a contract error. | High |
| F-06 | P2 | Documented capability alias acknowledgement branch appears unreachable. | S: agent_runs.py:401-409. | Valid overlay evidence may fail identity validation. | Medium |
| F-07 | P2 | Hidden-overlay/render-evidence semantics may disagree. | S: frontend layer_present checks and backend required-overlay selection. | Valid intentional visibility changes may block readiness. | Medium; targeted test required |
| F-08 | P2 | Model catalogue health lacks completion-path reachability. | L: ok=true, reachable=null. | Operators may believe the selected model is healthy when parsing is not. | High |
| F-09 | P3 | Existing upstream deprecation warnings remain. | S/L: focused test output. | Future maintenance noise; not current map blocker. | High |

## 19. Remediation order

1. Restore a reliable parser contract for the selected provider. Add a structured-completion canary and provider-specific contract diagnostics. Treat sparse/default-only responses as a parser contract failure or a clearly labelled ambiguity, not as an ordinary successful parse.
2. Make extraction completeness explicit. Require or validate the semantic minimum for each task class and preserve field-presence/default metadata. Keep the no-heuristic behavior for true provider failures, but do not let defaults hide provider degradation.
3. Improve bounded latency behavior. Measure provider extraction latency, decide whether the 20-second stage budget is appropriate for the configured provider, and add a narrowly scoped parser retry/fallback policy that does not silently substitute a different model/provider. Preserve the bounded deadline and diagnostic response.
4. Fix country candidate matching conservatively. Accept strong country-code/name matches returned as administrative while retaining ambiguity safeguards. Add country/region/city regression coverage.
5. Replace generic clarification with targeted clarification. Use the missing semantic field to ask about time window, threshold/top-N, radius anchor, presentation, or requested operation.
6. Add pipeline reachability telemetry. Record normalized semantic fields, defaulting, provider error category, and the last reached stage without logging sensitive content.
7. Repair and test render identity semantics. Correct the capability-ID alias comparison and explicitly define whether visibility is required for layer present versus layer loaded.
8. Normalize the direct API precondition. Return a typed 4xx response for a missing conversation or document and test the required create-then-turn sequence.
9. Add a live-provider release gate. A controlled fixture pass is necessary but insufficient; the selected provider/model must pass a small semantic canary covering map, point, boundary, compound target, radius, and temporal requests.

## 20. Regression-test plan

The following tests should be added or strengthened before claiming the live path is repaired:

### Parser/provider contract

- Show a map of Italy returns task_class=map_search, a country location signal, and an execution-ready action.
- Show Rome and Map Zurich do not return task_class=unclear.
- Coordinate-only prompts promote to a map/point task when the user uses show, point, or equivalent map language.
- Sparse JSON containing only schema defaults is classified as contract-incomplete and is observable as such.
- Structured provider timeout returns the bounded diagnostic and does not restart the entire workflow indefinitely.
- A valid provider response with compound capitals preserves all three targets.

### Clarification semantics

- Italy requests a targeted operation clarification.
- Show recent earthquakes in Japan requests a time window only when the product has no documented recent default.
- Show the strongest earthquakes in Japan requests threshold/top-N only when no default exists.
- Show nearby airports requests an anchor location.
- Where is Rome? asks only the documented presentation question, with Rome already parsed.

### Location resolver

- Country candidate with exact country code and result_type=country succeeds.
- Country candidate with exact country code/name and result_type=administrative succeeds when the match is unambiguous.
- A similarly named administrative region does not incorrectly resolve as the requested country.
- France, Germany, Italy, Iceland, Japan, and Switzerland all resolve through the same country contract.

### Planner and tool execution

- One canonical target is mapped to one plan step.
- Compound targets do not inherit the primary target’s point or scope.
- Radius, temporal, relational, and boundary semantics survive planning.
- Provider/data failure never becomes a successful empty overlay.
- Duplicate/no-progress loops terminate within configured bounds.

### Render and persistence

- Required overlay capability aliases are accepted by the acknowledgement validator.
- An intentionally hidden but loaded overlay follows one explicit policy: either hidden is valid evidence or it is excluded from the required set.
- Stale map session, stale presentation ID, stale collection revision, missing viewport bounds, and missing source/layer evidence are rejected.
- Matching map.render_ack atomically promotes the candidate and publishes durable completion.
- Browser reload/resume does not duplicate acknowledgement or regress a ready map.

### Live canary

Run the 20-row matrix, or a reduced release gate containing at least:

Show a map of Italy; Show Rome; Show the boundary of Switzerland; Show 46.9480, 7.4474; Show airports in Switzerland; Show the capitals of France, Germany, and Italy; Show airports within 100 km of Zurich; Show recent earthquakes in Japan; Show the area and points and bounds for Switzerland.

The gate must assert not only HTTP success but:

parsed task → resolved target → planned capability → tool result → map_prepared → browser render_ack → visible map.

## 21. Audit conclusion and cleanup record

At the audited commit, the AEGIS renderer, WebSocket protocol, candidate-map state, and atomic render acknowledgement are healthy under controlled evidence. The configured live provider/parser path is the release blocker: it fails explicit requests through an effective-unclear contract, bounded extraction deadlines, or strict country resolution before any geospatial capability runs.

No application code, configuration, prompt, schema, dependency, test, or existing repository file was changed. The following audit-created runtime state was removed after evidence collection:

- 24 audit-created conversations;
- 48 audit-created chat messages;
- 15 audit-created realtime events;
- one audit-created agent run;
- one migration-backup file created by audit backend startup.

The audit-started backend on port 7059 was stopped. The frontend on port 4512 was already running before the audit and was left running; it belongs to the existing user session.

The only repository artifact created by this investigation is AGENTIC_PIPELINE_AUDIT.md.

Overall decision: FAIL for live end-to-end agentic map readiness; PASS for the controlled render/acknowledgement path; remediation required before production confidence.

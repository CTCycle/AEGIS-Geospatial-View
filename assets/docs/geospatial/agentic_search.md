# Agentic Search

Last updated: 2026-07-11

## Summary

The chat workflow separates structured parsing from provider-native tool calling:

1. `ParserService` emits evidence-oriented `TurnParseResult`, including prompt relationship, entity/layer targets, basemap changes, ambiguities, and frontend update type.
2. A durable conversation task ledger records the supervised task and follow-up relationship.
3. Semantic layer concepts are resolved against enabled manifest metadata before planning.
4. Deterministic routing selects a narrow specialist group.
5. A typed tool plan fixes capability IDs, arguments, dependencies, timeouts, retries, validation, and merge behavior before execution.
6. `PolicyEngine` restricts both tool names and executable capability IDs.
7. Known capabilities execute through `ToolPlanExecutor`; catalog discovery uses the bounded native tool loop.
8. Verified results update the map, task status, and structured diagnostics.
9. The configured agent model converts only those verified results into concise Markdown, with deterministic text retained as fallback.

Residential-building requests use `overpass_residential_buildings`; amenities
remain separate. Satellite language selects the imagery basemap unless the user
explicitly requests an imagery data layer.

No legacy routing compatibility is preserved.

## Conversation Context

`conversation_id` isolates history, directives, tasks, map memory, summaries, and
tool outcomes. Explicit durable instructions enter a structured directive ledger;
later conflicts supersede earlier directives. Context is rebuilt for the selected
model using declared input/output limits, schema overhead, and safety margin.

## Parser Contract

`TurnParseResult` contains:

- user text and bounded context
- task class
- location signals
- normalized action
- temporal signal
- ambiguities
- disallowed patterns
- parser confidence
- task relationship and atomic tasks
- map/entity targets, requested layers, basemap, and attributes
- tool requirement/category and expected frontend update
- capability limitations and parser-recursion signal
- an optional generic clarification plan describing blocking fields, choices, and whether valid visualization changes may be applied before clarification

It does not contain provider-specific tool schemas, concrete executable tool names, or final map payloads.

## Capability Resolution

Parser output may contain semantic concepts such as `precipitation`; only
manifest IDs may enter an executable tool plan. Exact enabled IDs are preserved.
Semantic concepts are ranked against capability names, descriptions, keywords,
planner hints, rendering modes, and temporal compatibility.

Current radar requests prefer `rainviewer_precipitation_radar`, rainfall-rate
requests prefer `IMERG_Precipitation_Rate`, and forecast requests prefer
`openmeteo_weather_forecast`. Historical monthly precipitation means are not
available in the current catalog, so those requests produce a structured
clarification with supported current and forecast alternatives.

## Stable Action Catalog

Supported action values:

- `map_search`
- `location_render`
- `geospatial_data_retrieval`
- `data_layer_query`
- `overlay_control`
- `dataset_display`
- `visible_layer_interrogation`
- `map_external_source_combination`
- `chat_response`
- `unknown`

Unknown or low-confidence classifications normalize to `unknown` before policy selection.

## Native Geospatial Tools

- `list_geospatial_capabilities`
- `describe_geospatial_capability`
- `execute_geospatial_capability`
- `fetch_geospatial_provider_layers` for explicitly routed and provider-allowlisted discovery only

Catalog responses are deterministic, permission-aware, and capped at 50 items per page.

## Provider Boundary

Provider-neutral LLM tool contracts are translated by adapters for:

- OpenAI-compatible function tools
- Google Gemini function declarations
- Ollama chat tools

Provider-specific schemas do not leak into parser, policy, or executor models.

## Response Contract

`POST /api/chat/turn` returns a structured `ChatTurnResponse`.

Stable high-level fields:

- `assistant_message`
- `turn_contract`
- `decision`
- `operation`
- `tool_payload`
- `map_session`
- `memory_snapshot`
- `context_usage`

`operation` is the frontend-facing summary of verified backend outcome. It exists so clients do not need to infer success mode by inspecting `decision`, `tool_payload`, or `map_session`.

`operation.kind` values:

- `map_session`
- `direct_answer`
- `capability_catalog`
- `clarification`
- `rejection`
- `error`
- `failure_diagnostic`

`operation.status` values:

- `success`
- `partial`
- `failed`

Current behavior:

- successful map requests return `operation.kind = "map_session"` and a non-null `map_session`
- verified direct tool responses return `operation.kind = "direct_answer"` and may include `operation.direct_result`
- preflight clarification returns `operation.kind = "clarification"`
- policy denial returns `operation.kind = "rejection"`
- parser, provider, validation, and timeout failures return `operation.kind = "error"`

`tool_payload` remains available for raw tool trace and debugging, but it is not the primary source of truth for user-visible outcome.

`assistant_message` is Markdown-capable user-facing text. The response model is
grounded with the verified operation, map summary, direct result, warnings,
clarification requirements, and task state. It must not invent facts or expose
internal identifiers.

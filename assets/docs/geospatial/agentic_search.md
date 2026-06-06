# Agentic Search

Last updated: 2026-06-06

## Summary

The chat workflow separates structured parsing from provider-native tool calling:

1. `ParserService` emits evidence-oriented `TurnParseResult`.
2. `PolicyEngine` adds constraints, authorization checks, and audit metadata.
3. `AgentToolCatalogService` exposes stable geospatial catalog tools.
4. `NativeToolLoop` sends those tools to the selected provider through native tool-calling APIs.
5. The model decides exact tool names and arguments.
6. `ToolRegistry` executes exact emitted tool names and returns structured tool-result messages.
7. The loop continues until final text or a production limit is reached.

No legacy routing compatibility is preserved.

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

It does not contain provider-specific tool schemas, concrete executable tool names, or final map payloads.

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

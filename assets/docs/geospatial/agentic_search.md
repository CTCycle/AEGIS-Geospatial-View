# Agentic Search

Last updated: 2026-06-02

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

Agent responses expose:

- `action`
- `action_label`
- `action_confidence`
- `tool_calls`
- `map_operations`
- `message`

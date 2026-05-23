# Agentic Search

Last updated: 2026-05-23

## Summary

The chat workflow is action-first and tool-native:

1. Parser emits evidence-only `TurnParseResult` with `normalized_action`.
2. `ActionRouter` validates the action against `ACTION_CATALOG`.
3. `ToolManifestService` selects a focused provider-neutral tool set.
4. LLM providers receive those tools through their native tool-calling APIs.
5. `AgentToolExecutor` runs approved calls and returns structured map operations.
6. Internal service roles render location state, resolve overlays, combine map data, and produce the final chat response.

No legacy routing compatibility is preserved.

## Turn Contract

Parser output is `TurnParseResult` and contains only:

- user text and bounded conversation context
- task class (`map_search | direct_query | general_question | unclear`)
- location signals
- normalized action
- temporal signal
- ambiguities
- disallowed patterns
- parser confidence

Parser output never contains provider-specific tool schemas, overlay execution directives, or final map operation payloads.

## Action Catalog

The stable action catalog lives in `app/server/domain/agent/actions.py`.

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

Each action definition declares its user-facing label, description, tool groups, map-context requirement, and whether external sources are allowed. Unknown or low-confidence parser classifications are normalized to `unknown` before policy selection.

## Tool Manifest

Provider-neutral tools are defined by `AgentToolDefinition` in `app/server/domain/agent/tools.py` and selected by `ToolManifestService`.

Base tools:

- `search_maps`
- `resolve_location`
- `retrieve_geospatial_data`
- `query_data_layer_api`
- `load_map_overlay`
- `toggle_map_overlay`
- `display_dataset_on_map`
- `interrogate_visible_layers`
- `combine_map_data_with_external_sources`

Tool definitions include a JSON Schema parameters contract, action scope, map-context requirement, and optional source manifest or capability IDs.

## Provider-Native Tool Calling

The shared LLM boundary exposes provider-neutral `LLMToolDefinition`, `LLMToolCall`, and `LLMToolResult` types. Provider adapters translate those into native schemas:

- OpenAI function tools and structured output schema.
- Google Gemini function declarations and tool configuration.
- Ollama chat tools and structured output format.

Provider-specific schemas do not leak into parser, policy, or executor models.

## Overlay Tools

Overlay-specific tools are generated from `CapabilityRegistry`. Names are deterministic:

```text
overlay__{safe_capability_id}
```

Overlay tool definitions retain `source_manifest_id` and `source_capability_id`, and resolve back through the registry at execution time. They are scoped to overlay control, dataset display, data-layer query, or visible-layer interrogation actions.

## Action-Aware Tool Selection

`ToolManifestService.select_tools(...)` enforces deterministic limits:

- maximum 12 active tools per provider call
- location resolver included for map search, location rendering, and unresolved map requests
- no more than 4 overlay-specific tools for non-overlay actions
- visible layers preferred when layer IDs are present
- topic-matching capability names and tags preferred
- external-source tools excluded unless the action is `map_external_source_combination`

Requests to show every possible layer should be refused as indiscriminate loading and answered with a concise category offer.

## Internal Agent Roles

The pipeline uses internal service roles, not user-facing bots:

- `ChatAgent`: final user-facing response only.
- `ActionRouter`: action classification validation and focused tool selection.
- `LocationRenderAgent`: location resolution and map viewport operations.
- `OverlayResolutionAgent`: overlay, layer, and dataset operations.
- `MapDataFusionAgent`: visible map data plus permitted external sources.

## Execution Pipeline

`AgentPipeline.run(...)` executes:

1. Parse the user message into `NormalizedAction`.
2. Route through `ActionRouter`.
3. Select focused tools through `ToolManifestService`.
4. Invoke provider-native tool calling.
5. Execute returned calls through `AgentToolExecutor`.
6. Delegate location-heavy work to `LocationRenderAgent`.
7. Delegate overlay-heavy work to `OverlayResolutionAgent`.
8. Delegate external-source combination to `MapDataFusionAgent`.
9. Pass final structured state to `ChatAgent`.
10. Return chat text plus frontend-actionable map operations.

Safety limits:

- maximum provider tool-calling rounds: 4
- maximum active tools per provider call: 12
- unknown tool names are rejected
- map-rendering tools return structured payloads, not free text

## API Contracts

Agent responses expose:

- `action`
- `action_label`
- `action_confidence`
- `tools_considered`
- `tools_selected`
- `tool_calls`
- `map_operations`
- `message`

Map operation payloads are frontend-actionable and may include viewport, center, bbox, zoom, layer ID, dataset ID, overlay ID, visibility, opacity, legend, and source attribution.

## Extensibility Rules

To add capabilities, update manifests and runtime profiles first.

- Basemap/overlay: add manifest + runtime profile entry.
- Direct tool: add tool manifest + runtime profile entry + handler module.
- Agent-visible overlay operations are generated from the manifest registry.

Core parser, provider abstraction, and executor code should not need edits for additive capabilities unless a new action or base tool is introduced.

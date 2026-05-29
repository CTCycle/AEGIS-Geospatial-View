# Agentic Search

Last updated: 2026-05-24

## Summary

The chat workflow separates structured parsing from provider-native tool calling:

1. Parser emits evidence-only `TurnParseResult` for request extraction.
2. Policy builds constraints, authorization checks, confirmation requirements, and audit metadata.
3. `AgentToolCatalogService` exposes stable catalog, describe, and execute tools.
4. `NativeToolLoop` sends those tools to the selected provider through native tool-calling APIs.
5. The model alone decides exact tool names and arguments.
6. `ToolRegistry` executes exact emitted tool names and returns provider-native tool-result messages.
7. The loop continues until the model returns final text or a production limit is reached.

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

Parser output never contains provider-specific tool schemas, concrete tool names, action IDs selected for execution, overlay execution directives, or final map operation payloads.

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

## Native Catalog Tools

Agent-visible geospatial manifests are exposed through a small stable native tool set:

- `list_geospatial_capabilities`: paginated, filterable compact catalog metadata.
- `describe_geospatial_capability`: full descriptor and executable JSON schema for one stable capability ID.
- `execute_geospatial_capability`: schema-validated execution by stable capability ID.

The catalog page size is capped at 50. Catalog and describe responses are deterministic and permission-aware.

## Provider-Native Tool Calling

The shared LLM boundary exposes provider-neutral `LLMToolDefinition`, `LLMToolCall`, and `LLMToolResult` types. Provider adapters translate those into native schemas:

- OpenAI function tools and structured output schema.
- Google Gemini function declarations and tool configuration.
- Ollama chat tools and structured output format.

Provider-specific schemas do not leak into parser, policy, or executor models.

## Manifest Exposure

Capability manifests remain the source of truth for overlays, layers, datasets, and geospatial operations, but manifest vectorization is not used to decide which tools the agent may see or call. The agent sees the stable catalog tools, discovers capabilities by catalog/describe calls, and executes by stable capability ID.

## Internal Agent Services

The pipeline uses internal services, not user-facing bots:

- `ParserService`: structured extraction only.
- `PolicyEngine`: constraints, authorization, validation, and clarification/rejection checks.
- `AgentToolCatalogService`: stable catalog, describe, and execute tools.
- `NativeToolLoop`: provider-native multi-turn tool loop.
- `ToolRegistry`: exact-name tool resolution, schema validation, and execution envelopes.

## Execution Pipeline

`NativeToolLoop.run(...)` executes:

1. Send conversation, constraints, and stable native tools to the provider.
2. If the provider returns tool calls, validate exact tool names and arguments.
3. Execute allowed tools through `ToolRegistry`.
4. Append assistant tool-call and tool-result messages using provider-native roles.
5. Repeat until final text or a limit is reached.

Safety limits:

- maximum provider tool-calling rounds: 8
- maximum parallel tool calls per round: 8
- maximum tool-result payload before deterministic truncation: 12000 characters
- tool timeout: 30 seconds
- unknown tool names are rejected
- tools return structured envelopes, not free text

## API Contracts

Agent responses expose:

- `action`
- `action_label`
- `action_confidence`
- `tool_calls`
- `map_operations`
- `message`

Map operation payloads are frontend-actionable and may include viewport, center, bbox, zoom, layer ID, dataset ID, overlay ID, visibility, opacity, legend, and source attribution.

## Extensibility Rules

To add capabilities, update manifests and runtime profiles first.

- Basemap/overlay: add manifest + runtime profile entry.
- Direct tool: add tool manifest + runtime profile entry + handler module.
- Agent-visible manifest operations are discovered through catalog, describe, and execute native tools.

Core parser, provider abstraction, and executor code should not need edits for additive capabilities unless a new stable native tool category is introduced.

# Agentic Search

Last updated: 2026-05-11

## Summary

The chat workflow is now contract-first and deterministic:

1. Parser emits evidence-only `TurnParseResult`.
2. Policy engine builds a strict `PolicyDecision` + `ExecutionPlan`.
3. Orchestrator executes only the approved plan state (`clarify`, `direct_tool`, `map_search`, `reject`).
4. Turn payloads and location memory snapshots are persisted as structured JSON.

No legacy routing compatibility is preserved.

## Turn Contract

Parser output is `TurnParseResult` and contains only:
- user text and bounded conversation context
- task class (`map_search | direct_query | general_question | unclear`)
- location signals
- normalized intent
- temporal signal
- ambiguities
- disallowed patterns
- parser confidence

Parser output never contains tool IDs, overlay IDs, or execution directives.

## Policy Engine Order

Decisioning order is fixed and must not be reordered:

1. validate task class
2. enforce location requirement
3. resolve location
4. validate ambiguity
5. retrieve capabilities
6. filter runtime availability
7. filter coverage
8. choose execution mode
9. build execution plan

The policy engine is the only authority that decides execution mode.

## Execution Modes

`ExecutionPlan.state` can be only:
- `clarify`
- `direct_tool`
- `map_search`
- `reject`

### `direct_tool`

- Tool is resolved from manifest-backed capability + runtime registries.
- Tool execution is handled through `ToolRegistry` and handler bindings.

### `map_search`

- `RequestBuilder` converts plan + resolved location into `LocationSearchRequest`.
- Search orchestrator executes only explicit `basemap_id` + `overlay_ids`.
- No inferred overlay selection from legacy semantic filters.

## Capability Retrieval

Retrieval is two-stage:

1. semantic retrieval against manifest embeddings
2. deterministic reranking (`intent`, `temporal`, `runtime`, `coverage`)

Searchable kinds include basemaps, overlays, and tools from the same manifest source.

## Geographic Intelligence Selection

Geographic sources are agentic capabilities, not passive layers. The policy engine and manifest intent resolver select basemaps, overlays, camera networks, search indexes, and analysis tools only when the user request benefits from them.

Selection rules:

- General factual chat does not load map capabilities.
- Location, nearby, route, show, overlay, live, current, camera, traffic, flood, fire, weather, demographic, amenity, or visual-confirmation requests can select geospatial capabilities.
- Webcam and camera requests select `camera-network` capabilities such as `windy_webcams`.
- Amenity requests select POI/search-index capabilities, not every available geographic layer.
- Missing credentials do not crash the turn; the runtime returns access-needed state and should prefer public alternatives where possible.
- Broken or metadata-only capabilities are not exposed as normal renderable toggles.

## Runtime and Coverage

Runtime availability is driven by `runtime_profiles.json` + current credentials:
- enabled/disabled
- mode support (`supports_map`, `supports_direct_text`)
- health and credential status

Coverage filtering is explicit and supports:
- `global`
- `global-partial`
- `eu-eea`
- `global-except-poles`

## Location Memory

Location context is stored as slot-based memory snapshot in persisted structured payloads.

Services:
- `build_memory_snapshot`
- `resolve_explicit_references`
- `update_memory_snapshot`

This memory is consumed by parser/policy and returned as `memory_snapshot` in `ChatTurnResponse`.

## API Contracts

`POST /api/chat/turn` returns `ChatTurnResponse` with:
- `assistant_message`
- `turn_contract`
- `decision`
- `tool_payload`
- `map_session`
- `memory_snapshot`

`POST /api/maps/search` accepts strict `LocationSearchRequest` only.

## Extensibility Rules

To add capabilities, update manifests and runtime profiles first.

- Basemap/overlay: add manifest + runtime profile entry.
- Direct tool: add tool manifest + runtime profile entry + handler module.

Core parser/policy/orchestrator code should not need edits for additive capabilities.

# Agentic Search

Last updated: 2026-04-10

## Summary

AEGIS uses a chat-first flow where each user turn can either:
- execute geospatial search and update map session, or
- return a follow-up question when required input is materially ambiguous.

## Key Behaviors

- Datetime default:
  - when omitted, backend defaults to current UTC timestamp.
  - if temporal specificity is materially ambiguous, assistant returns follow-up instead of executing.
- Ollama runtime:
  - external service only; no automatic startup.
  - settings expose URL validation, health, refresh, and pull.
- Catalog source of truth:
  - provider/basemap/overlay metadata is loaded from JSON manifests in `AEGIS/resources/manifests`.
- Vector retrieval:
  - vector index bootstrap runs at backend startup when `vectors.auto_sync_on_start=true`.
  - bootstrap runs once when artifacts are missing and is skipped when both collection and metadata are valid.
  - similarity retrieval uses the raw user prompt text.
  - manual rebuild is exposed at `POST /api/chat/vectors/rebuild`.
  - incremental sync is exposed at `POST /api/chat/vectors/sync`.
- Direct coordinates tool:
  - explicit coordinate-lookup requests route to direct geocoding.
  - geocoding responses return plain text coordinates and do not create `map_session`.
- Direct runtime tools:
  - location-scoped weather, air-quality forecast, and nearby POI requests can route to direct tools.
  - direct tool responses remain plain text and never expose internal tool IDs.
- Retrieval availability:
  - retrieved basemap/overlay candidates are annotated with runtime availability before decisioning.
  - keyed integrations trigger clarification only when required and no available alternative can satisfy the same intent.
- Runtime provider overlays:
  - `openmeteo_weather_forecast`, `openmeteo_air_quality_forecast`, `overpass_poi_amenities`, and `rainviewer_precipitation_radar` are normalized into `map_session.insights`.
  - each overlay in `map_session.overlays` includes a `runtime` block with freshness/availability and provider-safe error envelopes.
- Plain text response safety:
  - chat response payloads are sanitized before model generation.
  - assistant output is normalized to plain text and falls back to deterministic plain text when needed.
- Persistence:
  - provider/model settings persisted in database.
  - cloud credentials persisted encrypted at rest.
  - chat sessions/messages persisted in database (`chat_sessions`, `chat_messages`).
- Conversation memory:
  - parser/decision/response model calls receive bounded transcript context.
  - transcript depth is controlled by `chat.max_history_messages` in `AEGIS/settings/configurations.json`.
- Provider transport:
  - parser and response model invocation is routed through LangChain-backed provider adapters.
  - agent behavior, fallback logic, and map-search execution flow are unchanged.
- Location resolution:
  - structured location mapping no longer falls back to raw user text as `address`.
  - geocoding supports city/country-only input.
  - unresolved locations fail early with actionable 400 validation errors.

## Backend Flow

1. `POST /api/chat/turn` or `POST /api/chat/stream` receives user turn.
2. Agent orchestration loads bounded transcript context and extracts intent.
3. Vector retriever resolves candidates from the raw user message.
4. Candidate availability and tool descriptions are passed into decisioning.
5. Decision selects geocode/search/clarify without exposing internal IDs.
6. Intent mapper converts agent output to `LocationSearchRequest` shape for search mode.
7. Shared location-search orchestrator executes map pipeline reused by `/api/maps/search`.
8. Assistant response + structured payload + map session are persisted.

## Streaming Events

`/api/chat/stream` returns NDJSON events:
- `status`
- `assistant_delta`
- `tool_status`
- `final`
- `error`

# Agentic Search

Last updated: 2026-04-08

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
  - vector index is built on first use if missing.
  - manual rebuild is exposed at `POST /chat/vectors/rebuild`.
  - incremental sync is exposed at `POST /chat/vectors/sync`.
- Persistence:
  - provider/model settings persisted in database.
  - cloud credentials persisted encrypted at rest.
  - chat sessions/messages persisted in database (`chat_sessions`, `chat_messages`).
- Conversation memory:
  - parser/decision/response model calls receive bounded transcript context.
  - transcript depth is controlled by `chat.max_history_messages` in `AEGIS/settings/configurations.json`.
- Location resolution:
  - structured location mapping no longer falls back to raw user text as `address`.
  - geocoding supports city/country-only input.
  - unresolved locations fail early with actionable 400 validation errors.

## Backend Flow

1. `POST /chat/turn` or `POST /chat/stream` receives user turn.
2. Agent orchestration loads bounded transcript context and extracts intent.
3. Vector retriever resolves relevant layer IDs.
4. Intent mapper converts agent output to `LocationSearchRequest` shape.
5. Shared location-search orchestrator executes map pipeline reused by `/maps/search`.
6. Assistant response + structured payload + map session are persisted.

## Streaming Events

`/chat/stream` returns NDJSON events:
- `status`
- `assistant_delta`
- `tool_status`
- `final`
- `error`

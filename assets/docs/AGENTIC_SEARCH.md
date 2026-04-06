# Agentic Search

Last updated: 2026-04-06

## Summary

AEGIS now uses a chat-first flow where each user turn can either:
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
- Persistence:
  - provider/model settings persisted in database.
  - cloud credentials persisted encrypted at rest.
  - chat sessions/messages persisted in database (`chat_sessions`, `chat_messages`).
- Conversation memory:
  - every parser/decision/response model call now receives a bounded transcript context.
  - transcript depth is controlled by `chat.max_history_messages` in `AEGIS/settings/configurations.json`.
  - in-memory history buffering is used per process/session for recent turns, while DB remains source of truth.
- Location resolution:
  - structured location mapping no longer falls back to raw user text as `address`.
  - geocoding now supports city/country-only input (address can be empty).
  - unresolved locations fail early with actionable 400 validation error instead of generic map-extent failure.

## Backend Flow

1. `POST /chat/turn` or `POST /chat/stream` receives user turn.
2. Agent orchestration loads bounded prior transcript, then extracts structured intent.
3. Vector retriever resolves relevant layer IDs.
4. Intent mapper converts agent output to `LocationSearchRequest` shape.
5. Shared location-search orchestrator executes map pipeline reused by `/maps/search`.
6. Assistant response + structured payload + map session are persisted to chat history tables and in-process buffer.

## Streaming Events

`/chat/stream` returns NDJSON events:
- `status`
- `assistant_delta`
- `tool_status`
- `final`
- `error`

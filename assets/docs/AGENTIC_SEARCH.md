# Agentic Search

Last updated: 2026-04-03

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
  - chat sessions/messages persisted in database.

## Backend Flow

1. `POST /chat/turn` or `POST /chat/stream` receives user turn.
2. Agent orchestration extracts structured intent.
3. Vector retriever resolves relevant layer IDs.
4. Intent mapper converts agent output to `LocationSearchRequest` shape.
5. Shared location-search orchestrator executes map pipeline reused by `/maps/search`.
6. Assistant response + structured payload + map session are persisted to chat history tables.

## Streaming Events

`/chat/stream` returns NDJSON events:
- `status`
- `assistant_delta`
- `tool_status`
- `final`
- `error`

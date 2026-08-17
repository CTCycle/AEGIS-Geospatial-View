# Frontend Architecture

Last updated: 2026-08-17

## Route-Level Pages

- `GeospatialPageComponent` at `/`
  Main chat and map workspace.
- `CapabilitiesPageComponent` at `/geodata`
  Manifest-backed geodata catalog.
- `SettingsPageComponent` at `/settings`
  Model, provider, and credential management.
- `AccessConfigurationsPageComponent` at `/access-configurations`
  Optional geospatial provider credential management.

## Core Frontend Boundaries

- API client request execution: `app/client/src/app/core/api.ts`
- API response normalization and parsing: `app/client/src/app/core/api-parsers.ts`
- Realtime envelope, run-event, and terminal-payload parsing: `core/realtime-parsers.ts`
- Persisted app/view state: `core/app-state.ts` and store service
- Shared runtime guards: `core/type-guards.ts`
- Shared contracts: `core/types.ts`
- Error presentation: `core/user-facing-error.service.ts`
- Model selection and model list utilities: `core/model-selection.ts`
- Dynamic-provider narrowing and model-library merging: `core/model-library.ts`
- Selected agent readiness checks: `core/agent-readiness.service.ts`
- Credential settings update orchestration: `core/credential-settings.service.ts` and `core/chat-settings-update.ts`
- Map rendering surface: `components/map-preview.component.*` and `components/map-preview-rendering.ts`

## Agent Run Interaction

`GeospatialPageComponent` uses the conversations API for agent chat. The first message creates a conversation if needed, opens the versioned realtime WebSocket, and sends an idempotent `run.start` command. Additional composer submissions while the run is active are sent as `run.steer` updates and rendered as compact refinements rather than independent tasks.

`RealtimeService` owns the socket lifecycle, subprotocol negotiation, heartbeat,
stale-connection detection, full-jitter exponential backoff, and command replay.
`core/realtime-parsers.ts` validates the wire envelope, run-event discriminator,
sequence/version fields, visibility, and JSON payload boundary before the page
receives a message. The page persists the last durable event sequence and
ignores duplicate event IDs so reconnect replay can be applied without
duplicating assistant or progress output.

Clarification runs terminate with `clarification_needed`. The event may include a
partial validated map update, allowing a basemap or layer correction before the
user answers. Matching assistant/error messages are deduplicated.

The agent is presented as continuously ready for the chat session. Per-run
progress begins with request understanding and is separate from the persistent
availability state.

Run events are applied by type: progress labels update the activity indicator,
assistant completion updates the transcript, clarification-needed preserves any
partial map update, and completed payloads apply normalized operation, task,
memory, visualization, and context-revision state together. Invalid optional
terminal fields are ignored rather than replacing the last valid value.
Replayed event IDs are ignored after reconnect.

Assistant message strings are rendered as GitHub-style Markdown through the
shared chat-message component and Angular HTML sanitization. User messages
remain escaped plain text.

## Map Rendering

`MapPreviewComponent` renders only normalized `MapSession` payloads through MapLibre. It does not render embedded HTML map payloads. Raster overlays should prefer `overlay.render` descriptors from the backend, including WMS/WMTS time, format, CRS, style, and tile matrix metadata.

Basemap changes are prepared in candidate containers. A generation token and
destroyed guard dispose pending candidates and ignore late load/error or queued
callbacks, preserving the active last-known-good map when a replacement fails.

Provider-native layer discovery is rendered through the same normalized overlay
descriptor path as curated catalog capabilities. The frontend does not assemble
provider-specific WMS/WMTS requests or treat provider errors as successful map
layers.

## Component Patterns

Reusable component examples include:

- `map-preview.component.*`
- `chat-message.component.*`
- `settings-icon-action.component.*`
- `settings-modal-shell.component.*`
- `settings-api-key-field.component.*`
- `settings-warning-banner.component.ts` (attribute selector on the existing
  `<section>` host so settings warning markup and CSS remain stable)
- `selected-model-summary.component.*`
- `capability-status-list.component.*`

Settings uses card-level model selection for one selected agent model.

## Routing Rule

Unknown routes redirect to the workspace route.

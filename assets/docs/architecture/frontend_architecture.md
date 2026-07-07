# Frontend Architecture

Last updated: 2026-07-03

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
- Persisted app/view state: `core/app-state.ts` and store service
- Shared runtime guards: `core/type-guards.ts`
- Shared contracts: `core/types.ts`
- Error presentation: `core/user-facing-error.service.ts`
- Model selection and model list utilities: `core/model-selection.ts`
- Selected agent readiness checks: `core/agent-readiness.service.ts`
- Credential settings update orchestration: `core/credential-settings.service.ts` and `core/chat-settings-update.ts`
- Map rendering surface: `components/map-preview.component.*` and `components/map-preview-rendering.ts`

## Agent Run Interaction

`GeospatialPageComponent` uses the conversations API for agent chat. The first message creates a conversation if needed, creates one active run, and opens an `EventSource` stream. Additional composer submissions while the run is active are sent as steering updates and rendered as compact refinements rather than independent tasks.

The page tracks the last run event ID and ignores duplicate event IDs so reconnect replay can be applied without duplicating assistant or progress output.

Clarification runs terminate with `clarification_needed`. The event may include a
partial validated map update, allowing a basemap or layer correction before the
user answers. Matching assistant/error messages are deduplicated.

The agent is presented as continuously ready for the chat session. Per-run
progress begins with request understanding and is separate from the persistent
availability state.

Assistant message strings are rendered as GitHub-style Markdown through the
shared chat-message component and Angular HTML sanitization. User messages
remain escaped plain text.

## Map Rendering

`MapPreviewComponent` renders only normalized `MapSession` payloads through MapLibre. It does not render embedded HTML map payloads. Raster overlays should prefer `overlay.render` descriptors from the backend, including WMS/WMTS time, format, CRS, style, and tile matrix metadata.

## Component Patterns

Reusable component examples include:

- `map-preview.component.*`
- `chat-message.component.*`
- `settings-icon-action.component.*`
- `settings-modal-shell.component.*`
- `settings-api-key-field.component.*`
- `selected-model-summary.component.*`
- `capability-status-list.component.*`

Settings uses card-level model selection for one selected agent model.

## Routing Rule

Unknown routes redirect to the workspace route.

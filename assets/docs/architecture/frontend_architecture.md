# Frontend Architecture

Last updated: 2026-06-04

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
- Map rendering surface: `components/map-preview.component.*` and `components/map-preview-rendering.ts`

## Component Patterns

Reusable component examples include:

- `map-preview.component.*`
- `model-role-actions.component.*`
- `settings-icon-action.component.*`
- `settings-modal-shell.component.*`
- `model-stats-panel.component.*`

## Routing Rule

Unknown routes redirect to the workspace route.

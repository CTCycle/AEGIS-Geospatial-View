# Layout And Navigation

Last updated: 2026-08-02

## Workspace Layout

The main workspace uses a two-pane grid:

- chat and toolbar pane
- resize handle
- map pane

Toolbar width constraints:

- minimum: `280px`
- maximum: `760px`
- map minimum width guard: `320px`

On screens at or below `960px`, the workspace stacks chat above the map and
removes the resize handle. At or below `700px`, the chat and map minimum heights
are reduced for narrow-screen scrolling. The operations bar compresses at
`900px` and `460px`.

## Other Page Layouts

- Settings page uses a two-column `7fr/3fr` layout with responsive fallback rules.
- The app shell uses an Operations Bar for top-level navigation and status.

## Primary Screens

- `/`
  chat workspace, map pane, resizable divider, inline alerts, progress indicators
- `/settings`
  sticky header, search/filter controls, model cards, API key and Ollama management modals
- `/geodata`
  grouped manifest-backed capability tables
- `/access-configurations`
  optional geospatial provider credentials and access status

## Navigation Hierarchy

- top-level Operations Bar routes: workspace, geodata, access, model settings
- unknown routes redirect to workspace

# Layout And Navigation

Last updated: 2026-08-20

## Desktop Viewport Contract

AEGIS is a desktop application delivered through web technologies. The minimum
supported browser viewport is `1024px` wide. Smaller windows show a blocking
minimum-size notice rather than switching to a mobile layout.

Windows tablet devices are supported when they operate as a desktop browser and
can display the full desktop interface at the supported width.

## Workspace Layout

The main workspace uses a two-pane grid:

- chat and toolbar pane
- resize handle
- map pane

Toolbar width constraints:

- minimum: `280px`
- maximum: `760px`
- map minimum width guard: `320px`

The chat rail and map remain side by side at all supported widths. The divider
is mouse-resizable and the chat rail can be collapsed when map focus is useful.

## Other Page Layouts

- Settings page uses a two-column `7fr/3fr` desktop layout.
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

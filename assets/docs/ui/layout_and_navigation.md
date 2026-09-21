# Layout And Navigation

Last updated: 2026-09-21

## Desktop Viewport Contract

AEGIS is a desktop application delivered through web technologies. The minimum
supported browser viewport is `1024px` wide. Smaller windows show a blocking
minimum-size notice rather than switching to a mobile layout.

Windows tablet devices are supported when they operate as a desktop browser and
can display the full desktop interface at the supported width.

## Workspace Layout

The main workspace uses a two-pane content grid with a thin footer row:

- chat and toolbar pane
- resize handle
- map pane
- compact full-width workspace status footer spanning chat and map, with a
  Tool activity entry point for expandable execution details

The composer owns a separate 20px context-window progress row directly below
the send controls. It is not part of the footer. The progress indicator is
neutral below 80% usage, warning from 80% through 94%, and critical at 95% or
above; its label and title expose token details.

Toolbar width constraints:

- minimum: `280px`
- maximum: `760px`
- map minimum width guard: `320px`

The chat rail and map remain side by side at all supported widths. The divider
is mouse-resizable and the chat rail can be collapsed when map focus is useful.

The map header keeps its status/progress region in a flexible left column and
its icon actions in a fixed right column. Long status text truncates rather
than wrapping, resizing, or displacing the controls.

## Other Page Layouts

- Settings page uses a narrow persistent left navigation and a scrollable right
  content area; runtime forms use responsive three-, two-, and one-column field
  groups.
- The app shell uses an Operations Bar for top-level navigation and status.

## Primary Screens

- `/`
  chat workspace, map pane, resizable divider, inline alerts, context progress,
  and full-width status footer
- `/settings`
  persistent Models, Model Providers, Geospatial Access, Application,
  Map & Search, Data Sources, and Agent Runtime navigation; model cards,
  inline provider credentials, local Ollama controls, and typed runtime forms
- `/geodata`
  grouped manifest-backed capability tables

## Navigation Hierarchy

- top-level Operations Bar routes: Search (`/`), Geodata (`/geodata`), and
  Settings (`/settings`)
- Settings section query values: `models`, `model-providers`,
  `geospatial-access`, `application`, `map-search`, `data-sources`, and
  `agent-runtime`; missing and invalid values normalize to `models`.
- Settings section transitions use router history so browser Back/Forward restores
  the previous panel. Leaving Settings returns to the workspace without
  carrying its query parameters.
- unknown routes redirect to workspace

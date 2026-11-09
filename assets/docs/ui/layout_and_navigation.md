# Layout And Navigation

Last updated: 2026-11-09

## Desktop Viewport Contract

AEGIS is a desktop application delivered through web technologies. The minimum
supported browser viewport is `1024px` wide. Smaller windows show a blocking
minimum-size notice rather than switching to a mobile layout.

Windows tablet devices are supported when they operate as a desktop browser and
can display the full desktop interface at the supported width.

## Workspace Layout

The main workspace uses a content grid with a thin footer row:

- chat and toolbar pane, with a compact "Agent chat" header (new chat, Tool
  activity, hide chat); Tool activity opens its execution details inside the
  chat pane because they belong to the current session
- resize handle
- map pane, with no header row; small overlays hold the location chip and the
  agent activity pill
- session-history sidebar (15rem; fully collapsed by default on narrow screens)
- workspace toolbar, an always-visible 2.5rem icon rail on the far right with
  History, Alerts, Map tools, Layers, and Hide/Show map
- compact full-width workspace status footer spanning chat and map (capability status only)

The composer owns a separate 20px context-window progress row directly below
the send controls. It is not part of the footer. The progress indicator is
neutral below 80% usage, warning from 80% through 94%, and critical at 95% or
above; its label and title expose token details.

Toolbar width constraints:

- minimum: `240px`
- maximum: viewport width minus the map minimum
- map minimum width guard: `240px`

The chat rail and map remain side by side at all supported widths. Drag the
divider to resize the panes, or focus it and use the arrow keys; Home and End
move it to the minimum and maximum chat widths. Either the chat rail or the
map can be hidden (Hide chat in the chat header, Hide map in the workspace
toolbar); the other panel fills the space, and the hidden panel is
restored from a tab on the map's left edge or from the chat header. At most
one panel is hidden at a time. The history sidebar starts collapsed below
1280px viewport width.

Map tools (basemap selector, legend, and metadata-only/no-result notes) are
hidden by default and open from the Map tools button in the workspace toolbar.
The Layers button toggles the layer controls independently. Alerts, Map tools,
and Layers are disabled while the map is hidden. Zoom controls, failures,
attribution, and compliance notices stay visible on the map, and layer rows
keep names on one line to conserve canvas space.

The location chip truncates on one line at the top center of the map; the
activity pill sits beneath it and never blocks map gestures outside its Stop
button.

## Other Page Layouts

- Settings page uses a narrow persistent left navigation and a scrollable right
  content area; runtime forms use responsive three-, two-, and one-column field
  groups.
- The app shell uses an Operations Bar for top-level navigation and status.

## Primary Screens

- `/`
  chat workspace, map pane, history sidebar, resizable divider, inline alerts,
  context progress, and full-width status footer
- `/settings`
  persistent Models, Model Providers, Geospatial Access, Application,
  Map & Search, Data Sources, and Agent Runtime navigation; a scrollable model row list,
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

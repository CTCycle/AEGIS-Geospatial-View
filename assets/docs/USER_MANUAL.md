# User Manual

Last updated: 2026-05-17
Scope: End-user operation of AEGIS Geospatial View

## 1. What the Application Does

AEGIS Geospatial View is a chat-driven geospatial workspace. You describe a location and requested action in plain language, and the system returns map-focused results with overlays and session context.

## 2. Primary Screens

- Workspace (`/`): chat panel + map canvas.
- Geodata (`/geodata`): manifest-backed overview of map types, layers, direct tools, data providers, access constraints, and dependencies.
- Access configurations (`/access-configurations`): optional geospatial provider keys for Geoapify and TomTom.
- Model Settings (`/settings`): model selection, cloud/local LLM keys, and Ollama management.

## 3. Quick Start Journey

1. Open the app.
2. In chat, ask for a place or coordinates and what you want to see.
3. Wait for the assistant to return a response and map session.
4. Review map output and overlay controls.
5. Use the top Operations Bar to open geodata, optional access configuration, or model settings.

## 4. User Journeys

### Journey A: Location-first search
1. Enter a place request such as a city, region, or coordinate pair.
2. Include desired context (imagery or overlay action).
3. Send message.
4. Review updated map output.

### Journey D: Direct coordinate lookup
1. Ask directly for coordinates of a place (example: "Give me the coordinates of Rome, Italy").
2. The assistant returns plain-text coordinates.
3. This path does not require map rendering and may return without a map session.

### Journey B: Iterative refinement
1. Start with a broad location request.
2. Ask follow-up refinements in chat (scope, focus, timeframe).
3. Compare updated map session results after each turn.

### Journey C: Optional geospatial access setup
1. Open Access configurations from the Operations Bar.
2. Add Geoapify or TomTom keys only if you want optional key-backed layers.
3. Leave this page empty for the default free/open workflow.

### Journey D: Model setup
1. Open Settings.
2. Choose `Cloud` or `Local` mode.
3. Search/filter models and assign parser/api/chat/agent roles.
4. For Ollama, installed local models can be assigned immediately; selecting a library-only model starts a pull before assignment.
5. For local mode, manage Ollama URL, check connection, refresh models, or pull a model.
6. Save and return to chat.

## 5. Primary Commands and Interactions

Chat composer:
- `Enter`: send message.
- `Shift+Enter`: newline.

Toolbar and layout:
- Collapse/expand left panel with the toolbar toggle button.
- Resize toolbar width by dragging the vertical resize handle.
- Use the map `+` and `-` controls or type `zoom in` / `zoom out` to adjust the active interactive map.

Navigation:
- Workspace: chat and map canvas.
- Geodata: available map types, layers, tools, providers, and access status.
- Access: optional geospatial provider keys.
- Model Settings: LLM provider/model configuration.

Model Settings controls:
- Provider mode toggle (`Cloud`/`Local`).
- Model search bar and provider filters.
- API key modal for supported cloud providers.
- Ollama modal for URL, connectivity, model refresh, and model pull.

## 6. Usage Patterns

Recommended message pattern:
- Location: place name or coordinates.
- Goal: what insight/map output you need.
- Constraints: optional timeframe or focus.

Examples:
- "Show current satellite context for Rome, Italy."
- "Analyze this coordinate area: 41.9028, 12.4964 and include relevant overlays."
- "Refine the previous result to focus on environmental overlays."
- "Give me the coordinates of Rome, Italy."
- "What can you do?"
- "Show available layers."
- "Zoom in."

## 7. Key Features

- Chat-first geospatial orchestration.
- Interactive map payload preview with overlay controls.
- Lightweight map zoom controls and chat zoom commands.
- Manifest-backed geodata overview.
- Persisted session state across page refreshes within the same tab.
- Default free/open data workflow with optional geospatial provider keys.
- Configurable model roles (parser, chat, agent).
- Local and cloud provider workflows.

## 8. Troubleshooting Basics

- No response or failed request: verify backend/frontend are running.
- Local model issues: confirm Ollama URL and run connection check in Settings.
- Missing expected model: refresh model list or pull model in Ollama settings.
- Unexpected state after auth failures: app clears persisted state on 401/403 for safety.
- If asked for location: provide a city, address, region, or coordinate pair.
- If asked for missing geospatial integration: add the requested key in Access configurations or ask for an available open-data alternative.

## 9. Operational Notes

- External data sources can affect response quality/availability.
- State persistence is session-based and tab-aware.

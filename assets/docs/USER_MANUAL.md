# User Manual

Last updated: 2026-04-10
Scope: End-user operation of AEGIS Geospatial View

## 1. What the Application Does

AEGIS Geospatial View is a chat-driven geospatial workspace. You describe a location and intent in plain language, and the system returns map-focused results with overlays and session context.

## 2. Primary Screens

- Workspace (`/`): chat panel + map canvas.
- Settings (`/settings`): model selection, provider configuration, API key and Ollama management.

## 3. Quick Start Journey

1. Open the app.
2. In chat, ask for a place or coordinates and what you want to see.
3. Wait for the assistant to return a response and map session.
4. Review map output and overlay controls.
5. Open Settings (gear icon) to tune providers/models if needed.

## 4. User Journeys

### Journey A: Location-first search
1. Enter a place request such as a city, region, or coordinate pair.
2. Include desired context (imagery/overlay intent).
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

### Journey C: Model/provider setup
1. Open Settings.
2. Choose `Cloud` or `Local` mode.
3. Search/filter models and assign parser/chat/agent roles.
4. For local mode, manage Ollama URL, check connection, refresh models, or pull a model.
5. Save and return to chat.

## 5. Primary Commands and Interactions

Chat composer:
- `Enter`: send message.
- `Shift+Enter`: newline.

Toolbar and layout:
- Collapse/expand left panel with the toolbar toggle button.
- Resize toolbar width by dragging the vertical resize handle.

Settings controls:
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

## 7. Key Features

- Chat-first geospatial orchestration.
- Interactive map payload preview with overlay controls.
- Persisted session state across page refreshes within the same tab.
- Configurable model roles (parser, chat, agent).
- Local and cloud provider workflows.

## 8. Troubleshooting Basics

- No response or failed request: verify backend/frontend are running.
- Local model issues: confirm Ollama URL and run connection check in Settings.
- Missing expected model: refresh model list or pull model in Ollama settings.
- Unexpected state after auth failures: app clears persisted state on 401/403 for safety.
- If asked for location: provide a city, address, region, or coordinate pair.
- If asked for missing integration: add the requested API key in Settings or ask for an available alternative layer.

## 9. Operational Notes

- External data sources can affect response quality/availability.
- State persistence is session-based and tab-aware.

# Workflows

Last updated: 2026-06-02

## Core Journeys

### Location-First Search

1. Enter a place request such as a city, region, or coordinate pair.
2. Include desired context such as imagery or overlays.
3. Send the message.
4. Review updated map output.

### Direct Coordinate Lookup

1. Ask directly for coordinates of a place.
2. The assistant can return plain-text coordinates.
3. This path may not require map rendering.

### Iterative Refinement

1. Start with a broad location request.
2. Ask follow-up refinements in chat.
3. Compare updated map-session results after each turn.

## Recommended Prompt Pattern

- location
- goal
- optional timeframe or focus constraints

## Example Prompts

- `Show current satellite context for Rome, Italy.`
- `Analyze this coordinate area: 41.9028, 12.4964 and include relevant overlays.`
- `Refine the previous result to focus on environmental overlays.`
- `Give me the coordinates of Rome, Italy.`
- `Show available layers.`
- `Zoom in.`

## Key Features

- chat-first geospatial orchestration
- interactive map payload preview with overlay controls
- lightweight zoom controls and chat zoom commands
- manifest-backed geodata overview
- session persistence within the same tab
- optional provider-key workflows
- configurable model roles

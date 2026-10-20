# Workflows

Last updated: 2026-10-20

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

### Clarification And Overlay Control

1. If the request contains similarly likely locations, answer the clarification
   with the intended candidate.
2. Ask to add a layer or focus to extend the current map session.
3. Ask to remove, hide, clear, or stop showing a named overlay to remove the
   matching active layer while preserving the rest of the session.

Clarifications and unavailable providers are shown as explicit assistant
messages or warnings; they are not treated as successful empty map results.

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
- one selectable agent model for extraction, orchestration, tools, and responses
- durable run progress with steering while a request is active

## Discover conditions across an area

Ask an objective such as “Where in Europe did it rain most today?”, “Show the
highest temperatures in Southeast Asia”, or “Show European seismic hotspots
this week.” AEGIS samples the land of the region's member countries, refines
around the strongest samples, derives ranked points or grid bins, names the
nearest place for leading results, and fits a value-driven map to the results.
An unspecified search area uses World. A country outside the macro-region
catalog still uses the normal location resolver. Springfield and Florence can
still require clarification.

Read the source, sample count/spacing, units, time window and excluded/partial
coverage in the answer. Weather grid values are Open-Meteo model estimates,
not station measurements. The highest sample is not a verified regional
maximum. European, Mediterranean and Middle East earthquakes come from EMSC,
which is denser than USGS there; counts below the stated completeness magnitude
remain lower bounds. Place names are the nearest settlement, not a measured
site.

## Locate a photo

Attach an image with the button left of the message box (vision-capable models
only; the button is disabled otherwise) and ask, for example, “Where was this
photo taken?”. The agent names the visual cues it used, treats the place as a
hypothesis, and asks for confirmation when cues are not specific.

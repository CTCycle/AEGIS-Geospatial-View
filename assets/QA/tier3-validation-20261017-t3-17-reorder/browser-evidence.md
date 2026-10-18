# T3-17 browser evidence

- App: AEGIS local workspace in Codex in-app Browser, `http://127.0.0.1:5079/`.
- Conversation: `conv_77c80ca6b01d43b8b4e398bc37d2b52f`.
- Provider/model: `opencode-go / deepseek-v4.1-flash`; settings showed the lane
  as verified during the accepted runs.
- Map: OpenStreetMap, centered on Rome (41.8933°N, 12.4829°E).
- Attribution in the three-layer state: Open-Meteo, NASA GIBS, and GBIF.org and
  contributing datasets; OpenStreetMap attribution remained visible.

## Rendered composition and controls

The browser displayed Open-Meteo pressure/humidity/wind points (one feature),
NASA GIBS MODIS Terra daytime LST (21,584 nontransparent pixels), and a bounded
GBIF sample (300 records, three clusters). The trace has ready render
acknowledgements for the three initial compositions and checks
`required_sources_loaded`, `required_layers_present`, and `viewport_valid` as
true. See `run-evidence.json` for run IDs and acknowledgement sequences.

The layer rows exposed buttons named `Move <layer> up` and `Move <layer> down`.
The top row's up button and bottom row's down button were disabled. Keyboard
Enter on GBIF's up button moved it from position 3 to 2 and announced
“GBIF Species Occurrences moved to position 2 of 3.” The visible cluster
symbols then appeared above the raster. Keyboard Enter on its down button
returned it to position 3 and announced position 3 of 3; the opaque raster
covered those symbols. Enter on up restored position 2 and the symbols were
visible above the raster again.

The Open-Meteo, MODIS, and GBIF opacity controls were independently set to 80%,
50%, and 30%, then restored to 100%.

## Map updates

1. Removing MODIS produced a ready acknowledgement with Open-Meteo and GBIF
   still present and visible, in that order.
2. A fresh MODIS retrieval and re-add produced a ready acknowledgement with the
   same two surviving layers still ordered Open-Meteo / GBIF, followed by the
   appended raster. The successful second render attempt confirmed the raster
   source loaded and reported 21,584 nontransparent pixels.
3. Removing GBIF produced a ready acknowledgement with Open-Meteo and MODIS
   still present and visible. The browser layer panel showed `2 of 2 visible`
   and both attributions remained present.

The previous request to restore the raster had stopped at the agent's
configured execution limit without changing the map. The successful retry used
the same conversation and exact lane, with a fresh raster retrieval. No model
fallback occurred.

## Capture boundary

The in-app Browser exposed the live DOM/accessibility state and the runtime's
render trace, but its screenshot call returned `Unable to capture screenshot`.
The rendered stack change was observed in the browser during the run; no image
file is claimed here.

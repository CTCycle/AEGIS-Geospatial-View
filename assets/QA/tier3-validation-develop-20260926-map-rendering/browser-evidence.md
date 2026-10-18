# Browser evidence: Tier 3 map-rendering follow-up

Date: 2026-09-26 11:25–11:36 UTC (13:25–13:36 Europe/Rome).

The run used the user-configured exact `opencode-go / deepseek-v4.1-flash`
lane in the isolated runtime. Browser state was observed in the Chrome
extension tab at `http://127.0.0.1:4512/`; the user-owned tab was not closed.

| Slice | Prompt / action | Visible result | Status |
| --- | --- | --- | --- |
| T3-01 | `Show me the Colosseum in Rome.` | Colosseum transcript, coordinates, OSM tiles, OSM/MapLibre attribution, and ready map state. | PASS |
| T3-02 | `Show me active USGS water gauges around Austin, Texas.` | 48 gauges, clustered point symbols, `USGS Water Gauges` layer, layer legend, USGS attribution, and verified ready narration. | PASS |
| T3-02 | Toggle `Show USGS Water Gauges layer`. | Accessibility state changed `1 of 1 visible` → `0 of 1 visible` → `1 of 1 visible`; no map teardown. | PASS |
| T3-03 | Select `Dark Basemap`, then `OpenTopoMap Terrain`. | Darkened OSM and terrain tiles visibly rendered with matching selector values and attribution. | PASS |
| T3-04 | `Show me current NOAA weather alerts around Houston, Texas.` | Provider returned one non-renderable alert; the UI stopped after repeated invalid tool calls and retained no map. | BLOCKED |

No local screenshot artifact is claimed: the available browser-control API
returned screenshots inline but did not expose a filesystem export path.

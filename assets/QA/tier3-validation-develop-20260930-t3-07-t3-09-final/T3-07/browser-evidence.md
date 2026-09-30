# Browser evidence

The Codex in-app browser loaded the local frontend on `http://127.0.0.1:5010`.
The Geodata catalog reported `86 entries Ready`; its ESA WorldCover row showed
the source `mapproxy.terrascope.be/mapproxy/service`, WMS/static rendering, and
the preserved ESA/Terrascope attribution requirement.

The same browser opened the live AEGIS proxy tile
`/api/geospatial/tiles/esa_worldcover/8/136/93.png` as a `256×256` PNG image.
The saved raster evidence and pixel counts are in `network-summary.json`.

This is browser-visible source/tile proof only. It is not promoted to a full
MapLibre `map.render_ack` pass because the exact native agent run was not
available in the fresh runtime.

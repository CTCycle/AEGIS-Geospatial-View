# Browser evidence

The browser-first validation used the Codex in-app computer-use browser skill
and a full-size Chrome tab against the local frontend on `127.0.0.1:5000`.

1. `/geodata` rendered the real catalog with `86 entries` and `Ready`; the DOM
   exposed 18 provider items and 6 basemaps, including the EEA, ESA, GIBS,
   NOAA, and RainViewer entries.
2. The local same-origin RainViewer route
   `/api/geospatial/tiles/rainviewer_precipitation_radar/4/3/6.png` displayed
   an actual colored radar PNG in Chrome.
3. The workspace root displayed `Agent model: Needs attention`. A prior local
   chat attempt was stopped after remaining at `Understanding request`; no
   map session or `map.render_ack` is counted from that attempt.

The catalog and tile observations are browser evidence for catalog/data
availability only. They are not a MapLibre end-to-end pass, because no live
agent map plan was available in this isolated runtime.

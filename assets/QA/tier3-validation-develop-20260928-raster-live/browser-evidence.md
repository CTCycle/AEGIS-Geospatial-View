# Live raster browser evidence

Date: 2026-09-28. The official Windows launcher started the backend on
`127.0.0.1:7059` and the Angular client on `127.0.0.1:4512`. The Codex
in-app Browser was used for the live UI run. The selected lane was visible as
`opencode-go / deepseek-v4.1-flash`; the independent native structured probe
also returned `passed` with `parse_status=complete`. No provider or model
fallback was used.

## FEMA New Orleans

Request: `Show FEMA flood zones around New Orleans, Louisiana.` The provider
returned a renderable raster descriptor (`result_status=ok`, evidence
`evidence_33d49fac491144cf83bf54a77f225d31`) with Federal Emergency
Management Agency attribution. The browser briefly showed the FEMA Flood
Zones layer and raster-tile legend, but the map canvas stayed empty. The
terminal state was `render_failed` at the MapLibre source-load boundary, with
no visible source/layer acknowledgement and no `map.render_ack`.

## ESA WorldCover Rome

Request: `Show ESA WorldCover around Rome, Italy.` The provider returned a
renderable raster descriptor (`result_status=ok`, evidence
`evidence_c1737e02dce6462ebb220ea95440dc08`) with `© ESA WorldCover /
Terrascope` attribution. The final transcript explicitly reported that the
WorldCover data source did not load in the map renderer; the map remained
empty and no `map.render_ack` was received.

## Dependent composition and removal

The FEMA conversation was resumed and sent:

1. `Add nearby active USGS water gauges around New Orleans, Louisiana.`
2. `Remove the water gauges but keep the FEMA flood zones.`

The first update rendered a verified USGS-only map: `1 of 1 visible`, USGS
Water Gauges clustered-points, U.S. Geological Survey attribution, and the
footer showed `Agent model Verified`. FEMA was not simultaneously visible,
so FEMA plus USGS composition remains blocked. The second update reported
`Map state update verified in the browser` with `Visible overlays: none`.
The basemap remained visible and attributed, but FEMA was not retained because
it had never rendered. This does not satisfy FEMA retention.

The browser displayed the screenshots inline during the run, but this browser
surface did not expose a local binary screenshot path. No screenshot filename
is claimed here.

# T3-07 / T3-08 raster-provider follow-up

Date: 2026-09-29
Branch: `develop`
Lane: `opencode-go / deepseek-v4.1-flash`
Base source boundary: `643ecf3fa018f2f86569b1dd87c1d83973b623e` plus the scoped working-tree changes

## Outcome

- `T3-08: PASS` — all 12 advertised GIBS cases meet the existing browser acceptance boundary. The stable AEGIS fire capability remains `MODIS_Combined_Thermal_Anomalies_Fire` and maps to provider-native `MODIS_Combined_Thermal_Anomalies_All`.
- ESA WorldCover: `PASS` — current Terrascope WMS, AEGIS proxy, `200 image/png`, MapLibre source/layer/pixels, attribution, and accepted render acknowledgement.
- FEMA NFHL transport/render: `PARTIAL` — the existing endpoint and request construction remain intact, but the upstream request fails before an image response.
- FEMA composition/removal: `UNPROVEN` — no visible FEMA raster exists to validate retention and selective removal.
- `T3-07: PARTIAL` — ESA success does not override the FEMA boundary.

## Implementation boundary

ESA was migrated from the stale Terrascope WMTS manifest to `https://titiler.terrascope.be/wms` with WMS `1.3.0`, `EPSG:3857`, `image/png`, the current layer identifier, and the required static `TIME=2021-01-01`. The ESA adapter now emits protocol-aware WMS descriptors while retaining WMTS descriptor compatibility and legend/freshness metadata. The standard raster proxy remains the only browser-facing provider path.

GIBS keeps the public capability ID stable and now forwards the manifest’s provider-native layer. The provider adapter selects WMS when a matching WMTS advertises only vector tiles, preventing the fire layer from being materialized as an invalid `.png` WMTS request.

FEMA source code was not changed.

## Evidence

- [slice](slice.json)
- [provider probe](provider-probe.json)
- [network summary](network-summary.json)
- [GIBS trace summaries](gibs-trace-summaries.json)
- [browser evidence](browser-evidence.md)
- [backend diagnostics](backend-raster-diagnostics.log)
- [quality checks](quality-checks.log)
- [hosted CI](hosted-ci.json)

The raw instrumented reports and screenshots remain under this package for audit; the browser evidence deliberately preserves transport failures as failures rather than treating retrieval text as render proof.

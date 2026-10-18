# Tier 3 raster validation and gate reconciliation

- Date: 2026-09-28
- Branch: `develop`
- Tested source: `develop@be61298ddf4ae1c0b6900810b046c10d97e4993a`
- Evidence commit: `develop@51f94d2bc82e8510df1b70730b3b722ca272b64e`
- Provider/model: `opencode-go / deepseek-v4.1-flash`
- Runtime: isolated `runtimes/cache/test-runtime/tier3-raster-remediation-20260928`

## Decision

**T3-07 remains PARTIAL.** The exact-lane provider probe passed, and fresh FEMA and ESA requests returned attributed, renderable descriptors. In the real browser, both raster sources failed before source/layer presence and `map.render_ack`; two candidate basemaps did not recover ESA. No raster pixels were observed.

The FEMA-dependent `GEO-HYD-05` composition and `GEO-HYD-06` retention scenarios remain **BLOCKED** because FEMA never rendered. USGS rendered and acknowledged by itself. The follow-up removal acknowledged a basemap-only map with no overlays, which does not satisfy the request to retain FEMA.

The source-load evidence does not conclusively distinguish a bad constructed raster URL from a remote service or network failure. The official ESA GetCapabilities request failed in the browser with `ERR_HTTP2_PROTOCOL_ERROR`, but the Browser API exposed no network request events or HTTP response status. Descriptor tests pass, credentials are not the blocker, and a speculative renderer change is not supported by the evidence. `ISSUE-002` remains open; no implementation code was changed.

## Validation

- Official Windows launcher, isolated data root, exact `opencode-go / deepseek-v4.1-flash` lane. Startup/migration evidence: [startup.log](startup.log). Native structured probe: passed, parse complete.
- Browser-authoritative FEMA New Orleans and ESA WorldCover Rome attempts, plus USGS-only rendering and removal. Exact run identities, map sessions, bounds, source/layer checks, and acknowledgement states are in [browser-evidence.md](browser-evidence.md) and [run-summary.json](run-summary.json).
- Focused backend selection: **150 passed** across raster/descriptor/manifest, map-plan, capability execution, inspection, auditor, provider, render completion, and overlay-collection tests. See [focused-suite.log](focused-suite.log).
- Strict production manifest audit: **86 manifests, 0 errors, 0 warnings**. See [manifest-audit.log](manifest-audit.log).
- Ruff: **passed** for the backend and test packages. Ruff emitted three access-denied warnings while traversing protected cache paths; it reported no code diagnostics. See [ruff.log](ruff.log).
- Browser captured no console errors or warnings. Network request events/statuses were not exposed; direct ESA capabilities navigation returned `ERR_HTTP2_PROTOCOL_ERROR`. See [console-network-summary.json](console-network-summary.json).
- Task-owned backend/frontend processes were stopped and ports `4512`, `7059`, and `9876` were confirmed free. The isolated SQLite clone reports `quick_check=ok`; see [cleanup-checks.md](cleanup-checks.md) and [database-observation.txt](database-observation.txt).
- No renderer source changed, so frontend renderer tests and production build were not rerun. The live Browser scenarios exercised the current frontend source.

## Gate results

| Item | Final status | Evidence conclusion |
| --- | --- | --- |
| `T3-07` / `RASTER-LIVE` | `PARTIAL` | FEMA and ESA retrieval/descriptor paths pass; live MapLibre sources/layers and acknowledgements fail. |
| `GEO-HYD-05` FEMA + USGS | `BLOCKED` | USGS succeeds alone; there is no rendered FEMA layer to compose. |
| `GEO-HYD-06` remove USGS, retain FEMA | `BLOCKED` | Removal leaves no overlays; FEMA retention cannot be tested until FEMA renders. |
| `LIVE-HYD-20260920` | `PARTIAL` | Existing NOAA/USGS and vector scenarios remain valid; raster-dependent scenarios stay blocked. |
| `maps.raster-overlays` | `PARTIAL` | Public FEMA and ESA source-load boundary remains unresolved. |
| `maps.state-preservation` | `PARTIAL` | Existing vector composition/removal evidence stands; FEMA-specific retention is unproven. |
| `agent.map-render-ack-recovery` | `PARTIAL` | Failure is withheld correctly; no raster acknowledgement is falsely accepted. |
| `MATRIX-22` | `PARTIAL` | Raster dependent rows and broad route/provider/recovery coverage remain open. |
| `PROCESS-CLEANUP` | `PASS` | Exact owned processes stopped; required ports are free. |
| `HOSTED-CI` | `PASS` | [Run 36447036544](https://github.com/CTCycle/AEGIS-Geospatial-View/actions/runs/36447036544) completed successfully with all four jobs green for exact evidence commit `51f94d2bc82e8510df1b70730b3b722ca272b64e`; see [hosted-ci.json](hosted-ci.json). The final ledger reconciliation follows as a docs-only commit. |

The campaign remains **30 PASS, 1 PARTIAL, 0 BLOCKED, 37 UNRUN** at the 68-slice tier roll-up. Scenario-level FEMA dependencies are blocked without changing the slice count. Other open items remain visible: route coverage, the representative diary, OpenAI/Ollama parity, credentialed/local providers, dataset ingestion, and T3-08 through T5.

## Next boundary

Retry FEMA and ESA on a browser/network environment that records the actual tile request URL, HTTP response/status, and MapLibre error detail, or after the public endpoint is demonstrably available. Fix only a confirmed repository-owned URL/rendering defect. Then rerun standalone FEMA/ESA, FEMA+USGS composition, and FEMA retention, requiring visible pixels, source/layer state, attribution, matching session/revision, and accepted `map.render_ack`.

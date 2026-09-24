# Exact-lane browser evidence

- Date: 2026-09-24
- Official launcher: frontend `http://127.0.0.1:4512`, backend `http://127.0.0.1:7059/api/health`
- Isolated runtime: `runtimes/cache/test-runtime/validation-20260924-exact-lane`
- Provider/model: `opencode-go / deepseek-v4.1-flash`
After the launcher restart, Settings showed `deepseek-v4.1-flash` selected. `Test selected model` returned `Verified` and `Native tool probe passed`. No alternate lane was used.

## `T2-01` — Milan

- The first current-code live retest, `run_261892b0c24b4fc799cb075670cdb8da`, resolved `Mostrami Milano.` as ambiguous and asked the user to choose between `Milano, Texas, United States` and `Milan, Lombardy, Italy`. These are clearly labeled place/country alternatives.
- This followed an earlier current-source run (`run_ccd41391b8804c19ac6e1b213f43c676`) that exposed a verbose label (`Milan, Rodano, Milan, Lombardy, Italy`). The resolver was fixed to compose city ambiguity labels from structured locality, region, and country fields, dropping repeated locality and district noise. A focused regression covers the Texas/Italy pair.
- `run_9a8243e859714449a55c4c89245269a6`, follow-up `Milano, Italia`: the UI rendered the header `Milan, Lombardy, Italy`, coordinates `45.4642° N, 9.1896° E`, and an urban extent. The visible assistant result said the map was prepared and verified, with OpenStreetMap as the basemap and attribution visible. The run status completed and its trace recorded location resolution and `apply_map_plan` success.
- Prior exact-lane evidence for Springfield clarification and invalid-coordinate map retention remains in the [2026-09-23 browser record](../tier2-validation-develop-20260923-retry/browser-evidence.md).

`T2-01` passes for its recorded slice boundary: ambiguous candidates are presented with canonical labels, explicit Italy resolves correctly, and the map is visibly acknowledged.

## `T2-02` — Rome to Florence

- `run_9191dbe1eee445068801fb8011832c7e`, `Show me a map of Rome, Italy.`: Rome rendered at approximately `12.4829° E, 41.8933° N`, with OpenStreetMap attribution visible.
- `run_23f46a8c161a41ed97cdab8aa83a4982`, `Show me Florence.`: the assistant asked which Florence and presented Florence, Tuscany, Italy and Florence, Alabama, United States. Rome remained the displayed map while the ambiguity was unresolved.
- `run_9cb946f38ad24391bf82e6c7253fd4b6`, choice `1`: the UI rendered Florence, Tuscany, Italy around `11.26° E, 43.77° N`, showed OpenStreetMap attribution, and reported the map as rendered and ready. This completes the tested Rome-to-Florence replacement flow; `T2-02` passes for this scenario boundary.

## `T2-04` — Capability inventory

- `run_e736054311d241b8b53b1b73205e2de1`, `List the available map data capabilities. Do not display a map or load a layer.`
- The run completed three successful `discover_geospatial_capabilities` calls, each reporting 12 eligible capabilities. The UI then reported that the agent reached its configured execution limit. The configured `max_model_calls` was 4; discovery stopped before the bounded inventory of up to 50 candidates was exhausted.
- No map was requested or rendered. The inventory is `PARTIAL`; the validated behavior is paginated discovery without a map, not complete enumeration.

## `FEMA-COVERAGE-GUARDRAIL` — Zurich

- `run_08ff9bd080d04de588a443ab5eb7115c`, `Show the FEMA National Flood Hazard Layer over Zurich, Switzerland.`
- The operational trace shows `Resolve geospatial location` succeeded for Zurich, then `Describe geospatial capability` failed with `Capability is outside its declared geographic coverage.` The final visible response repeated that message. The map workspace remained ready with no map; no retrieval or render tool was called. The declared-coverage guardrail passes for this case, while the map request itself is correctly blocked.

## Capture limits

The rendered state was inspected through the browser accessibility tree and visible UI. The in-app Browser did not export a local screenshot; no binary screenshot or browser console/network artifact is claimed. No credentials, raw provider payloads, or private reasoning are recorded here.

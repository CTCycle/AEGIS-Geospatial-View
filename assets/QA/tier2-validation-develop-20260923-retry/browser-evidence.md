# Current-head browser evidence

- Date: 2026-09-23
- Branch/source boundary: `develop@f6e78852b21e1c4abdcdded95148cf86ee9c3371`
- Launcher: `start_on_windows.ps1 -Action Launch`
- Provider/model: `opencode-go / deepseek-v4.1-flash` (visible in the app; model status reached `Verified`)
- Browser: Chrome, `http://127.0.0.1:4512/`
- Data: isolated `runtimes/cache/test-runtime/tier2-retry-20260923` runtime, removed after validation.

## T2-01 — locations and bounds

- Zurich rendered with the header `Zurich, District Zurich, Switzerland`, center `8.5410°E, 47.3744°N`, and OpenStreetMap attribution. The follow-up coordinates `91,181` were rejected as out of bounds; the Zurich map stayed in place.
- `Show me Springfield` asked which Springfield was intended, distinguishing Sangamon County, Illinois from Hampden County, Massachusetts. Selecting `Springfield, Massachusetts, United States` rendered at `42.1019°N, 72.5887°W` with render verification.
- Current-run conversation `conv_29d6424da4db491d92e7c59c8735c42f`: `Mostrami Milano` asked for clarification. The choices included `Milano, Milam County, Texas` and `Milan, Rodano, Milan, Lombardy, Italy`. Selecting `Milan, Lombardy, Italy` rendered a verified Milan map centered at `45.4642°N, 9.1896°E` (run `run_fcf7c2fc07d349dcb99a66edf24333c1`).

**Status: PARTIAL.** Bounds rejection, Springfield clarification, and the selected Milan map passed. The Milan clarification still contains an incongruous Texas alternative and a geocoder label with `Rodano`, so the candidate quality remains an attention item.

## T2-02 — hydrated Rome and Florence replacement

Current-run conversation `conv_71783abf01d8433e9aa4100ea6430ae1`:

- Rome rendered with the correct Rome/Lazio header, center `12.4829°E, 41.8933°N`, OpenStreetMap, and verified render status (run `run_a891e22c1a5f4b5b94f726e7f6818727`). Reload restored the Rome transcript and map header.
- `Show me Florence on the map.` replaced Rome directly and set the header to `Florence, Tuscany, Italy` (run `run_4570de03ee124f9db54ff6024f4406d1`). It did not ask for confirmation. The final text was the generic verified-render acknowledgement; no DSML protocol text was exposed.
- The explicit follow-up `Show me Florence, Tuscany, Italy on the map.` rendered with center `11.2556°E, 43.7698°N` and verified render status (run `run_a20904123e1244b883d2e601d3c47592`).

**Status: PARTIAL.** Hydration, protocol-text suppression, and explicit Florence replacement passed. The ambiguous Florence request still changes the map without a clarification, so the Rome-preservation-during-clarification assertion remains unmet.

## T2-03 — landmark and POI routing

- Colosseum conversation `conv_a2bc27d715d147fea14ca4b6692b9c38`, run `run_dfe94ed41440408d96935cbe926cb38c`: the location resolved to the Colosseum in Rome; discovery selected `overpass_poi_amenities`; execution reported 100 features; the map plan was applied; the Overpass layer was checked and visible over OpenStreetMap with attribution; the run completed after render acknowledgement.
- Central Rome conversation `conv_631757cb3f4d462f8d2c7b786a23f029`: the initial `central Rome` wording produced a safe clarification asking for a city, country, or coordinates. After `Rome, Italy`, the location resolved to Rome/Lazio, the Overpass POI capability executed, and the layer rendered. The assistant reported 120 hospital/pharmacy points within an approximately 2.5 km area (runs `run_30516021077e4503b5f44f3043ed0b1e` and `run_f76d6fbd9ede41c4b831ba6e58e0fbbd`).
- After the route fix, `Show pharmacies in Rome, Italy.` completed on conversation `conv_fe8250bf708543aa94e06a85c2500c13`, run `run_3a727521ffe04ea0b026fc4a855c6858`. The operational trace showed `resolve_geospatial_location`, `describe_geospatial_capability`, successful `execute_geospatial_capability` (`overpass_poi_amenities`, 107 features), and `apply_map_plan`. The browser acknowledged the render; the checked Overpass layer was visibly rendered with OpenStreetMap attribution. The visible answer reports 19 features at the current zoom.

One pre-fix run showed execution rejected as outside the validated route; another attempt hit a temporary Overpass availability error. The final implementation run above succeeded, and the clarified central-Rome run also succeeded. Overpass reports partial reliability and a limited approximately 2.5 km returned extent; feature counts and completeness are provider/model-reported rather than independently audited.

**Status: PASS.** The safe location clarification, correct country binding, capability discovery/execution, map application, visible layer, attribution, and render acknowledgement were observed. Provider reliability and geographic coverage remain explicit limitations.

## Rendered evidence boundary

The in-app Chrome screenshots were visually inspected during these checks. The browser-control surface did not export standalone screenshot files, so no PNG evidence is claimed. Operational trace messages and visible map/layer state are recorded above; provider-reported feature counts are not treated as independent ground truth.

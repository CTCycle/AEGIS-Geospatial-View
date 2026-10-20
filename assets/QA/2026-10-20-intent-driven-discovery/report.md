# Intent-driven discovery — live validation (2026-10-20)

Branch `intent-driven-discovery`. Exact lane `opencode-go / deepseek-v4.1-flash`,
isolated runtime (`runtimes/cache/test-runtime/intent-discovery-20261020`),
backend `127.0.0.1:5087`, client `127.0.0.1:4587`, driven through the built-in
browser. Servers stopped afterwards; ports verified free.

## Results

| Workflow | Run | Outcome | Evidence |
| --- | --- | --- | --- |
| Europe: where did it rain most today | `run_83fdaf01…` | `completed` / `ready` in 6 tools. Europe bound from the macro-region catalog with no geocoding; Open-Meteo grid of 51 land points (~5.43°, 47 sea points excluded), then sort + limit, then a graduated map fitted to the results. Disclosure: model estimates, mm, per-point local window, "highest sampled, not verified regional maximum". | `final-europe-rain.jpg` |
| European seismic hotspots, past week | `run_d9aab8e0…` | `completed` / `ready`. The server replaced model-supplied dates (May) with the week window; USGS FDSN bbox query returned 3 events (M4.5–5.3), then `grid_aggregate` (2°), then a heatmap with a centres layer. Observations, completeness lower bound stated. | `final-europe-seismic.jpg`, `final-trace-europe-seismic.json` |
| Southeast Asia highest temperatures | `run_3122142b…` | `completed` / `ready`. 33 land points, ~4.55°, top 10 graduated; coordinates only, no invented place names; bbox over-coverage disclosed. | `final-seasia-heat.jpg`, `final-trace-seasia-heat.json` |
| Southern Europe > 20 °C with no rain | `run_5a38e46d…` | `completed` / `ready`. `attribute_filter` threshold returned 9 of 49 points, rendered as a graduated map. | `final-southern-europe-threshold.jpg`, `final-trace-southern-europe-threshold.json` |
| Southern Europe > 30 °C with no rain (earlier run) | `run_5363374e…` | Honest `valid_empty`: "no locations met both conditions in this sample", with full disclosure. | `earlier-trace-southern-europe-30c-valid-empty.json` |
| Weather in Paris (regression) | `run_1591aff1…` | `completed` / `ready`. Resolve, then point weather, then the map. Street-level zoom is the pre-existing single-point fit (unchanged from `main`). | `final-paris-weather.jpg` |
| Show Springfield / Show Florence (regression) | — | Both still clarify between the two candidates. | — |
| Hospitals within 5 km of Lyon (regression) | `run_c0c0d242…` | Routing is correct (resolve, then Overpass). The upstream Overpass status endpoint returned **502**, so the run ended with an honest failure. This is an external failure, not a regression. | — |

Traces (`*.json`) are kept locally only, because `assets/QA/**` is ignored.

## Defects found and fixed in this pass

1. **Analysis completion required one capability per query phrase.** For the threshold run the router emitted two queries (temperature, precipitation). One Open-Meteo grid covered both, yet render validation failed `required_data_retrieved`, `temporal_scope_applied` and `spatial_scope_applied`.
   - Fix: `CompletionEvaluator.data_checks` now requires one valid numeric source. The registry still exposes `execute` for further distinct sources.
   - Covered by `test_analysis_requires_distinct_executes`.
2. **Wrong USGS completeness note.** The note said "complete from about M2.5" outside the US. The live Europe week contained only M4.5+ events, which is consistent with ComCat's global completeness of about M4.5.
   - Fix: the note, its test and the docs were corrected.

The earlier fixes from the morning's live runs were all confirmed live:
- A raster no longer closes numeric retrieval.
- `transform_evidence` rejects raster descriptors.
- Analysis maps require derived evidence.
- The heatmap centres layer makes the heatmap queryable, so render verification passes.
- Grid points carry coordinate labels.

## Checks

- Backend unit: `1180 passed` (`unit-final.log`).
- Ruff clean (`ruff.log`).
- Pyright on changed files under `app/server` config: 0 errors (`pyright.log`).
- Client Karma: `291 SUCCESS` (`frontend-specs.log`).
- `ng build` OK (`client-build.log`).
- `requires_location` is absent from `app/`.

## Limitations (also recorded in the ledger and docs)

- Visual-clue image upload is deferred.
- Static bboxes over-cover; for example, Europe includes edges of North Africa and Turkey.
- Grid sampling misses local extremes. World sampling is about 25°.
- Open-Meteo values are model estimates.
- The elevation-zero sea heuristic is approximate.
- USGS completeness outside the US is limited (about M4.5).
- Result points carry coordinate labels only.
- Only one model lane was exercised.

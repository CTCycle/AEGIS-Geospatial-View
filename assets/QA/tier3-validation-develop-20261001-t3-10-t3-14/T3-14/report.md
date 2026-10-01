# T3-14 — GBIF species occurrence point-insight overlay

Date: 2026-10-01
Branch: `validation` (working tree)
Runtime: isolated `runtimes/cache/test-runtime/t3-07-live-*`; exact
`opencode-go / deepseek-v4.1-flash` lane persisted through the Settings API and
verified by the native structured probe.
Evidence package: `T3-14/` under this directory.

## Result

Both T3-14 scenarios render the GBIF species-occurrence point-insight overlay
with `GBIF.org and contributing datasets` attribution and an accepted
`map.render_ack`, with zero direct-upstream browser requests. The gbif
capability is `enabled_by_default: true` and routes for ordinary
species-occurrence prompts (the `avoidWhen` rewording landed in the T3-10
slice).

| Scenario | Classification | Overlay status | Attribution | Render ack | Direct upstream |
| --- | --- | --- | --- | --- | ---: |
| `t3_14_gbif_lugano` | `map_render_pass` | `loaded` | "GBIF.org and contributing datasets" | `render_observed` (ready) | 0 |
| `t3_14_gbif_valid_empty` | `map_render_pass` | `loaded` | "GBIF.org and contributing datasets" | `render_observed` (ready) | 0 |

Both runs selected `gbif_species_occurrences` (+ `osm_default` basemap) and
completed normally. The provider returns bounded occurrence records (limit
capped at 300) with dataset-level provenance fields (`basisOfRecord`,
`eventDate`, `datasetKey`), and occurrence results are never presented as
evidence of species absence.

## Note on the valid-empty sub-scenario

The chosen remote bounded location (48.5°N, 128.5°W, open Pacific) returned
marine occurrence records this run, so a strictly empty GBIF no-observations
boundary was not separately demonstrated. The point-insight render,
attribution, provenance/citation semantics, and accepted acknowledgement are
the new evidence recorded here; the absence-not-absence contract is enforced by
the manifest and provider warnings.

## Quality gates

- Backend focused suites: **passed** (agent + geospatial unit suites, including
  the gbif routing-contract assertions).
- Ruff: pass. Pyright: **0 errors**.
- Disposable runtime hygiene: exact lane persisted, probe passed, owned runtime
  cleaned on stop.
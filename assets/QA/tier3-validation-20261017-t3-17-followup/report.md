# T3-17 live validation follow-up

Last updated: 2026-10-17

**Outcome: live composition and removal scenarios passed; T3-17 remains `PARTIAL`.**
The exact provider/model lane was available through the user-authorized
database-stored key, and the missing third layer, opacity, and reverse-removal
scenarios were exercised in the browser. Manual layer reordering remains
unavailable in the current controls, so this report does not claim that
behavior.

## Tested boundary

- Branch: `validation`
- Tested HEAD before this evidence update: `9164b22e410c4fdb8c87121f1cfa738dd9b64390`
- Required lane: `opencode-go / deepseek-v4.1-flash`; no fallback.
- Bootstrap: `scripts/validation/run_t3_07_live_runtime.py` resolved the key
  from the local database in process and configured only the disposable
  isolated runtime. No credential value was entered into the browser, written
  to evidence, or printed.
- Runtime: isolated backend on port `5079`; its exact-lane health probe passed.
  The owned runtime data root was removed at shutdown and port `5079` was no
  longer listening. No application source changed in this slice.
- [Sanitized live-run evidence](run-evidence.json) captures application run
  events, `render_observed` status, source/layer visibility, and raster pixel
  evidence. [Runtime metadata](live-runtime.json) records only the selected
  lane and readiness state.

## Accepted browser scenarios

The app ran with its verified `opencode-go / deepseek-v4.1-flash` lane and
OpenStreetMap basemap. Each accepted map render reached `completed` with
`presentation_status=ready`, and its `render_observed` event was `ready`.

- Fresh Open-Meteo pressure/humidity/wind point: one provider feature, visible
  in Rome; run `run_3dac6616600d4543b43428a528330223`.
- NASA GIBS MODIS Terra daytime land-surface-temperature raster composed with
  the weather vector: both visible and attributed; 21,584 non-transparent
  raster pixels intersected the viewport. Run
  `run_2d55848ef9d74793a319a73679d39b10`.
- GBIF indexed historical occurrence sample: 25 records returned for the
  5-km Rome query, rendered as clustered points with Open-Meteo and MODIS
  retained; run `run_65fd79523744498fa3989eac178af516`. This is a capped sample
  from 163,580 matched records, not a complete inventory or evidence of
  absence. It is historical, not real-time, and source licensing/provenance
  varies by contributing dataset.
- In the browser, per-layer opacity sliders were set independently to
  Open-Meteo `80%`, MODIS `50%`, and GBIF `30%`; each displayed value was
  verified, then all three were restored to `100%` before removal checks.
- Removing only MODIS retained visible Open-Meteo and GBIF with both
  attributions; run `run_05db4bbc9d704778a27345154ea06277`.
- MODIS was fetched again and accepted with all three layers visible; run
  `run_f31312afe306447fb2e9f74d6e19eb15`. Removing only GBIF then retained
  visible Open-Meteo and MODIS and their attributions; run
  `run_5110096330a94abfa1a904d4940d2aef`.

The tested viewport remained Rome city-wide on OpenStreetMap. The final browser
state has two visible layers: Open-Meteo and the MODIS raster. The GBIF result
was only used as a historical bounded sample, with its contributing-dataset
attribution present while displayed.

## Remaining boundary

The layer panel exposes visibility checkboxes and opacity sliders, but no
manual reorder control. The browser showed the point overlays above the MODIS
raster; however, an interactive custom-order mutation could not be performed.
Because ordering is included in the reconstructed T3-17 purpose, the gate stays
`PARTIAL` pending either an explicit acceptance decision or a supported order
control and browser validation.

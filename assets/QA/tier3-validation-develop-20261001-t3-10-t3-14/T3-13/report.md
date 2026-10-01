# T3-13 — Open-Meteo atmospheric point insight family

Date: 2026-10-01
Branch: `validation` (working tree)
Runtime: isolated `runtimes/cache/test-runtime/t3-07-live-*`; exact
`opencode-go / deepseek-v4.1-flash` lane persisted through the Settings API and
verified by the native structured probe.
Evidence package: `T3-13/` under this directory.

## Result

Both T3-13 scenarios pass. The atmospheric point layer
(`openmeteo_pressure_humidity_wind`) renders over Rome with Open-Meteo
attribution and an accepted `map.render_ack`, and a pure numeric-insight
question (wind speed in Milan) returns a text answer without rendering an
unexpected map.

| Scenario | Classification | Overlay status | Attribution | Render ack | Direct upstream |
| --- | --- | --- | --- | --- | ---: |
| `t3_13_atmospheric_rome` | `map_render_pass` | `loaded` | "© Open-Meteo" | `render_observed` (ready) | 0 |
| `t3_13_text_vs_map_boundary` | `text_pass` | — | — | none (text only) | 0 |

The text-vs-map boundary holds: the Milan wind-speed question selected
`openmeteo_pressure_humidity_wind` (+ `get_weather_forecast` for the numeric
answer), rendered no map (`maplibre_canvas_count=0`), and completed normally.
No unexpected `unexpected_map_rendered` classification was recorded.

## Notes

- The capability is `enabled_by_default: true` in `runtime_profiles.json`
  (despite `agenticUse.manualToggle:false` in the manifest), so the
  atmospheric point layer is agent-routable without a settings action.
- No repository fix was required for this slice; the vector spatial/temporal
  scope coverage fixes from the T3-10 slice already satisfy the completion
  checks for the resolved-location point result.

## Quality gates

- Backend focused suites: **passed** (agent + geospatial unit suites).
- Ruff: pass. Pyright: **0 errors**.
- Disposable runtime hygiene: exact lane persisted, probe passed, owned runtime
  cleaned on stop.
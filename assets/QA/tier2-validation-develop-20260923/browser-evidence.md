# Tier 2 browser evidence

- Date: 2026-09-23
- Source boundary: `develop@155e1e22ce34a4b2698f474afa60b57f61b56916`
- Required browser: Codex in-app Browser
- Attempted app URL: `http://127.0.0.1:4512/`

## Observed browser state

After the official launcher returned its 60-second backend-health timeout, the
in-app Browser tab for the application showed the Chromium error page:
`127.0.0.1 refused to connect` / `ERR_CONNECTION_REFUSED`. The app was not
rendered. No map canvas, basemap attribution, layer state, run/session/revision
identity, or `map.render_ack` was available. No scenario prompt was submitted.

## Required evidence that is absent

| Slice | Expected location and viewport | Visible map / attribution | Matching acknowledgement |
| --- | --- | --- | --- |
| `T2-01` | Direct place navigation should center the map on the requested city; ambiguous `Springfield` should resolve to Springfield, Massachusetts after clarification; `Go to 91, 181` should retain the prior Zurich viewport; `Mostrami Milano` should prefer Milan, Italy or ask a safe clarification. | Not observable; app unreachable, so no visible map or attribution can be claimed. | None. |
| `T2-02` | Rome, Lazio, Italy should remain centered while `Florence` is ambiguous; explicit `Florence, Tuscany, Italy` should center near `11.2556°E, 43.7698°N`. | Not observable; app unreachable, so no visible map or attribution can be claimed. | None. |

No screenshot is presented as map evidence because the browser never loaded
the application. The current-head live slices therefore remain `BLOCKED`.

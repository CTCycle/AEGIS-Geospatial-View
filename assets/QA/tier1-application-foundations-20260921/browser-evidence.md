# Tier 1 browser evidence

Date: 2026-09-21
Revision: `c615c5799e1d5fb01e0af0eccaab5c6490d554c0`
Runtime: official Windows launcher, backend `7059`, frontend `4512`

The first Codex in-app browser opened at a narrow viewport and visibly showed
the documented **Resize the browser window to continue** gate. A separate
desktop-width Chrome session was then used for application assertions. This
kept the narrow gate as evidence and avoided treating it as a feature failure.

## Observed scenarios

| Scenario | Result | Observation |
| --- | --- | --- |
| Direct `/geodata` route | PASS | Title was `AEGIS | Geospatial catalog`; catalog rendered 86 entries at desktop width. |
| Direct `/settings?tab=application` | PASS | URL and Application runtime section rendered. |
| Unknown route | PASS | `/tier1-invalid-route` returned the Search workspace at `/`. |
| Below-minimum viewport | PASS | Narrow in-app browser was inert and showed the accessible resize message. |
| Seven Settings sections | PASS | Models, Model Providers, Geospatial Access, Application, Map & Search, Data Sources, and Agent Runtime each updated the query URL and rendered after settling. |
| Invalid Settings tab | PASS | `?tab=not-real` normalized to `/settings` and opened Models. |
| History panel | PASS | Existing saved conversations listed; search `Cambridge` returned matching requests. No saved item was modified. |
| Tab-local panel state | PASS | Chat panel was toggled, page reloaded, state remained, and the default visible chat state was restored afterward. |
| Safe credential lifecycle | PASS | Non-secret ArcGIS fixture was saved, input remained masked/blank, Clear became enabled, fixture was cleared, and reload returned `Not configured`. |
| Context identity | PASS | Workspace retained exact `opencode-go / deepseek-v4.1-flash` identity and showed `Context Unavailable` rather than fabricating a limit. |

The browser actions did not enter a real credential or open a provider
documentation page. The fixture was local-only and verified cleared after
reload.

## Browser limitations

The browser tool displayed screenshots inline but did not expose a local image
export API in this run. No binary screenshot is claimed. The headless E2E
failure and current accessible role contract are preserved in
[`report.md`](report.md) and [`test-results.md`](test-results.md).

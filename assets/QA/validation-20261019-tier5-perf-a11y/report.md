# 2026-10-19 Tier 5 accessibility and performance slice (T5-10, T5-09)

Branch: `develop`. Starting SHA: `4ead938d` (clean). Tested source: that SHA plus the working-tree changes in [slice.json](slice.json) (committed afterwards; the commit SHA is recorded in the ledger).
Lane: exact `opencode-go / deepseek-v4.1-flash` on an isolated disposable runtime (backend 127.0.0.1:5079, Angular dev server 5080, data root copied into `runtimes/cache`, removed afterwards; copied database `integrity_check` ok). A free OpenCode Zen model was considered as the agent model but no Zen credential exists in this runtime, so the validated lane was kept. Tier 5 IDs keep the LOW-confidence reconstructed mapping. No contract for `T5-09`/`T5-10` survives in the repository; the contracts below are authored here.

## Result summary

| Item | Result | Notes |
| --- | --- | --- |
| `T5-10` accessibility | `PASS` (automated + keyboard boundary) | 9 views audited with axe-core 4.10.2 (WCAG 2.0/2.1/2.2 A+AA and best-practice) at 1440 px: 0 violations after 9 defects were fixed. Manual screen-reader and contrast-over-map review not done. |
| `T5-09` performance | `PASS` (authored budget) | API p95 under 30 ms, one 2.0 s cold outlier; production bundle 368 kB initial transfer; Naples render completed within the observation window. Not a load test. |

## T5-10 authored contract

1. Every route (`/`, `/geodata`, seven Settings sections) and the populated map workspace have no axe violations at desktop width, with transitions disabled so mid-transition colours are not sampled.
2. Exactly one visible `h1`, a single `main` landmark, labelled elements carry a role that supports labels, ARIA id references resolve.
3. Real Tab presses move focus through the navigation and show a visible focus indicator.

The first audit pass ran while the viewport was below the 1024 px desktop gate, so the shell was `inert`; it was discarded and everything was re-audited at 1440 px. Axe was served from a scratchpad HTTP server and injected into the page; it is not a repository dependency.

### Defects found and fixed

| Finding | Fix |
| --- | --- |
| No `h1` on any route (`page-has-heading-one`) | Visually hidden `h1` per route page (`.page-title` in `styles.css`) |
| Models panel jumped from `h1` to `h3` (`heading-order`) | Hidden `h2 Models` in the models panel |
| Settings nested a `<main>` inside the app `main` (`landmark-main-is-top-level`, `landmark-no-duplicate-main`, `landmark-unique`) | `settings-page__main` is now a `div` |
| `aria-label` on `div`/`header`/`footer`/`span` without a supporting role (6 places) | `role="group"` on zoom controls, context-window row, status bar, provider list, status items; label removed from plain `header`s; map container is `role="region"` |
| `<footer role="status">` (disallowed role) | `div` |
| `aria-describedby` pointing at tooltips that exist only on hover | Set only while the tooltip is rendered |
| API-key field `aria-describedby` pointed at a health message that renders only for `healthy`/`unreadable` | IDs listed only for those states |
| MapLibre attribution link indistinguishable from text (`link-in-text-block`) | Underline via the control's own class chain in `styles.css` |
| Scrollable chat transcript not keyboard reachable (`scrollable-region-focusable`) | `role="log"`, `tabindex="0"`, `aria-label` |

Regression tests: two assertions added (status-list `aria-describedby`, API-key field description ids). Karma 277/277 pass; a production `ng build` succeeds.

### Boundaries

- Axe "incomplete" items remain for text over map imagery (`Basemap` label, loading text, MapLibre link) and the icon-only zoom button; axe cannot determine the background. Not manually verified.
- The in-app browser pane is hidden, so CSS transitions froze mid-state and produced false contrast hits on the Geospatial Access "Clear saved key" buttons; with transitions disabled the view is clean. This is a harness artifact, not a product defect.
- Dynamic states (modals, history, alerts, error panels, overlay controls with layers) were not audited. No screen-reader pass.

## T5-09 authored budget and measurements

| Measure | Budget | Observed |
| --- | --- | --- |
| Local API (health, chat settings, model catalog, runtime settings, geospatial catalog), 30 requests each | p95 under 100 ms | p95 15.5-27.6 ms; p50 2.4-9.7 ms; one 2,056 ms outlier on the first `chat/settings` call (cold), max of the others 120 ms |
| Production bundle initial transfer | under 500 kB | 368.25 kB (main 1.58 MB raw, 359.7 kB; styles 8.55 kB) |
| Dev-server navigation load | informational | DOMContentLoaded 199 ms, load 209 ms |
| Location prompt to rendered map (Rome, Naples) | under 30 s | Both rendered with `Verified` status; Naples was complete at the 17.4 s check, run time itself is 4.0-5.8 s per the T5-06 record; the pane is hidden so timers are throttled and this is an upper bound |
| Heap after repeated runs | informational | about 51 MB JS heap |

Not covered: concurrent load, large overlay payloads, cold-start of the backend, and any comparison against an earlier baseline (none exists).

## Not covered, and why

`T5-11` needs Tier 4B lanes without approved credentials; `T5-13` theme is unresolved; F-19, Overpass reliability, T4-03/T4-05/T4-06/T4-07 and Tier 4B are unchanged. Processes on ports 5079, 5080 and the helper server were stopped and the disposable runtime was deleted.

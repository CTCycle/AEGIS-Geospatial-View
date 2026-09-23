# T1-09 Settings Navigation and Drafts

Date: 2026-09-23
Slice result: `PASS`
Implementation commit: `develop@c090abd1ca9d6d78e82e798da9167b9d19b3fc23`
Baseline: `develop@696b1bcdceec5760f365e06fe18f9228161d70f3`

## Evidence boundary

The Settings component now follows browser history changes to the selected
section and removes its `popstate` listener when destroyed. The component test
covers Back/Forward state restoration. The stale toolbar and Geospatial Access
browser locators now use the existing button accessibility contract. Browser
fixtures return default runtime settings and empty provider setup data; no real
credentials are entered or submitted.

The controlled browser flow verifies the invalid-tab fallback, direct
`?tab=` section URLs, all seven rendered sections, URL changes, Back/Forward,
Application draft retention while switching sections, saving through an
in-memory runtime-settings fixture, and returning to Search before reopening
Settings and reading the saved value. Its PATCH never reaches the runtime
database. The in-app Browser separately rendered each section at desktop width
and verified the Search → Settings return path without saving settings.

Source fingerprints for the exact implementation commit are in
[source-sha256.txt](source-sha256.txt). The rendered test captures are in
[screenshots](screenshots/): Models, Model Providers, Geospatial Access,
Application, Map & Search, Data Sources, Agent Runtime, retained draft, and
saved value after return.

## Local validation

| Gate | Result | Evidence |
| --- | --- | --- |
| Focused Settings component suite | `PASS` — 31/31 | `npm run test -- --watch=false --browsers=ChromeHeadlessNoGpu --include src/app/pages/settings-page.component.spec.ts` |
| Settings browser regressions | `PASS` — 2 passed, 6 deselected | [settings-focused-e2e.log](settings-focused-e2e.log) |
| Toolbar Settings browser regression | `PASS` — 1 passed, 6 deselected | [toolbar-e2e.log](toolbar-e2e.log) |
| Angular production build | `PASS` | `npm run build` |
| Ruff on changed E2E files | `PASS` | `ruff check --no-cache app/tests/e2e/test_app_flow.py app/tests/e2e/test_settings_regressions.py` |
| `git diff --check` | `PASS` | Clean staged diff |
| In-app Browser rendered check | `PASS` | All seven section panels rendered; Search and Settings reopened successfully |

The recorded [broader Settings regression attempt](settings-regressions.log)
was exploratory and is not the T1-09 gate result. It ran before the history
listener correction and therefore contains the now-fixed T1-09 Back-navigation
failure. It also exposed a separate model-selection assertion with an invalid
`selected_model_context.model` response; that T1-11-area assertion was not
rerun as part of this focused T1-09 slice and is not included in this `PASS`.

## Hosted CI

The push-triggered `CI` workflow passed all four jobs against the exact
implementation commit
`c090abd1ca9d6d78e82e798da9167b9d19b3fc23`:
[GitHub Actions run 35873578752](https://github.com/CTCycle/AEGIS-Geospatial-View/actions/runs/35873578752).
See the [hosted-CI record](hosted-ci.md). The later evidence commit is
documentation-only and preserves this tested source boundary.

## Hand-off

T1-09 is `PASS`. Tier 1 remains `PARTIAL` because T1-10 credential failure
fixtures remain open. Continue with T1-10; the out-of-slice model-selection
finding remains for its own validation boundary.

# T3-07 / T3-09 ordered validation follow-up

Date: 2026-09-30
Branch: `develop`
Validated source: `develop@c8e6f416`
Validated working tree: source clean at the pushed commit; QA artifacts are
retained under this directory

## Ordered actions

1. Establish the current baseline and reproduce the provider boundaries.
2. Diagnose before changing code: FEMA failed at the transport/TLS boundary;
   ESA MapProxy returned a bounded raster; the fresh exact OpenCode Go lane had
   no injected credential or model assignment.
3. Apply only evidence-supported fixes:
   - ESA WorldCover now uses the first-party Terrascope MapProxy WMS service,
     with no static `TIME` parameter because the MapProxy bounded request is
     successful without it.
   - Add the isolated Settings-API exact-lane bootstrap at
     `scripts/validation/bootstrap_t3_09_exact_lane.ps1`.
4. Rerun the exact Settings-API/model sub-gate with the explicitly authorized
   canonical `opencode-go` credential supplied transiently through the process
   environment; do not copy or modify the canonical database.
5. Retest the affected contracts and record remaining gate boundaries.
6. Run the exact RainViewer request in the bounded retained Codex in-app
   browser, repair only the observed transparent fit-zoom and scope-evidence
   failures, then rerun the browser acknowledgment.

## Current evidence

- Focused post-fix regression: **74 passed**.
- Full backend unit suite: **1,034 passed**, 2 existing dependency warnings.
- Angular production build: **passed**; Karma: **264 passed**.
- Ruff: **pass**; Pyright: **0 errors, 0 warnings, 0 informations**.
- Strict production manifest audit: **86 manifests, 0 errors, 0 warnings**.
- Disposable backend proxy check: ESA tile `8/136/93` returned PNG bytes and
  the 256×256 result was fully non-transparent/non-white.
- In-app browser: the Geodata catalog showed ESA WorldCover using
  `mapproxy.terrascope.be/mapproxy/service`; the live AEGIS ESA proxy tile was
  also displayed as a 256×256 browser image.
- Exact-lane Settings-API/model bootstrap: **PASS**. The response reported
  credential presence/health, selected `opencode-go` /
  `deepseek-v4.1-flash`, and a native structured probe with HTTP 200 and a
  complete parse; the owned disposable runtime was cleaned. The raw
  user-authorized canonical credential was not recorded. See
  `T3-09/exact-lane-bootstrap.json`.
- Browser-authoritative RainViewer run: **PASS**. The browser displayed the
  Naples map and RainViewer layer; the server acknowledgment reported source
  and layer loaded, viewport-valid, tile intersection, supported z6 raster,
  90 non-transparent pixels, and satisfied temporal/spatial scope. See
  `T3-09/live-browser/browser-evidence.md` and `.json`.

## Gate boundaries

`T3-07` remains **PARTIAL**. ESA’s corrected first-party route is transport
and raster-content healthy, but the full browser MapLibre source/layer
acknowledgement package is not claimed here; FEMA remains **PARTIAL** because
REST metadata, layer query, export, WMS, fresh `httpx`, and native curl all
reset before an HTTP response. No FEMA fallback or provider substitution was
introduced.

`T3-09` is **PASS**. The exact
`opencode-go / deepseek-v4.1-flash` Settings-API/model structured probe and
the browser-authoritative RainViewer map acknowledgment both pass. The public
provider limitations remain documented in the browser evidence.

All temporary backend/frontend processes and disposable runtime roots created
for this follow-up were cleaned up after validation.

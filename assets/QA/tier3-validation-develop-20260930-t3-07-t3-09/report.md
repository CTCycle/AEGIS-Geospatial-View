# Tier 3 validation report — 2026-09-30

## Outcome

- `T3-07`: `PARTIAL`. FEMA is still blocked by an external transport failure;
  no image, visible pixels, accepted raster acknowledgement, or FEMA+USGS
  composition/removal proof exists.
- `T3-08`: `PASS` unchanged from the previously recorded 12-case GIBS browser
  boundary.
- `T3-09`: `PARTIAL`. The RainViewer implementation and exact-lane browser
  flow pass functionally, but the required disposable-runtime exact-lane run
  could not be completed because a fresh QA root had no OpenCode Go credential
  or model assignment. The successful browser proof used the launcher's
  configured canonical data root; this is reported as an evidence-isolation
  limitation, not promoted to a clean slice PASS.
- `FEMA-COVERAGE-GUARDRAIL`: `PASS` unchanged.

## Implementation

The scoped implementation:

- keeps FEMA on ArcGIS REST export and explicitly pins NFHL layer `28`;
- preserves protocol-aware, sanitized transport failure categories;
- adds RainViewer as a backend-owned raster provider;
- validates provider-supplied HTTPS hosts and opaque recent `/v2/radar/...`
  frame paths without deriving timestamps;
- enforces color scheme `2`, max zoom `7`, recent observed frames only, and
  same-origin AEGIS tile proxying;
- sets RainViewer provider responses to `result_type=raster`, including the
  valid-empty response;
- removes stale timestamp URL fallback and updates routing/catalog contracts.

## Evidence

The deterministic FEMA matrix is in `provider-probe.json`. RainViewer live
events, render acknowledgement boundary, and the pre-fix contract diagnosis
are in `run-trace.json`. The browser-visible state and exact MapLibre source /
layer IDs are in `browser-evidence.md`; network and proxy facts are in
`network-summary.json` and `backend-raster-diagnostics.log`.

The required exact lane was selected and natively verified in Settings. The
corrected request completed with a visible attributed raster overlay over
Naples, `render_observed=ready`, and committed `render_verified=true`.

## Quality gates

- Focused geospatial/provider suite: `125 passed, 2 warnings`.
- Post-catalog-contract regression: `34 passed` after the final manifest hash
  and catalog updates.
- Full backend unit suite: `1009 passed, 2 warnings`.
- Ruff: `All checks passed!` (the host emitted three access-denied warnings
  while scanning protected historical QA cache directories).
- Pyright: `0 errors, 0 warnings, 0 informations`.

Hosted CI for exact pushed implementation SHA
`bd1fe60b1e272936bc7b02d284c7bcc48d064acb` is run
`36692241300`; all four jobs passed: capability-contract-validation,
backend-unit-tests, persistence-conformance, and frontend-build-and-tests.
The only annotations were non-gating Node.js 20 action deprecation and
`ubuntu-latest` migration notices. See `hosted-ci.json`.

The initial broad `app/tests` command was stopped when it entered live E2E
tests without servers; it is not counted as a validation result. The final
unit suite used the repository's canonical pytest cache and disposable
basetemp root.

## Cleanup and limitations

The temporary transport harness and isolated runtime database were removed.
The official launcher processes and ports were stopped after validation. The
canonical `data` database was not altered or cleaned because the successful
browser run created validation conversations there and destructive deletion
was not authorized. See `cleanup-checks.txt`.

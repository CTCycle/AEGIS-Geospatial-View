# T3-09 exact-lane bootstrap

The supported bootstrap is `scripts/validation/bootstrap_t3_09_exact_lane.ps1`.
It creates a disposable runtime under `runtimes/cache`, injects the secret only
through `PATCH /api/chat/settings`, assigns exactly
`opencode-go / deepseek-v4.1-flash` in a separate Settings API patch, checks the
masked settings response, runs the native structured probe, scans owned logs
for the secret, and removes the disposable runtime by default.

The exact Settings-API/model sub-gate was rerun with the user-authorized
canonical `opencode-go` credential supplied only through a transient process
environment. The canonical database was not copied or modified; the raw key
was not recorded in output, logs, JSON, or QA. The bootstrap persisted the
credential only in its owned disposable runtime, verified the masked settings
response, and passed the native structured probe for
`opencode-go / deepseek-v4.1-flash` (HTTP 200, complete parse).

The bounded retained browser run then exercised the exact RainViewer request
in the Codex in-app browser. The first attempt exposed a real fit-zoom issue:
the public z7 tile was transparent for the Naples viewport. The surgical fix
set the catalog-backed browser fit cap to z6 while preserving the provider
ceiling at z7, and propagated server-bound current/point scope evidence into
the provider result. Commit `c8e6f416` was pushed to `origin/develop` before
the rerun.

Fresh run `run_e9325598bce1432ca73642b0b7b2920b` completed with
`presentation_status=ready`. The browser acknowledgment reported the source
and layer loaded, viewport valid, tile intersection true, zoom supported,
90 non-transparent raster pixels at z6, and both spatial and temporal scope
confirmed. See `live-browser/browser-evidence.md` and
`live-browser/browser-evidence.json`. The browser/backend processes were
stopped, the temporary viewport override was reset, and the marked disposable
runtime was removed after verification.

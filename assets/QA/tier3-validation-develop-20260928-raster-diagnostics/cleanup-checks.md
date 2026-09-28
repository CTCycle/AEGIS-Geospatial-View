# Raster diagnostics cleanup checks

- Date: 2026-09-28
- Stopped verified task-owned launcher processes: backend `28912`, preview wrapper `30668`/`6276`, Angular dev server `39172`, and child `esbuild` `34416`.
- Port `4512`: free.
- Port `7059`: free.
- Port `9876`: free.
- The task-created AEGIS in-app Browser tab was closed. A stale error-only data-URL tab from the initial refused-connection navigation remains in the temporary Codex in-app Browser session; Browser Use policy prevents rebinding that `data:` URL for closure. No application process or validation port remains.

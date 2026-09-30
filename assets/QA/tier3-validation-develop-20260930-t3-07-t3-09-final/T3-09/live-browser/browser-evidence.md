# T3-09 browser-authoritative RainViewer evidence

Date: 2026-09-30
Branch: `develop`
Source commit: `c8e6f416` (`fix: preserve raster scope evidence through render ack`)
Run: `run_e9325598bce1432ca73642b0b7b2920b`
Browser: Codex in-app Browser, `http://127.0.0.1:5011/`

## Request

`Show the latest RainViewer precipitation radar over Naples, Italy.`

## Result

**PASS — browser-authoritative render acknowledgment.** The run completed with
`state=completed`, `presentation_status=ready`, and one render attempt. The
browser visibly displayed the Naples map with the RainViewer layer selected.

The server-recorded browser acknowledgment reported:

- required sources loaded: `true`
- required layers present: `true`
- viewport valid: `true`
- raster source loaded: `true`
- raster layer present and visible: `true`
- raster tile intersects the Naples viewport: `true`
- raster zoom supported: `true`
- non-transparent raster pixels: `90`
- observed raster tile: `z=6, x=34, y=24`
- temporal scope: satisfied
- spatial scope: satisfied

The browser response identified the latest observed frame at `2026-09-30
21:20 UTC`, retrieved at `21:27 UTC`, and retained the provider limitations:
recent past radar only, latest frame only, public zoom ceiling 7, best-effort
service, and global-partial coverage.

## Surgical fix validated

The first browser attempt reached RainViewer at z7 but returned zero
non-transparent pixels and failed `raster_zoom_unsupported`/visibility
validation. The catalog now retains the provider `max_zoom=7` while exposing
`fit_max_zoom=6` for browser fit views. The server-bound route also carries
`temporal_mode=current` and `analysis_scope=point`; the RainViewer provider
reports those scope facts as evidence metadata. This keeps the browser gate
strict and removes only the observed transparent-fit and missing-scope
failures.

The raw `opencode-go` credential was supplied through process environment only
and is not present in this artifact.

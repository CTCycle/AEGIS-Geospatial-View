# Browser evidence: T0-04 and T2-04

- Date: 2026-09-25
- Source: `develop@800e0568f6b83254b60c4efe25e014e3fefdf81c`
- Browser: Chrome, local AEGIS tab at `http://127.0.0.1:4512/`
- Runtime: isolated `runtimes/cache/test-runtime/validation-20260925-t0-t2-followup`
- Provider lane: Settings visibly selected `opencode-go / deepseek-v4.1-flash`; no fallback was used.

## Settings and lane

The browser Settings > Agent Runtime panel initially showed `Simple model calls = 4`.
Only that field was changed to `6`; the UI confirmed that a restart was required.
After restart, the panel showed `6`. Settings > Models continued to show
`deepseek-v4.1-flash` under `opencode-go · cloud`. The final restore set the field
back to `4`, restarted the official launcher, and the browser showed `4` again.
The final Settings model probe visibly reported `Verified` and `Native tool probe
passed`.

## T2-04 discovery-only run

The exact browser request was:

> List the available map data capabilities. Do not display a map or load a layer.

The workspace remained `Ready for a location or data request` with the map canvas
empty throughout. The expanded browser Tool activity panel showed run
`run_24af742659ad4c32863c2c38b5f6abd2`, status `completed`, five successful
`Discover geospatial capabilities` calls, and page counts `12`, `12`, `12`, `12`,
and `2`. The browser showed `Agent model: Verified` and `5 calls`.

The persisted sanitized run trace reconciles 50 candidate records with 50 unique
IDs and a final `next_cursor = null`; it also records `model_calls = 6`,
`max_model_calls = 6`, no map session, and no budget-exhausted result. No map
request, provider retrieval, or render acknowledgement was part of this slice.

An earlier diagnostic wording (`List all available geospatial capabilities and
data sources...`) intentionally returned two eligible Census capabilities in one
call because its semantic query was narrower. It is not counted as the T2-04
inventory result; the approved broad wording above exercised the full catalog.

## T0-04 visible startup boundary

The official launcher reached backend health and frontend readiness on every
recorded isolated start. The browser was reloaded after the restored launch and
the runtime setting and exact model selection remained visible. The launcher
safety harness separately verified changed-owner/PID-reuse protection and
backend/frontend readiness-failure cleanup; its output reports that unrelated
processes survived and no real service or user process was targeted.

No local screenshot was exported by the in-app Browser. The evidence is based on
the live accessibility tree, visible Settings/Workspace status, and the
operational execution panel. No credentials, private reasoning, or raw provider
payloads are included.

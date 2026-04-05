# Web App State Preservation

Last updated: 2026-04-05  
Scope: `AEGIS/client/src`

## Overview

The web app now preserves user working context across:
- in-app navigation between `/` (chat/map) and `/settings`
- browser back/forward navigation
- page refreshes in the same tab

State is stored in `sessionStorage` under `aegis:webapp-state:v2` with a 6-hour TTL.
Legacy key `aegis:webapp-state:v1` is removed on load; no backward restore compatibility is retained.

## Preserved State Categories

Chat/map workspace (`/`):
- toolbar layout: width and collapsed state
- chat session context: `sessionId`, transcript messages, assistant draft stream text, current status
- chat composer draft text
- chat transcript scroll position
- latest rendered map payload (`map_session` + compatible payload fields)
- overlay control state: visibility and opacity per overlay id
- page scroll position

Settings workspace (`/settings`):
- model search query text
- selected provider mode tab (`local`/`cloud`)
- status/footer text
- settings page scroll position
- model grid scroll position

## Routing and Deep Links

- Routing uses browser history paths:
  - `/` -> chat/map workspace
  - `/settings` -> settings workspace
- Back/forward behavior is handled via `popstate`.
- Direct loads to `/` and `/settings` restore state correctly when available.
- Unknown paths are normalized to `/` to avoid stale route-state mismatches.
- Settings deep links now include URL query state:
  - `q=<search text>`
  - `mode=local|cloud`
  Query params are treated as source-of-truth on load and are kept synchronized while using `/settings`.

## Restore and Clear Rules

Restore behavior:
- State is validated and restored only when schema and version checks pass.
- Expired state (older than 6 hours) is discarded.
- Transient runtime-only flags (for example active request loading flags) are not restored.

Intentional clear behavior:
- `401` or `403` API responses clear persisted state to prevent unsafe cross-auth leakage.
- corrupted/invalid storage payloads are discarded automatically.

## Edge Cases and Guardrails

- Refresh: state restores from `sessionStorage`.
- Duplicated tabs: persisted state is now tab-scoped with a generated tab id plus cross-tab ownership heartbeat. If a duplicated tab starts while the original tab is active, the duplicated tab rotates to a new tab id and discards the copied snapshot to prevent cross-tab leakage.
- Missing/changed entities (for example overlays no longer present): only current overlay ids are applied; stale ids are ignored and a non-blocking in-UI notice is shown.
- No hydration mismatch risk: app is client-rendered only and restores state after startup.

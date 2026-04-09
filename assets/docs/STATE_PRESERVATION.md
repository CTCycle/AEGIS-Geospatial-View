# Web App State Preservation

Last updated: 2026-04-09
Scope: `AEGIS/client/src`

## Overview

The web app preserves user working context across:
- navigation between `/` (chat/map) and `/settings`
- browser back/forward
- page refreshes in the same tab

State is stored in `sessionStorage` under `aegis:webapp-state:v2` with a 6-hour TTL.

## Preserved State Categories

Chat/map workspace (`/`):
- toolbar width and collapsed state
- chat session context and transcript state
- chat composer draft
- transcript scroll position
- latest rendered map payload
- overlay visibility/opacity
- page scroll position

Settings workspace (`/settings`):
- model search text
- provider mode tab (`local`/`cloud`)
- status/footer text
- page scroll position
- model grid scroll position

## Routing and Deep Links

- `/` -> chat/map workspace
- `/settings` -> settings workspace
- Back/forward is handled by Angular Router/browser history.
- Unknown paths redirect to `/`.
- Settings query-state deep links use:
  - `q=<search text>`
  - `mode=local|cloud`

## Restore and Clear Rules

Restore behavior:
- state is restored only when schema/version checks pass
- expired state is discarded
- transient runtime-only loading flags are not restored

Clear behavior:
- corrupted storage payloads are discarded automatically

## Guardrails

- Duplicated tabs are isolated via tab id and ownership heartbeat.
- Stale overlay ids are ignored.
- App is client-rendered and restores state post-startup.

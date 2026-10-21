# State Preservation

Last updated: 2026-10-21

## Overview

The web app stores per-tab view preferences in `sessionStorage` under
`aegis:webapp-ui-state:v1` with a 6-hour TTL.

Malformed, expired, and unsupported-version payloads are discarded. The
current state contract has no migration from older keys or versions.

## Persisted Root Contract

`PersistedAppState` contains:

- `version`
- `savedAt`
- `chatPage`
- `settingsPage`

## Chat And Map State

Persisted chat state includes:

- toolbar width and collapsed state
- chat-panel conversation ID, last run sequence, composer draft, and transcript
  scroll position
- map overlay visibility, opacity, and order
- chat-page scroll position
- settings search text and scroll positions

The basemap selector is a live session preference: a manual choice is retained
when subsequent location requests prepare a new map candidate, while a new
chat or browser reload starts from the catalog default basemap.

Conversation history, active runs, and map sessions are loaded from their
current API contracts; they are not copied into this view-preference cache.

Prepared map state is a candidate, not committed visualization memory. The
client validates it locally and acknowledges the exact run/version/session/
revision tuple. Until the server accepts that acknowledgment, the previous
committed map remains authoritative. Reconnect hydrates a still-pending
candidate; a duplicate matching acknowledgment updates neither transcript nor
context revision, while a stale or conflicting acknowledgment is discarded.

## Restore Rules

State is restored only when:

- schema version matches
- TTL has not expired
- persisted `tabId` matches active ownership
- payload shape remains valid

Otherwise the app falls back to `defaultAppState()`.

Settings section selection is URL-owned rather than session-storage-owned. The
`tab` query parameter deep-links to any Settings section (`models`,
`model-providers`, `geospatial-access`, `application`, `map-search`,
`data-sources`, or `agent-runtime`); missing and invalid values resolve to
`models`. Runtime form drafts remain local to the active Settings page until an
explicit save commits them through the runtime settings API.

Late completion payloads with older context revisions are discarded. Numeric
backend chat-session identifiers are neither restored nor transmitted.

The browser sends bounded render evidence only: source/layer presence, loaded
state, viewport validity, and rendered feature counts where applicable. It does
not send geometry, raw tile URLs, or browser error objects. A new run locally
invalidates an older pending candidate, and the server atomically supersedes it
when the new run is created.

The active run also persists the last realtime event sequence and bounded seen-
event IDs so WebSocket reconnects can replay without duplicating transcript
output. Event IDs protect against duplicate delivery; sequence remains the
durable replay cursor. Steering refinements are already represented in the
persisted message list and do not need a separate persisted field.

## Tab Isolation And Clear Behavior

Tab ownership uses:

- `aegis:webapp-tab-id:v1`
- `aegis:webapp-tab-heartbeat:v1:<tabId>`

The app clears persisted state when payloads are corrupted, expired, schema-invalid, or owned by a different active tab. `clearPersistedAppState()` explicitly clears the current tab snapshot.

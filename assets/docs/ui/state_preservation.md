# State Preservation

Last updated: 2026-09-05

## Overview

The web app stores per-tab UI state in `sessionStorage` under `aegis:webapp-state:v5` with a 6-hour TTL.

Older schema payloads are invalidated and discarded.

## Persisted Root Contract

`PersistedAppState` contains:

- `version`
- `savedAt`
- `tabId`
- `chatPage`
- `settingsPage`

## Chat And Map State

Persisted chat state includes:

- `conversationId`, `contextRevision`, `taskSnapshot`, `activeRunId`, and `activeRunVersion`
- `conversationNonce`
- `messages`
- `lastDecision`
- `memorySnapshot`
- `mapSession`
- candidate presentation identity and status (`runVersion`, `mapSessionId`,
  `collectionRevision`, and pending render requirements)
- status and composer/transcript UI state
- bounded run event duplicate-protection state

Persisted map UI state includes:

- `overlayVisibility`
- `overlayOpacity`
- stable overlay instance IDs and the active collection revision carried by the
  current `mapSession`

The v5 boundary invalidates pre-collection active-map/task snapshots. A small
one-time migration retains conversation ID and messages, while old map/task
state is discarded; messages are never removed solely because the map schema
changed.

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

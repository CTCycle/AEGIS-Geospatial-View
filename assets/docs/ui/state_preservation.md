# State Preservation

Last updated: 2026-08-27

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

## Restore Rules

State is restored only when:

- schema version matches
- TTL has not expired
- persisted `tabId` matches active ownership
- payload shape remains valid

Otherwise the app falls back to `defaultAppState()`.

Late completion payloads with older context revisions are discarded. Numeric
backend chat-session identifiers are neither restored nor transmitted.

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

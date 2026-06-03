# State Preservation

Last updated: 2026-06-02

## Overview

The web app stores per-tab UI state in `sessionStorage` under `aegis:webapp-state:v3` with a 6-hour TTL.

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

- `sessionId`
- `conversationNonce`
- `messages`
- `lastDecision`
- `memorySnapshot`
- `mapSession`
- status and composer/transcript UI state

Persisted map UI state includes:

- `overlayVisibility`
- `overlayOpacity`

## Restore Rules

State is restored only when:

- schema version matches
- TTL has not expired
- persisted `tabId` matches active ownership
- payload shape remains valid

Otherwise the app falls back to `defaultAppState()`.

## Tab Isolation And Clear Behavior

Tab ownership uses:

- `aegis:webapp-tab-id:v1`
- `aegis:webapp-tab-heartbeat:v1:<tabId>`

The app clears persisted state when payloads are corrupted, expired, schema-invalid, or owned by a different active tab. `clearPersistedAppState()` explicitly clears the current tab snapshot.

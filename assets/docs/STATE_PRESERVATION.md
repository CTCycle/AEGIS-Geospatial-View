# Web App State Preservation

Last updated: 2026-04-21
Scope: `AEGIS/client/src`

## Overview

The web app stores per-tab UI state in `sessionStorage` under key `aegis:webapp-state:v3` with a 6-hour TTL.

Persistence is strict-versioned. Older schema payloads are invalidated and discarded.

## Persisted Root Contract

`PersistedAppState` contains:
- `version` (`3`)
- `savedAt`
- `tabId`
- `chatPage`
- `settingsPage`

## Chat Page Persistence

`chatPage.chatPanel` persists:
- `sessionId`
- `conversationNonce`
- `messages`
- `lastDecision`
- `memorySnapshot`
- `mapSession`
- status and composer/transcript UI state

Map UI state also persists:
- `overlayVisibility`
- `overlayOpacity`

## Restore Rules

State is restored only when all checks pass:
- schema version is `3`
- TTL has not expired
- persisted `tabId` matches active tab ownership
- payload shape is valid objects/arrays for required sections

If checks fail, app falls back to `defaultAppState()`.

## Tab Isolation

Tab ownership uses:
- session tab id (`aegis:webapp-tab-id:v1`)
- localStorage heartbeat (`aegis:webapp-tab-heartbeat:v1:<tabId>`)

If an active owner heartbeat is detected, a new tab id is generated and persisted state is reset for isolation.

## Clear Behavior

The app clears persisted state when:
- payload is corrupted JSON
- schema version is invalid
- state is expired
- tab ownership is invalid

`clearPersistedAppState()` explicitly clears the persisted snapshot for the current tab.

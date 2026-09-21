# Tier 1 application-foundations validation ledger

Date: 2026-09-21
Branch: `loop-dev`
Commit: `c615c5799e1d5fb01e0af0eccaab5c6490d554c0`
Overall status: `PARTIAL`

The canonical machine-readable ledger is [`ledger.json`](ledger.json). Detailed
observations are in [`browser-evidence.md`](browser-evidence.md) and
[`test-results.md`](test-results.md).

| Slice | Capability | Exists | Exercised | Passed | Fully passed | Status | Primary boundary / next action |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `T1-01` | Navigation, route fallback, desktop gate | yes | yes | yes | yes | `PASS` | Routes, invalid redirect, narrow gate, and desktop workspace passed. |
| `T1-02` | Tab-local state persistence | yes | yes | yes | no | `PARTIAL` | Logical state restored, but headless fixture did not expose MapLibre canvas; retest with WebGL evidence. |
| `T1-03` | Conversation lifecycle and history | yes | yes | yes | no | `PARTIAL` | History list/search passed; select/hydrate, pagination, and missing-ID browser cases remain. |
| `T1-04` | Realtime connect/replay/deduplication | yes | yes | yes | yes | `PASS` | Local API/service/parser coverage passed; no hosted/outage claim. |
| `T1-05` | Run start/steer/cancel/idempotency | yes | yes | yes | yes | `PASS` | Local lifecycle/orchestrator coverage passed. |
| `T1-06` | Synchronous `/api/chat/turn` contract | yes | yes | yes | no | `PARTIAL` | Unit/preflight contract passed; exact live 200/202/409/404/503 matrix remains. |
| `T1-07` | Background chat jobs | yes | yes | yes | no | `PARTIAL` | Worker lifecycle passed; mounted API, unknown-job, and shutdown boundaries remain. |
| `T1-08` | Runtime Settings API/persistence | yes | yes | yes | yes | `PASS` | Typed merge/validation/atomicity and current restart metadata passed. |
| `T1-09` | Seven-section Settings navigation/drafts | yes | yes | yes | no | `PARTIAL` | Seven-section browser matrix passed; stale E2E expects `role=tab` instead of current buttons. |
| `T1-10` | Credential lifecycle | yes | yes | yes | no | `PARTIAL` | Safe save/mask/clear passed; unreadable and API-failure fixtures remain. |
| `T1-11` | Model library/selection/probe | yes | yes | yes | yes | `PASS` | Local catalog/probe contract and exact selection/no-fallback evidence passed. |
| `T1-12` | Context-window authority/presentation | yes | yes | yes | yes | `PASS` | Known/unknown profile presentation and retention evidence passed. |

No application source or test was changed during this baseline. Partial rows
remain visible so future agents can continue at the first incomplete boundary.

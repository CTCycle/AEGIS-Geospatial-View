# Tier 1 application foundations

Last updated: 2026-09-21

Tier 1 is the application-foundation gate. It must establish that the shell,
state, persistence, realtime lifecycle, Settings, model selection, and context
presentation are trustworthy before Tier 2 agent or Tier 3 provider/rendering
claims are expanded.

## Slice checklist

| Slice | Capability | Required boundary | Primary regression evidence |
| --- | --- | --- | --- |
| `T1-01` | Navigation, route fallback, desktop gate | Direct and navbar routes, invalid-route redirect, and inert below-minimum viewport. | `app.routes.spec.ts`, `app.component.spec.ts`, wide/narrow browser proof. |
| `T1-02` | Frontend tab-local state | Valid reload, TTL, corruption, schema, tab isolation, and retained UI/map state. | `app-state*.spec.ts`, one browser reload with visible state. |
| `T1-03` | Conversation lifecycle and history | Create/list/search/select/hydrate, pagination, unknown ID, and no cross-conversation leakage. | Conversation API/repository tests plus history browser flow. |
| `T1-04` | Realtime connect/replay/deduplication | Heartbeat, reconnect cursor, ordered replay, duplicate suppression, malformed envelope, and origin rejection. | Realtime API/service/parser suites plus one normal browser run. |
| `T1-05` | Run start/steer/cancel/idempotency | Version changes, duplicate request IDs, stale work protection, and terminal cancellation. | Run lifecycle/orchestrator suites and a post-cancel normal run. |
| `T1-06` | Synchronous `/api/chat/turn` contract | Distinguish terminal `200`, accepted `202`, genuine conflict `409`, missing `404`, and unusable-provider `503`. | Chat API contract suite plus exact live response matrix. |
| `T1-07` | Background chat jobs | Queue/progress/completion/cancel/unknown-job behavior, shutdown boundary, and no false restart persistence. | Job service/API suites and one normal job. |
| `T1-08` | Runtime Settings API/persistence | Typed defaults, partial merge, atomic update, invalid values, restart metadata, and reread. | Runtime Settings API/repository tests plus isolated restart. |
| `T1-09` | Seven-section Settings navigation/drafts | URL-authoritative section selection, invalid tab fallback, dirty draft behavior, save, and return. | Settings component suite plus all seven rendered sections. |
| `T1-10` | Credential lifecycle | Masked state, safe save/clear, blank-draft safety, invalid input, undecryptable state, and API failure. | Credential/crypto suites plus safe fixture browser flow; never use real secrets. |
| `T1-11` | Model library/selection/probe | Static and dynamic catalogs, unsupported protocol, selection retention, provider failure, and probe expiry. | Model-library/probe suites and exact selected-model browser proof. |
| `T1-12` | Context-window authority/presentation | Known limits, unknown limits, new-chat retention, and measured-request display without fabrication. | Context resolver/UI suites and the dated context-profile browser artifact. |

## Current result

The current Tier 1 evidence package is
[`../../QA/tier1-application-foundations-20260921/report.md`](../../QA/tier1-application-foundations-20260921/report.md),
with the canonical machine-readable ledger at
[`../../QA/tier1-application-foundations-20260921/ledger.json`](../../QA/tier1-application-foundations-20260921/ledger.json).

The exact tested revision is `loop-dev`
`c615c5799e1d5fb01e0af0eccaab5c6490d554c0`. The baseline is `PARTIAL`: the
backend and Angular regression suites pass, while state-render admission,
complete conversation hydration, synchronous live response timing, full job
API/shutdown coverage, current Settings browser assertions, and credential
failure boundaries still need explicit follow-up.

The two automated browser failures are retained as evidence, not hidden:

- `test_refresh_same_tab_restores_chat_and_map_state` restored the logical
  transcript/overlay state but did not expose a `.maplibregl-canvas` in the
  `ChromeHeadlessNoGpu` fixture. Re-run in a WebGL-capable browser or repair
  the fixture before promoting the renderer portion of `T1-02`.
- `TestChatFlow.test_settings_page_opens_from_toolbar` expects `role=tab`,
  while the current Settings sidebar exposes section buttons. Align the test
  with the current accessible contract before claiming automated `T1-09`
  completion; the rendered browser still verified all seven sections.

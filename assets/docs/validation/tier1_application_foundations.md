# Tier 1 application foundations

Last updated: 2026-09-22

Tier 1 is the application-foundation gate. It must establish that the shell,
state, persistence, realtime lifecycle, Settings, model selection, and context
presentation are trustworthy before Tier 2 agent or Tier 3 provider/rendering
claims are expanded.

## Slice checklist

| Slice | Capability | Required boundary | Primary regression evidence |
| --- | --- | --- | --- |
| `T1-01` | Navigation, route fallback, desktop gate | Direct and navbar routes, invalid-route redirect, and inert below-minimum viewport. | `app.routes.spec.ts`, `app.component.spec.ts`, wide/narrow browser proof. |
| `T1-02` | Frontend tab-local state | Valid reload, TTL, corruption, schema, tab isolation, and retained UI/map state. | Focused state/map Karma suite and [headed Chrome reload evidence](../../QA/tier1-validation-develop-20260922/T1-02/report.md). |
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

The 2026-09-21 baseline remains available at
[`../../QA/tier1-application-foundations-20260921/report.md`](../../QA/tier1-application-foundations-20260921/report.md),
with its machine-readable ledger at
[`../../QA/tier1-application-foundations-20260921/ledger.json`](../../QA/tier1-application-foundations-20260921/ledger.json).
That historical result was `loop-dev` at
`c615c5799e1d5fb01e0af0eccaab5c6490d554c0` and recorded 6 `PASS` and 6
`PARTIAL` slices.

The 2026-09-22 continuation records `T1-02` as `PASS` on the `develop`
working tree based at `8375fe071823e7f844f6bb125d86d6ebf36b3110`. Focused
Angular state/map tests passed 90/90, and the headed Chrome chat-state browser
file passed 8/8. See the [T1-02 report](../../QA/tier1-validation-develop-20260922/T1-02/report.md)
and [slice manifest](../../QA/tier1-validation-develop-20260922/T1-02/slice.json).
Tier 1 remains `PARTIAL`, now at 7 `PASS` and 5 `PARTIAL` slices across the
cited source boundaries; this roll-up is not a same-commit campaign result.

The 2026-09-21 headless run's missing `.maplibregl-canvas` remains historical
evidence; the current headed Chrome run verified the T1-02 reload and visible
map-control boundary. Its transparent tile fixture does not verify live
provider pixels or `map.render_ack`. The other retained browser failure,
`TestChatFlow.test_settings_page_opens_from_toolbar`, expects `role=tab` while
the current Settings sidebar exposes section buttons. Align that test with the
accessible contract before claiming automated `T1-09` completion.

## Next actionable slice

Continue with `T1-03` conversation lifecycle and history: create/list/search/
select/hydrate, pagination, unknown IDs, and cross-conversation isolation.
Keep the exact tested source boundary and isolated runtime paths in its QA
report.

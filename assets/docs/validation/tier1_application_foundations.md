# Tier 1 application foundations

Last updated: 2026-09-23

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
file passed 8/8. Its five source hashes remain the tested boundary in the
[T1-02 report](../../QA/tier1-validation-develop-20260922/T1-02/report.md)
and [slice manifest](../../QA/tier1-validation-develop-20260922/T1-02/slice.json);
those changes were subsequently committed at `35d04f8399d0166d1a134ad9f45931bc15efda91`.

The 2026-09-23 [T1-03 continuation](../../QA/tier1-validation-develop-20260923/T1-03/report.md)
passes focused conversation API/repository tests (9/9), the geospatial-page
Karma suite (47/47), and in-app Browser evidence for search, two-page history,
distinct conversation hydration, isolation, and stale-ID recovery. A focused
transcript top-spacing issue found during visual validation was repaired and
rechecked. Tier 1 remains `PARTIAL` at 8 `PASS` and 4 `PARTIAL` slices across
the cited source boundaries; this roll-up is not a same-commit campaign result.

The 2026-09-23 [T1-06 continuation](../../QA/tier1-validation-develop-20260923/T1-06/report.md)
passes the exact-lane live `/api/chat/turn` matrix (`200`, `202`, genuine
`409`, preflight `404`, and safe `503`), 14 focused API/OpenAPI tests, the
corrected 397-test backend CI selection, and exact-head hosted CI. Its live
terminal case exposed and fixed completed-event hydration of run-only and
omitted nullable fields. At the T1-06 source boundary, Tier 1 was `PARTIAL` at
9 `PASS` / 3 `PARTIAL`; the campaign then recorded 14 `PASS` / 3 `PARTIAL` /
51 `UNRUN`. These results retain their dated source boundaries.

The 2026-09-23 [T1-07 continuation](../../QA/tier1-validation-develop-20260923/T1-07/report.md)
passes the mounted job API and worker lifecycle cases (11/11 focused tests),
the full backend unit suite (918/918), and one successful live background job
on the exact `opencode-go / deepseek-v4.1-flash` lane. Cooperative shutdown
waited for active work to finish; after an official-launcher restart against
the same isolated runtime, the former job returned `404` for status, events,
and cancellation. Tier 1 is now `PARTIAL` at 10 `PASS` / 2 `PARTIAL`; the
campaign is 15 `PASS` / 2 `PARTIAL` / 51 `UNRUN`. The tested source boundary
is implementation commit `3fd0c820c2d4de0fb06120b6feac80b199d57f26`.

The 2026-09-21 headless run's missing `.maplibregl-canvas` remains historical
evidence; the current headed Chrome run verified the T1-02 reload and visible
map-control boundary. Its transparent tile fixture does not verify live
provider pixels or `map.render_ack`. The stale toolbar `role=tab` locator was
aligned with the Settings button contract in T1-09 and its focused browser
regression now passes.

The 2026-09-23 [T1-09 continuation](../../QA/tier1-validation-develop-20260923/T1-09/report.md)
passes the seven-section URL and rendered-panel flow, invalid-tab fallback,
Back/Forward restoration, draft retention, controlled save, and return/reopen
value check. The focused Settings component suite passed 31/31, the targeted
browser regressions passed 2/2, the toolbar regression passed 1/1, and the
Angular production build and exact-head hosted CI passed. Its tested source
boundary is implementation commit
`c090abd1ca9d6d78e82e798da9167b9d19b3fc23`. Tier 1 is now `PARTIAL` at
11 `PASS` / 1 `PARTIAL`; the campaign is 16 `PASS` / 1 `PARTIAL` / 51
`UNRUN`.

The 2026-09-23 [T1-10 continuation](../../QA/tier1-validation-develop-20260923/T1-10/report.md)
passes 38 focused backend credential/settings tests, 33 Settings Angular tests,
and five controlled browser regressions. The tests cover model and geospatial
credential masking, safe save/clear, blank and invalid drafts, unreadable
credentials, and failed updates. The model-card regression checks both PATCH
responses and confirms the final visible selected state. A missing success-path
change-detection call was fixed. T1-10 is `PASS` on
`develop@8e32f82e3f094e5fb17c3978fad69b9f80b7af0b`; Tier 1 is now 12/12
`PASS`, and the campaign is 17 `PASS` / 0 `PARTIAL` / 51 `UNRUN`.
Credentialed provider connectivity was not tested and remains a separate gate.

## Next actionable slice

Continue with `T2-01` and `T2-02`, the first core agent workflow slices. Their
2026-09-23 live attempt is `BLOCKED` because the official launcher did not
reach backend health; see the [current Tier 2 report](../../QA/tier2-validation-develop-20260923/report.md).
Preserve exact-location and no-fallback evidence boundaries. Tier 1 is 12/12
`PASS`; the full campaign remains `PARTIAL` with 2 slices `BLOCKED`, 49
`UNRUN`, and separate live/provider gates still open.

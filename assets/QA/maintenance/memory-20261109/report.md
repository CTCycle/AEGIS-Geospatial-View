# Memory audit and optimization — 2026-11-09

Branch `develop` at `bee400a6` plus the uncommitted changes listed below. Windows 11, Python 3.14, Chrome 156.

Method: two read-only code audits (backend, frontend), then before/after measurement of the changed paths. Every number is labelled **measured** or **estimated**.

## Where memory goes

Sizes in the local database (`data/database.db`, 2.2 GB on disk), as reported by the read-only backend audit (the file size was confirmed directly; per-table figures were not re-queried):

| Table / column | Size | Notes |
|---|---|---|
| `agent_run_events.payload_json` | 1.44 GB, 106k rows | `map_prepared` max 3.9 MB, `completed` max 3.6 MB; 11,340 checkpoint rows hold 687 MB |
| `chat_messages` JSON columns | about 460 MB | about 114 KB per message |
| `agent_evidence` | about 5 MB compressed, 1,043 rows | blob up to 16 MiB per row |

The Python process decodes whatever a query selects, so the dominant risk is queries that pull these columns when the caller needs a few small fields. Everything else on the backend that was audited (run lifecycle tasks, subscriber and outbound queues, per-conversation locks, the shared httpx client, the `agent_evidence` store, provider caches other than Overpass) is bounded and released. No ML models, embeddings or vector DB are loaded; the catalog is 1.6 MB, so startup eager loading is not a meaningful cost.

The frontend has no leaks: subscriptions, listeners, timers, the WebSocket and the `ResizeObserver` are released on destroy, and persisted state is `sessionStorage` only and small. Its cost is the MapLibre map (see "Remaining issues").

## Changes made

| # | Change | Files |
|---|---|---|
| 1 | Conversation snapshot selects only `role`, `content`, `created_at` instead of whole message rows. `list_messages` (one caller) became `list_message_headers`. | `repositories/chat_history.py`, `services/chat/history_service.py`, `services/chat/conversation_snapshot.py` |
| 2 | `AgentEvidenceRecord.payload_blob` is `deferred`, so `list_summaries` (called every agent turn, up to 100 rows) and `get_summary` stop loading blobs. `get_payload` still reads it explicitly. | `repositories/schemas/models.py` |
| 3 | Overpass response cache is bounded (64 entries) with an expiry sweep and oldest-first eviction, following the Open-Meteo cache pattern. It was unbounded and evicted only the entry being read. | `services/geospatial/overpass.py` |
| 4 | Final-response lookup (`read_completed_response`) reads the newest `completed`/`clarification_needed` event with a `LIMIT 1` query instead of decoding every event of the run. | `repositories/agent_run_events.py`, `services/agent_runs/events.py`, `services/agent_runs/lifecycle.py` |
| 5 | Chat message Markdown is parsed once per content change instead of on every change-detection pass. | `components/chat-message.component.ts` |
| 6 | `/geodata` and `/settings` are lazy-loaded. | `app.routes.ts` |

Tests added: message headers exclude payload columns; latest-event lookup order and visibility; Overpass cache bound and expiry; Markdown parsed once per content change. Existing tests were updated for the renamed method and the new lookup (`test_api_contracts.py`).

## Measured results — backend

Script: [memory_benchmark.py](memory_benchmark.py). It seeds a disposable SQLite database (31 MiB) and runs each scenario in a fresh process. Seeded sizes: 200 messages (100 assistant rows of about 224 KB across the three JSON columns), 100 evidence rows of 0.5 MiB uncompressed, and one run with 30 small events plus a 3.5 MB `map_prepared` and a 3.5 MB `completed` event. 5 repetitions per scenario. The synthetic data is sized to the production figures above, not copied from them, so it shows the shape of the effect, not production totals. Raw outputs: [baseline.json](baseline.json), [after.json](after.json) (both on `bee400a6`, before and with the working-tree changes).

`peak_alloc` is the tracemalloc peak of one pass (exact Python allocations). `rss_peak` is the process working-set peak (OS level, includes interpreter and imports of about 90 MiB).

| Scenario | peak_alloc before → after | rss_peak before → after | rss_delta over the run before → after |
|---|---|---|---|
| Snapshot message list (200 msgs) | 83.1 → 0.13 MiB | 183.5 → 90.8 MiB | +71.6 → 0.0 MiB |
| `list_summaries(limit=100)` | 10.34 → 0.40 MiB | 100.5 → 91.5 MiB | -1.2 → +0.1 MiB |
| Terminal-response lookup | 28.0 → 14.0 MiB | 119.9 → 105.0 MiB | +7.3 → +4.7 MiB |
| Event stream replay (unchanged) | 28.0 → 28.0 MiB | 120.9 → 121.1 MiB | +6.3 → +6.6 MiB |

The evidence-summary figures are for 0.5 MiB seeded payloads; the saving scales with blob size (up to 16 MiB per row in production), so production savings per turn can be larger.

The snapshot `rss_delta` of +71.6 MiB before the change means the process kept that much resident after repeated calls (allocator fragmentation after decoding large dicts), not only a transient peak.

Not measured: the Overpass cache fix (its effect depends on live traffic; covered by a bound-and-expiry unit test, no memory number claimed), and a live end-to-end run with the real 2.2 GB database and an LLM provider (no provider session was run; idle/peak/sustained process figures for the real server are therefore **not** measured).

## Measured results — frontend

| Measure | Before | After |
|---|---|---|
| Initial JS (production build), raw | 1.61 MB main (1.68 MB with CSS) | 1.09 MB main + two shared chunks = 1.49 MB total |
| Initial transfer (estimated by Angular) | 374.5 kB | 348.1 kB |
| Lazy chunks | none | settings 176 kB, catalog 11 kB (loaded only on those routes) |
| JS heap on the home route, no backend | 9.2 / 21.7 / 10.2 MB | 18.5 / 24.9 / 10.1 MB |

The initial bundle is **measured** 11% smaller. The heap figures are not a result: `performance.memory.usedJSHeapSize` swings by 2x between identical loads depending on when GC last ran, and there is no honest difference between the two builds. Home-route heap is **not** improved; the lazy chunks mainly cut download and parse cost, and the settings code never loads for users who stay on the map page. MapLibre and `marked` stay in the initial bundle because the default route needs them.

Markdown: the unit test asserts one `marked.parse` call across repeated change-detection passes. Allocation savings from that were not measured; that is **estimated** to grow with transcript length and streaming rate, not verified here.

## Validation

- Backend: `ruff check . ../tests` passes. Pyright reports 12 errors, all in `prompts/agent.py` (not modified; present before the change). Full unit suite: 1651 passed, 2 failed. The two failures (`test_all_tooling_resolves_disposable_state_under_canonical_cache_root`, `test_batch_entrypoint_reports_missing_powershell_without_cmd_parse_error`) fail identically on the unmodified baseline.
- Frontend: `ng test` 324 of 324 passed; production `ng build` succeeds.

## Evaluated and not changed

- **Event replay paging.** Paging `RunEventPublisher.events()` one row at a time was tried and reverted: peak allocation fell only from 28.0 to 25.4 MiB because a single decoded 3.5 MB event costs 14 MiB or more of Python objects and the consumer still holds the previous event. It added code to the SSE/WebSocket hot path for about 9%.
- **`maxTileCacheSize`.** MapLibre sizes its tile cache from the viewport by default; a fixed 64 could be larger than the default on small windows, and GPU/tile memory cannot be read from the page, so no change is justified without a measurement.
- **Image attachment duplicate (`dataUrl` + `base64`).** About 100–200 KB, cleared on send; not worth a change.

## Remaining significant issues

1. **Map GL memory** (frontend, largest remaining). `preserveDrawingBuffer: true` (`map-preview.component.ts:682`) keeps a backing buffer per map, and the previous map stays alive in `retainedPrevious` until the backend acknowledges the render, with no timeout, so two or three GL contexts can coexist. Fixing it touches the vision-capture flow; needs a measured GPU baseline.
2. **Large decoded events.** Run events and the stored `map_prepared`/`completed` payloads decode to 4–7x their JSON size. Avoiding it requires forwarding raw JSON without decoding, an architectural change.
3. **Checkpoint rows are never pruned.** 11,340 `checkpoint` events hold 687 MB of the database; this is mostly disk, but each write serializes and hashes the full run state. Pruning touches resume semantics.
4. **Evidence decode ceiling.** `get_payload` allows 16 MiB payloads that `json.loads` expands to 100–200 MB; `inspect_evidence` paginates only after the full decode.
5. **Smaller:** per-call LLM provider httpx clients (allocation churn, not a leak); `RenderCaptureStore.delete_for_run` has no caller (15-minute TTL bounds it); whole-file reads in ingestion downloads and the Mobility Database CSV; `land_mask` cache of 64 geometries; a cluster click handler on the map that is not removed with its layer (freed when the map is removed); chat transcript has no cap or virtualization.
6. **Live idle/peak/sustained process measurements** of the real server under agent turns were not taken. `psutil` is not installed; the sampling approach is `Get-Process` on the uvicorn PID (see the plan in the session) and is the first step for the next pass.

# Native remediation validation report

Date: 2026-09-15

## Scope and baseline

The attached architecture plan audited `develop` at
`c6809755e1ea2dafdc09e45f0f4c574d5327f04f`. The repository state immediately
before this remediation series was `4d55d16c` on `develop`. Changes were made
locally and committed incrementally; no push, main-branch synchronization,
tag, release, or pull request was performed. The pre-existing deletion of
`AGENTIC_PIPELINE_AUDIT.md` and pre-existing `app/assets/` work were preserved
out of scope.

## What the audit found and what was remediated

The audit's central conclusion was correct: the old branch still had multiple
execution modes, overlapping state/registry contracts, incomplete native
context and observations, weak recovery/discovery behavior, and inconsistent
completion and timeout boundaries. The remediation series addressed those
runtime gaps:

| Area | Remediation |
| --- | --- |
| Native architecture | Removed the legacy/shadow execution paths, parser/planner chain, migration response projections, and duplicate registry boundary. The application now boots one native loop, one registry, and one typed executor. |
| State and persistence | Made conversation-state and assistant-message persistence atomic, added canonical-state migration/backfill coverage, and persisted durable checkpoints/resume state. |
| Observation and recovery | Kept bounded discovery/evidence/provider metadata, samples/statistics, warnings, coverage, freshness, pagination, error/recovery fields, and valid-empty status in `ModelObservation`; recovery is returned to the loop for correction, replan, alternate source, retry, or clarification. |
| Discovery and manifests | Made empty deterministic shortlists enter manifest-driven discovery and aligned compound/recent aliases with schema-v2 execution contracts. |
| Goal/completion | Bound location, temporal, spatial, evidence, map, and final-response obligations to the native goal/completion contract. Undated `recent/latest/live/near_real_time` intent is normalized to `current`; explicit dated historical requests remain historical. |
| Provider execution | Server-owned route/goal binding now supplies location, bbox/radius, time fields, filters, and `live=true`; model arguments cannot override those invariants. |
| Map candidate | Bounded evidence payloads are converted to GeoJSON descriptors, validated temporal/spatial scope is carried onto overlays, and the render handshake retains last-known-good state with compare-and-swap semantics. |
| Public completion | A successful `map.render_ack` now atomically finalizes the durable assistant message and stores the committed candidate, preventing reloads from showing transient “awaiting render” text. |
| CI contract | Updated the workflow's capability/trajectory references to the current native test paths instead of deleted legacy tests. |

## Deterministic verification

Commands were run from the repository's existing environments:

- `app/server/.venv/Scripts/python.exe -m pytest ../tests/unit ../tests/agent_benchmark -q -p no:cacheprovider --basetemp C:\Users\Thomas V\AppData\Local\Temp\aegis-pytest-final-20260915` → **736 passed, 2 warnings**. The first retry using an `assets/QA` basetemp produced only pytest ACL cleanup/setup errors; it was not a product-test result.
- `app/server/.venv/Scripts/pyright.exe --threads 1` → **0 errors, 0 warnings, 0 informations**.
- `app/server/.venv/Scripts/ruff.exe check server tests` → **All checks passed** (the managed workspace emitted access-denied warnings for protected cache residue).
- `npm run build` → **Angular build succeeded**.
- `npm test -- --watch=false --browsers=ChromeHeadlessNoGpu` → **217 SUCCESS**. The test runner emitted its existing sanitizer warning and intentional `/x` 404 warning; no test failed.
- `pytest ../tests/e2e --collect-only -q -p no:cacheprovider` → **51 tests collected**.

## Live provider/browser evidence

The backend was restarted from the post-remediation tree on `127.0.0.1:7059`
and the official in-app browser used the running client on `127.0.0.1:4512`.
The configured lane was preserved exactly: provider `opencode-go`, model
`deepseek-v4-flash`, with a healthy stored credential. A structured probe passed
using the OpenAI-compatible chat-completions protocol.

Fresh browser request:

> Show recent earthquakes around Zurich on the map, then tell me what the data shows.

The final durable run was `run_aab8ee71207d4773944f3f3a8c5117c0` in conversation
`conv_cf772e7cddad45999b65718a60f84db4`. Correlated browser, API/log, and
SQLite evidence showed:

- Nominatim resolved `Zurich, District Zurich, Zurich, Switzerland`.
- The route and native goal both carried `temporal_scope.mode=current` and
  `granularity=recent`, with target `Zurich`.
- The server-bound overlay carried `temporal_mode=current`,
  `temporal_granularity=recent`, `analysis_scope=radius`, and
  `result_status=valid_empty` for `usgs_earthquakes`.
- The USGS result was a valid empty FeatureCollection (zero matching features),
  not a provider or transport failure.
- All eight completion requirements were `satisfied`: location resolved, data
  retrieved, temporal scope applied, spatial scope applied, map candidate
  prepared, map committed, viewport checked, and final response ready.
- The browser visibly showed the `USGS Earthquakes` clustered-points layer,
  the no-results explanation, USGS attribution, and the final assistant text:
  `The map is ready. No results were found in the requested area or time window.`
- Browser console diagnostics contained no warnings or errors. A browser reload
  preserved the final assistant text, resolved map, layer, and no-results state.

This run also exercised recovery: an initial model call supplied an extra
provider argument, the schema boundary rejected it with `correct_arguments`,
and the native loop continued to a valid provider request and successful map
completion.

## Remaining gates and honest conclusion

The plan's major runtime gaps are now covered in the tested native path, and
the live configured lane is materially more reliable and accurate than the
pre-remediation branch. That is not equivalent to production certification.

Remaining gates are explicit:

1. OpenAI Responses and Ollama provider-specific serialization/continuation
   still need live proof. OpenCode Go has the live probe and browser evidence
   above; no provider was silently substituted.
2. Hosted CI was not rerun after these local commits. The last exact-HEAD run
   (`34967001626`) failed its stale Pyright job before this remediation.
3. The broader browser/API E2E matrix was not run locally because its expected
   backend services on ports `8000` and `8001` were not listening. The
   controlled MapLibre handshake is proven, but it does not replace that
   service-backed matrix.
4. The live provider run is one request shape and one upstream snapshot. More
   varied live trajectories (including non-empty overlays, alternate providers,
   ambiguity, cancellation, steering, and follow-up turns) remain appropriate
   before claiming cross-provider production readiness.

Therefore: the original plan was **not fully covered at the old audit point**;
there were considerable gaps. After this remediation series, the core native
architecture and the configured OpenCode Go geospatial workflow are covered and
regressed locally, with external/provider matrix gates still open rather than
silently marked passed.

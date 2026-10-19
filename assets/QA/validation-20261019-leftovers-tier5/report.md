# 2026-10-19 leftover remediation and Tier 5 opening

Branch: `develop`. Starting SHA: `e81c2490` (clean). Tested source: that SHA plus the working-tree changes listed in [slice.json](slice.json) (committed afterwards; the commit SHA is recorded in the ledger).
Exact lane for live checks: `opencode-go / deepseek-v4.1-flash` (isolated disposable runtime on 127.0.0.1:5079, structured probe `passed`/`complete`, no fallback). The credential was resolved in-process and not written to these artifacts.

## Result summary

| Item | Result | Evidence |
| --- | --- | --- |
| F-13 point-scope raster exclusion (routing) | FIXED, routing only | `_concrete_scope_kind` now lowers `point` to `bbox` like the catalog handler. Regression test fails without the fix. Live API turn "Show the current precipitation radar at Naples, Italy." framed `point` scope and the shortlist now contains `rainviewer_precipitation_radar`; the prepared overlay is RainViewer ([summary](http/f13-radar-summary.json)). Model narration wording and browser acknowledgement were not exercised. |
| Imagery temporal/render-scope | FIXED + live PASS | `temporal_scope_applied` is vacuous when no evidence is required and no overlay exists (completion evaluator and render-completion override). Live `imagery_extent_rome`: `map_render_pass`, Esri World Imagery, verified ready ([screenshot](live/screenshots/ROUTE-MATRIX-LIVE/imagery_extent_rome.png)). Previously failed `temporal_scope_applied`. |
| Census tract timeouts | FIXED + live PASS | Cause confirmed by probe: Chicago tracts at full geometry took 20.4 s (10 s provider timeout). Query now caps `resultRecordCount=2000` and generalizes with `maxAllowableOffset=span/1000`: 1,047 tracts in 3.1 s through the provider. Live `census_demographics_chicago`: `map_render_pass`, TIGERweb attribution, overlay loaded and visible, 56 proxy requests all 200 ([screenshot](live/screenshots/ROUTE-MATRIX-LIVE/census_demographics_chicago.png)). Limit: the agent reported that `census_cartographic_boundaries` had no usable vector-tile render descriptor and rendered the TIGERweb boundary overlay instead; geometry only, no ACS demographic values. |
| F-25 elevation profile/contract mismatch | FIXED | `openmeteo_elevation` runtime profile now `supports_map:false`; new auditor rule `profile_claims_unrenderable_map_support` (test added). Strict production audit: 86 manifests, 0 errors, 0 warnings. Numeric elevation stays disabled by licence/opt-in (`AEGIS_ALLOW_RESTRICTED_SOURCES`); that is a product decision, not a defect. |
| Failed-materialization rollback | FIXED | `execute_ingestion_plan` removes files and directories created by a failed run and restores files a failed re-run overwrote. Tests: checksum, `minFeatureCount` and bbox failures leave no artifacts; a failed re-ingestion restores the previous materialization byte for byte. |
| Heavy-format behavior | FIXED (code now matches docs) | Shapefile/parquet/JSON manifests declare `minFeatureCount: 1` and previously raised; with no normalizer the run now keeps the raw artifact and reports `partial` health as documented. Test added. T4-03 stays PARTIAL: no normalizers and optional packages are absent. |
| T5 malformed input (reconstructed) | PASS after fix | 15-case API probe on an isolated backend: invalid JSON, empty/typed/null bodies, wrong content type, unknown conversation/run/job/layer, bad bbox all returned 4xx with safe bodies and the server stayed healthy ([probe](http/malformed-input.json)). Defect found and fixed: an over-long message (>12,000 characters) returned **404** with a raw pydantic error (the handler's `except ValueError` swallowed `ValidationError`). It now returns **422** with a sanitized `message is too long` detail ([after fix](http/oversize-message-after-fix.json)); regression test added. |
| T5 ack identity / failed-render recovery / races / cancellation (reconstructed) | PASS | Controlled-fault module at the current head: 10 passed ([log](logs/controlled-fault-module.log), [scenario reports](reports/)). Backend subset (render completion, agent runs, agent loop v2, native trajectories, tool parse errors, chat contracts, job API): 138 passed ([log](logs/tier5-backend-subset.log)). The controlled evidence records the starting SHA, not the working-tree edits. |

## Quality gates (final working tree)

- Full backend unit suite: **1,128 passed** ([log](logs/full-unit-final.log)). An earlier run failed `test_canonical_runtime_contract` only because this task's own ruff run had created a stray repo-root `.ruff_cache`; it was removed and the suite is clean.
- Ruff: all checks passed ([log](logs/ruff.log)). Strict Pyright: 0 errors, 0 warnings, 0 informations ([log](logs/pyright.log)). Strict production manifest audit: 86/0/0.
- Frontend sources were not changed, so Angular build/Karma were not rerun.

## Not covered, and why

- F-19 (explicit USGS time ranges): needs a contract and adapter redesign, not a surgical fix. Stays open.
- Overpass reliability: external capacity plus a design change (mirrors/retry); only provable live. Stays open.
- T4-03: normalizers unimplemented. T4-05/T4-06: no real configured source; a synthetic fixture would prove mechanism only. T4-07: OpenTripMap has no key.
- T4-09 to T4-13: only OpenCode Go has a live lane; OpenAI, Google, DeepSeek/OpenCode Zen and Ollama have no approved credentials or local server. T5-11 depends on them.
- T5-04/05/06 need new fixtures; T5-09/10 have no authored performance or accessibility contract; T5-13 has no recorded theme; T5-12 later passed: GitHub Actions run 39212579230 on pushed `c0da6dc7` (all four jobs).
- Tier 5 mapping is a reconstruction at LOW confidence (no original per-ID text exists); the 12-theme/13-ID mismatch is still unresolved.

## Cleanup

Task-owned backend, frontend, keeper runtime and browser contexts stopped; ports 5079, 5080, 8000, 8001, 4512, 7059 and 9876 verified free; disposable runtime and temp pytest directories removed. Probe scratch script lived in the session scratchpad.

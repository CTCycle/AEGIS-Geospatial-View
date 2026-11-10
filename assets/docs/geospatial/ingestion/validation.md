# Validation

Last updated: 2026-11-03

The ordered long-term campaign is documented in the
[comprehensive validation strategy](../../validation/strategy.md). The current
application-foundations hand-off is the
Tier 1 validation record;
its statuses are intentionally separate from this document's provider and
ingestion contracts.

## Static Validation

```powershell
cd app
.\server\.venv\Scripts\python.exe -m server.services.geospatial.layer_auditor --strict
.\server\.venv\Scripts\python.exe -m server.services.geospatial.layer_auditor --strict --production
```

The audit fails on missing schema-v2 metadata, invalid geometry claims, unsafe secret-like values, or incomplete production coverage.

## Backend Contract Tests

Focused coverage includes:

- manifest schema-v2 loading
- provider registry binding
- timeout, retry, and circuit-breaker behavior
- provider payload normalization
- geospatial API contracts
- camera detail and missing-key behavior
- agentic selection and policy gates
- dataset-ingestion execution and validation
- hazard legends, freshness labels, and safe failure states

## Frontend Validation

```powershell
npm --prefix app/client run build
npm --prefix app/client test -- --watch=false --browsers=ChromeHeadlessNoGpu
```

Frontend validation covers schema-v2 types, geospatial API helpers, services, capability catalog behavior, source-health display, camera popup behavior, and renderer dispatch.

## Browser Validation

Major renderer changes require browser validation covering:

- basemap-only sessions
- missing-credential states
- raster descriptor rendering
- mocked vector payload rendering
- webcam missing-key and mocked camera payloads
- capability catalog filtering and source-health display

## CI And Live Validation

CI should run:

- strict auditor
- focused geospatial unit contracts
- client build and test suite
- geospatial browser-smoke command
- frontend E2E/browser renderer checks under `app/client/src/app/e2e`

Live-provider validation should run outside deterministic CI when network access is available:

```powershell
cd app
.\server\.venv\Scripts\python.exe -m server.services.geospatial.live_validator --strict
.\server\.venv\Scripts\python.exe -m server.services.geospatial.live_validator --strict --include-credentialed
```

The validator is the canonical provider smoke matrix. It contains exactly one
declarative case for every provider factory entry and classifies each case as
public, credentialed, configured-source, or configuration-dependent. Missing
credentials or sources are `SKIP`; transport failures, provider error payloads,
and malformed semantic payloads are `FAIL`. Reports should be retained by the scheduled workflow without including secrets; locally, scripts write run output under the unversioned `assets/QA/`.

Live validation classifies upstream timeouts, rate limits, malformed responses,
and missing credentials as provider availability failures. A failed provider
probe is not a successful POI, layer, or map-render result; retain the last
known-good map state and report the actionable warning.

## Live Model Evaluation

CI proves deterministic behaviour only (the scripted trajectory gate and the scenario-matrix validator). Model behaviour is measured by `scripts/benchmarks/live_model_eval.py`, which runs the `model_in_loop` scenarios of `scenario_matrix.v1.json` and the holdout set against a running backend with a chosen provider and model, then grades each run from its public trace (`app/tests/agent_benchmark/live_grading.py`): route family and resolved targets, tool sequence, termination and deadline, evidence provenance, final-answer consistency (`check_final_answer`), render verdict and a false-success flag.

```powershell
# backend: from app/, FASTAPI_PORT=5013 server\.venv\Scripts\python.exe -m uvicorn server.app:app --host 127.0.0.1 --port 5013 --ws-max-size 65536 --ws-ping-interval 15 --ws-ping-timeout 10
app\server\.venv\Scripts\python.exe scripts\benchmarks\live_model_eval.py `
  --provider opencode-go --model deepseek-v4.1-flash --output-dir assets\QA\<folder>
```

- Default mode drives the UI with Playwright (reusing `app/tests/e2e/helpers`), so a real browser acknowledges renders and the render verdict is verified. `--no-render` drives the realtime WebSocket protocol instead, cancels each run once its map is prepared and records render as `unverified`; the final answer is then not graded. Use it where no browser is available (CI); multi-turn follow-ups that depend on a rendered map are only faithful in browser mode.
- `--scenario id1,id2`, `--limit N` and `--matrix main|holdout|both` narrow the run. Do not point it at a backend whose agent code is being edited.
- Credentials come only from the app's stored settings or from the environment variable named by `--api-key-env` (default `AEGIS_EVAL_API_KEY`), which is written to the app's encrypted credential store. Without a key the run exits `3` (skipped). Exit codes: `0` gate passed, `1` gate failed, `2` infrastructure error.
- Outputs per model under `--output-dir/<provider>-<model>/`: `results.json`, `summary.md`, `traces/` and (browser mode) `screenshots/`. They are local scratch under `assets/QA/`; summarize findings in the docs and delete the folder.
- Baseline: `app/tests/agent_benchmark/live_eval_baseline.v1.json`, keyed `provider/model`. The gate fails on any false success, on a scenario that passed in the baseline and now fails, and on a failing scenario without a documented `explanation`. A model without a baseline entry is gated on false successes only. Record one with `--write-baseline`, then fill in every failing scenario's `explanation` and review the diff.
- The route family check maps capability ids to families with the patterns in `FAMILY_PATTERNS`; extend them when new capabilities are added.
- The exact-lane browser tests (`tests/e2e/helpers/model_capability_metadata.py`) target `opencode-go / deepseek-v4.1-flash` by default; set `APP_TEST_LANE_PROVIDER` and `APP_TEST_LANE_MODEL` to run them against another configured model.
- `.github/workflows/live-model-eval.yml` runs the evaluator per model weekly and on `workflow_dispatch` with `--no-render`. Each model reads its key from a repository secret named in the workflow matrix; a model without its secret is skipped, not failed. Reports are uploaded as artifacts.

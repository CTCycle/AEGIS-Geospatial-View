# T1-10 Credential Lifecycle and Settings Follow-through

Date: 2026-09-23

Slice result: `PASS`

Implementation commit: `develop@8e32f82e3f094e5fb17c3978fad69b9f80b7af0b`

Baseline: `develop@7e93d2080668043b6a021de723c8b6e7717fa6f0`

## Evidence boundary

The Settings credential UI, credential service, API parser, and backend settings
service were checked with synthetic credentials and controlled responses. No
real credential was entered, transmitted to a provider, or recorded in this
report. The browser fixture keeps credential updates in memory and returns only
credential-presence and health metadata. Backend tests cover repository and
encryption behavior independently.

The model-selection fixture now returns a contract-valid
`selected_model_context` whose provider and model match the selected settings.
The browser regression waits for both keyboard-triggered PATCH responses and
checks the returned context and completed visible status. That check does not
reclassify or expand the full T1-11 gate.

The browser regression also exposed a UI refresh defect: after a successful
model selection, the optimistic selected card was correct while the footer
continued to show “Selecting…”. The success path now requests change detection
after updating the saved settings and completion status. The rendered test
asserts the final “Selected…” state.

## Credential scenarios

| Scenario | Result |
| --- | --- |
| Model provider: blank draft, invalid key, unreadable saved key | Blank and invalid drafts make no PATCH; unreadable state is clearly shown with an empty password field. |
| Model provider: safe save, clear, reload | Synthetic OpenAI key is accepted, the draft is cleared, the saved-key health is shown, and a later clear remains cleared after reload. |
| Model provider: API failure | Failed save and clear show the controlled error, retain the saved state/draft, and never show a successful-save or successful-clear status. |
| Geospatial: safe save, blank draft, clear, reload | Synthetic TomTom key is accepted, masked and cleared from the draft; blank saves do not mutate state; explicit clear persists after reload. |
| Geospatial: API failure | Failed save and clear preserve the readable saved state and masked draft and do not show success statuses. |
| Model-card selection regression | Both Enter and Space responses return `selected_model_context.model == agent_model_name == "gpt-5-mini"`; the rendered selection and completion status agree. |

The seven retained captures are in [screenshots](screenshots/). The password
fields are blank after successful saves and show only masked dots while a draft
is pending after a failed request. Test assertions also verify that fixture key
text is absent from rendered output.

## Local validation

All commands ran against the exact implementation commit above. Test runtime
data used `runtimes/cache/test-runtime/t1-10-20260923`; pytest used the isolated
`runtimes/cache/pytest-tmp/t1-10-20260923` basetemp. The pre-existing frontend
on port 4512 was left running. A task-owned backend on port 7059 used the
isolated data root and was stopped after validation. The test runner skipped
automatic server management to avoid its broad configured-port cleanup.

| Gate | Result | Command / boundary |
| --- | --- | --- |
| Backend credential/settings tests | `PASS` — 38 passed, 880 deselected, 2 non-failing dependency deprecation warnings | `STANDARD_TEST_PYTEST_TARGET=app\tests\unit`; `run_tests.bat -k "credential or settings_response_reports_credential_health" --basetemp runtimes\cache\pytest-tmp\t1-10-20260923` |
| Controlled Settings browser regressions | `PASS` — 5 passed, 7 deselected | `STANDARD_TEST_PYTEST_TARGET=app\tests\e2e\test_settings_regressions.py`; standard runner with the five named tests, `--browser-channel chrome`, and the isolated basetemp. Chrome 154, 1366×768 viewport. |
| Settings Angular suites | `PASS` — 33/33 | `npm run test -- --watch=false --browsers=ChromeHeadlessNoGpu --include src/app/pages/settings-page.component.spec.ts --include src/app/components/settings-api-key-field.component.spec.ts` from `app/client`. |
| Ruff on changed E2E file | `PASS` | `ruff check --no-cache app/tests/e2e/test_settings_regressions.py` |
| `git diff --check` | `PASS` | Clean at implementation commit. |

The focused E2E selection was:

```text
model_card_selects_the_single_agent_model
model_provider_unreadable_key_and_failed_updates_are_safe
model_provider_credential_safe_save_clear_and_reload
geospatial_credential_safe_save_clear_and_reload
geospatial_credential_failed_updates_preserve_saved_state
```

## Rendered browser review and limitations

The Codex in-app Browser opened `/settings`, but its available viewport was
below the application’s 1024 px desktop minimum and therefore showed the
intended resize gate. The controlled Playwright fixture could not be installed
in that tab, so the saved user-facing review uses the real rendered Chrome
screenshots at 1366×768 instead. Those captures show masked credentials,
readable/unreadable state, explicit errors, and the selected model after its
save completes.

Provider connectivity and credential validity were not exercised: the
credential API calls were controlled fixtures. OpenAI/Ollama parity and
credentialed/local source access remain separately `BLOCKED`. The broader
T1-11 model-library/probe gate was not rerun by this single selection check.

Other open gates remain unchanged: `ROUTE-LIVE`, `CONTROLLED-FAULT`,
`LIVE-DIARY-20260919`, `LIVE-HYD-20260920`, `LIVE-API`, and `MATRIX-22` are
`PARTIAL`; `GEO-HYD-05/06` remain `BLOCKED`; raster rendering and the FEMA
coverage-guardrail rerun remain unresolved. Dataset ingestion remains
unvalidated.

## Hand-off

`T1-10` is `PASS`. Tier 1 is now 12/12 `PASS`; the campaign roll-up is 17
`PASS`, 0 `PARTIAL`, and 51 `UNRUN` of 68 slices. The overall campaign remains
`PARTIAL` because downstream validation is incomplete. Continue with `T2-01`.
Exact-head hosted CI passed all four jobs for implementation commit
`8e32f82e3f094e5fb17c3978fad69b9f80b7af0b`; see [run 35891289442](hosted-ci.md).

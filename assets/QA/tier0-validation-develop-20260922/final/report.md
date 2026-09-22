# Tier 0 exact-head reconciliation

Date: 2026-09-22

## Boundary

- Branch: `develop`
- Starting HEAD: `7e8b10d58aebf21f194a74bcc2307f9d8e08f15c`
- `origin/develop` matched that starting SHA before the run.
- Validated source commit: `afa608c8d5c53a34d0ce8da36e5fe5f47f689145`, now
  pushed to `origin/develop`. The follow-up documentation-only commit may
  change the repository HEAD without changing the tested application source.
- All application-startup, migration, and pytest data used isolated locations
  below `runtimes/cache/test-runtime` and `runtimes/cache/pytest*`.
- The user's normal `app/resources/runtime/database.db` was restored and
  verified on `cloud / opencode-go / deepseek-v4.1-flash` with no custom
  DeepSeek URL. No validation service was left running.

## Final regression sweep

| Boundary | Result |
| --- | --- |
| Ruff repository gate | PASS — all checks passed; protected-cache warnings only |
| Strict Pyright | PASS — 0 errors, 0 warnings, 0 informations |
| Python source compilation | PASS — 410 files |
| Frontend state helper | PASS — 19 tests |
| Angular production build | PASS — bundle generated in 6.896 seconds |
| Angular/Karma | PASS — 248/248 Chrome Headless tests |
| T0-02 Alembic upgrade/check/current-heads | PASS — `202609210001 (head)` |
| T0-02 migration/persistence regression | PASS — 25 tests |
| T0-03 legacy Settings/runtime regression | PASS — 44 tests |
| T0-04 startup/backend/helper/harness regression | PASS — 36 backend tests, 19 helper tests, harness PASS |
| T0-05 API/composition/OpenAPI regression | PASS — 44 tests |
| Process cleanup | PASS — ports 7059, 4512, and 9876 free |

Warnings were limited to the existing Starlette/httpx deprecation, Google's
Python 3.17 deprecation notice, Angular Karma builder deprecation, and normal
Angular sanitizer test diagnostics. None changed an exit status.

## Campaign reconciliation

The five Tier 0 slices are now `PASS` on the same source boundary. The 68-slice
campaign therefore moves from 8 PASS / 6 PARTIAL / 54 UNRUN to **11 PASS / 6
PARTIAL / 51 UNRUN**. Tier 0 is `PASS`; the overall campaign remains `PARTIAL`
because Tier 1 partial rows and downstream live/browser/provider/hosted-CI
boundaries remain open.

The hosted workflow result for the eventual pushed commit is intentionally not
inferred from local evidence. Live geospatial/provider gaps, controlled
supersession ordering, and the complete scenario matrix remain separate from
this Tier 0 result.

## Evidence index

- [T0-03 report](../T0-03/report.md)
- [T0-04 report](../T0-04/report.md)
- [T0-05 report](../T0-05/report.md)
- [static, frontend, and Alembic logs](./)
- [migration regression log](final/migration-regression.log)

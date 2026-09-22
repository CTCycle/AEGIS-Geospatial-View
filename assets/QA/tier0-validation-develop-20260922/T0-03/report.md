# T0-03 legacy Settings migration evidence

Status: `PASS`

## Boundary

- Branch: `develop`
- Starting HEAD: `7e8b10d58aebf21f194a74bcc2307f9d8e08f15c`
- Validation source: working tree based on that exact HEAD; the validation
  changes are the focused test-isolation, contract-test, and launcher safety
  changes recorded in the final commit.
- Python: `app/server/.venv/Scripts/python.exe` (Python 3.14)
- Data boundary: `runtimes/cache/test-runtime/tier0-validation-develop-20260922/T0-03-final/data`
- Pytest boundaries: `runtimes/cache/pytest` and
  `runtimes/cache/pytest-tmp/tier0-validation-develop-20260922-T0-03-final`
- The normal `app/resources/runtime/database.db` was not used by the final
  T0-03 run. Its provider row was separately verified as
  `opencode-go / deepseek-v4.1-flash` after an earlier test-isolation defect
  was corrected.

## Coverage and result

The final focused command covered:

```text
pytest
  tests/unit/test_configuration_management.py
  tests/unit/test_database_initialization_policy.py
  tests/unit/test_runtime_settings_api.py
  tests/unit/test_sqlite_application_startup.py
  tests/unit/test_runtime_env_loading.py
  tests/unit/test_database_configuration.py
  tests/unit/test_model_settings_repository.py
  tests/unit/test_llm_settings_repository.py
  -q --basetemp runtimes/cache/pytest-tmp/tier0-validation-develop-20260922-T0-03-final
  -o cache_dir=runtimes/cache/pytest
```

Result: **44 passed, 2 warnings, 3.88 seconds**.

The matrix exercised fresh no-legacy seeding and restart idempotency, complete
legacy import with the canonical `agent_execution` default, commit-before-file
retirement ordering, malformed/non-object/missing/unknown/invalid legacy input,
commit rollback, retirement failure after commit, canonical-row precedence, and
the runtime Settings GET/PATCH/validation/masking contract. No invalid input
silently fell back to defaults or overwrote canonical persisted data.

## Remediation

The startup tests now reset the process-wide environment bootstrap state before
and after each isolated application lifespan and assert that the injected
provider test database is below its temporary data root. This prevents a
previous TestClient from redirecting a later test to the user's normal runtime
database. No production migration or repository fallback behavior was changed.

## Evidence

- [final pytest log](pytest-final.log)
- [T0-04 startup log with the same isolation regression](../T0-04/backend-focused-retry.log)

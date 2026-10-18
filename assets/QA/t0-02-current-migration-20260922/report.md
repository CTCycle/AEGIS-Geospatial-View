# T0-02: Current SQLite migration and schema validation

- **Status:** PASS
- **Date:** 2026-09-22
- **Target:** `develop` at `664f1beb69f17063f5f9e1deb0f38cdc4a5596c3`
- **Runtime:** Windows; Python 3.14.7; uv 0.12.13; `app/server/.venv`
- **Isolated data root:** `runtimes/cache/test-runtime/t0-02-20260922-664f1be/`

## Revision and worktree boundary

At the start of validation, `git status --short --branch` reported
`## develop...origin/develop`. Git also printed access-denied warnings while
traversing pre-existing ignored pytest-cache directories; no tracked changes
were shown. The exact HEAD remained `664f1beb69f17063f5f9e1deb0f38cdc4a5596c3`
through the run. The T0-01 commit `5bb8d416da80e33a7e85b02538f605ee22aee0a5`
is an ancestor of this `develop` HEAD. No application source was changed for
this slice; this report, its [probe script](probe_supported_upgrade.py), and
the linked status documentation are in the change set.

Every Alembic, production-initializer, and test command used an isolated
`AEGIS_DATA_DIR` beneath the data root above. The normal application database
was not used. Pytest used the repository-required cache locations under
`runtimes/cache/pytest` and `runtimes/cache/pytest-tmp`.
The task-specific test-runtime and pytest temporary directories were removed
after collecting the evidence; the report and probe remain under `assets/QA`.

## Migration topology

Commands were run from `app/server` with `AEGIS_DATA_DIR` set to the isolated
`topology` directory. The venv executable was `app/server/.venv/Scripts/python.exe`:

```powershell
python -m alembic -c alembic.ini heads
python -m alembic -c alembic.ini history --verbose
python -m alembic -c alembic.ini branches
python -m alembic -c alembic.ini current
```

`heads` returned exactly one head: `202609210001`. `history --verbose`
returned the complete ten-revision chain with no duplicate or missing parent:

```text
202608200001 -> 202608310001 -> 202609050001 -> 202609050002
-> 202609090001 -> 202609090002 -> 202609140001 -> 202609150001
-> 202609170001 -> 202609210001
```

`branches` returned no branchpoints. `current` on the separate empty topology
database reported no current revision, as expected before its first upgrade.
The current migration declares `202609170001` as its parent and
`202609210001` as its revision.

## Fresh schema, seeds, and already-current startup

The direct fresh-file sequence ran with `AEGIS_DATA_DIR` set to the isolated
`fresh` directory, from `app/server`:

```powershell
& .\.venv\Scripts\python.exe -m alembic -c alembic.ini upgrade head
& .\.venv\Scripts\python.exe -m alembic -c alembic.ini check
& .\.venv\Scripts\python.exe -m alembic -c alembic.ini current --check-heads
```

Alembic upgraded all ten revisions;
`alembic check` returned `No new upgrade operations detected`, and
`current --check-heads` returned `202609210001 (head)`.

For application seeding and restart idempotency, a second empty SQLite file
used `AEGIS_DATA_DIR` under `fresh-seeds`. It was upgraded and checked with the
following commands:

```powershell
$repo = 'G:\Projects\Repositories\Active projects\AEGIS Geospatial View'
$env:AEGIS_DATA_DIR = Join-Path $repo 'runtimes/cache/test-runtime/t0-02-20260922-664f1be/fresh-seeds'
$env:PYTHONPATH = 'app'
uv run --project app/server python -m alembic -c app/server/alembic.ini upgrade head
uv run --project app/server python assets/QA/t0-02-current-migration-20260922/probe_supported_upgrade.py fresh-seeds
```

The production initializer probe found 17 application tables plus
`alembic_version`:

```text
agent_evidence, agent_run_events, agent_runs, agent_steering_messages,
application_runtime_settings, chat_messages, conversations,
credential_encryption_materials, model_credentials, model_provider_settings,
reference_countries, reference_country_aliases,
reference_geospatial_layer_aliases, reference_geospatial_layer_keywords,
reference_geospatial_layers, reference_gibs_layer_defaults,
reference_gibs_tile_matrix_sets
```

Required data was present: one credential-encryption material row, one
application runtime settings row, required model settings, and 249 reference
country rows. A second production initialization remained at head, applied no
migrations, and left all seed counts unchanged.

## Upgrade from the supported previous revision

The immediate previous revision `202609170001` was created from a fresh schema,
seeded, downgraded to that supported revision, and populated with a
representative conversation state and model settings. The production runner
then applied the pending migration:

```powershell
$env:AEGIS_DATA_DIR = Join-Path (Get-Location) 'runtimes/cache/test-runtime/t0-02-20260922-664f1be/previous-upgrade'
& .\app\server\.venv\Scripts\python.exe assets/QA/t0-02-current-migration-20260922/probe_supported_upgrade.py supported-upgrade
```

`MigrationResult` started at `202609170001`, ended at `202609210001`, and
reported `migrations_applied=True`. The conversation ID, active directive,
summary and summary index, resolved Zurich location, model settings, and active
credential-encryption material were preserved. The 249 reference-country rows
remained present, the new runtime-settings seed was created, SQLite reported no
foreign-key violations, and the migration backup was removed after success.

## Failure and recovery

The recovery probe added a conflicting table at the previous revision to
force the current migration's `CREATE TABLE` operation to fail. The production
runner reported `OperationalError` and restored its backup. A canonical logical
snapshot of schema definitions and ordered rows was identical before and after
recovery; the stored revision remained `202609170001`, the conflict marker
remained intact, and no migration backup remained:

```powershell
$env:AEGIS_DATA_DIR = Join-Path (Get-Location) 'runtimes/cache/test-runtime/t0-02-20260922-664f1be/failed-recovery-logical2'
& .\app\server\.venv\Scripts\python.exe assets/QA/t0-02-current-migration-20260922/probe_supported_upgrade.py failed-recovery
```

```text
logical_snapshot_sha256_before=f3ab3f4a8ba0d2e43b087bd3b99e687f032f654f4e7b36ddb5649ab70331f7b1
logical_snapshot_sha256_after=f3ab3f4a8ba0d2e43b087bd3b99e687f032f654f4e7b36ddb5649ab70331f7b1
schema_and_all_rows=PASS; conflict_marker=preserved; migration_backups=0
```

## Regression suite and CI migration commands

The migration/persistence regression command was:

```powershell
$repo = (Get-Location).Path
$runtime = Join-Path $repo 'runtimes/cache/test-runtime/t0-02-20260922-664f1be/regression-suite'
$cache = Join-Path $repo 'runtimes/cache/pytest'
$base = Join-Path $repo 'runtimes/cache/pytest-tmp/t0-02-20260922-664f1be'
$env:AEGIS_DATA_DIR = $runtime
$env:PYTHONPATH = 'app'
uv run --project app/server python -m pytest -c app/server/pyproject.toml `
  app/tests/unit/test_sqlite_application_startup.py `
  app/tests/unit/test_database_initialization_policy.py `
  app/tests/unit/test_database_configuration.py `
  app/tests/unit/test_sqlite_repository.py `
  app/tests/unit/test_persistence_conformance.py `
  -q -o "cache_dir=$cache" --basetemp "$base"
```

With `PYTHONPATH=app` and an isolated `AEGIS_DATA_DIR`, the result was **21
passed**. The policy tests passed for unknown revisions, populated unversioned
databases, corrupt SQLite files, seed repair, and restoration after a seeding
failure. The native-state regression also passed its conversation, model
settings, and encryption-material preservation assertions. Two dependency
deprecation warnings were reported: Starlette's `TestClient` httpx integration
and Google's use of `_UnionGenericAlias`.

The three CI Alembic metadata commands were also run with a separate fresh
isolated database, matching `.github/workflows/ci.yml`:

```powershell
$env:AEGIS_DATA_DIR = Join-Path (Get-Location) 'runtimes/cache/test-runtime/t0-02-20260922-664f1be/ci-migration'
$env:PYTHONPATH = 'app'
uv run --project app/server python -m alembic -c app/server/alembic.ini upgrade head
uv run --project app/server python -m alembic -c app/server/alembic.ini check
uv run --project app/server python -m alembic -c app/server/alembic.ini current --check-heads
```

All three passed; the final command returned `202609210001 (head)`.

## Conclusion and next slice

`T0-02` is **PASS** on `develop@664f1beb69f17063f5f9e1deb0f38cdc4a5596c3`.
Fresh creation, the supported prior revision, already-current initialization,
unknown and unversioned revisions, corrupt database handling, migration
failure recovery, seed behavior, and schema constraints are covered by the
isolated probes and the five regression files. Tier 0 remains `PARTIAL` because
`T0-03`, `T0-04`, and `T0-05` remain `UNRUN`; `T0-03` is next.

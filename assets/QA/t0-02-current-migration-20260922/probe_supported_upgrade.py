"""Run isolated supported-upgrade and migration-recovery probes for T0-02."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sqlite3
import sys
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPOSITORY_ROOT / "app"))

from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from sqlalchemy import inspect, select  # noqa: E402

from server.configurations import DatabaseSettings  # noqa: E402
from server.repositories.database.initializer import initialize_database  # noqa: E402
from server.repositories.database.migration_runner import (  # noqa: E402
    ALEMBIC_CONFIG_PATH,
)
from server.repositories.database.sqlite import SQLiteRepository  # noqa: E402
from server.repositories.credential_material import (  # noqa: E402
    CredentialEncryptionMaterialRepository,
)
from server.repositories.model_settings import ModelSettingsRepository  # noqa: E402
from server.repositories.schemas.models import (  # noqa: E402
    ApplicationRuntimeSettingsRecord,
    ConversationRecord,
    CredentialEncryptionMaterial,
    ModelProviderSettingsRecord,
    ReferenceCountryRecord,
)
from server.services.catalog.startup import seed_reference_catalog  # noqa: E402

PREVIOUS_REVISION = "202609170001"
CURRENT_REVISION = "202609210001"
CONVERSATION_ID = "t0-02-upgrade-preservation"
CONVERSATION_STATE = {
    "active_directives": [
        {"text": "Preserve migration probe context", "created_turn_index": 2}
    ],
    "summary": {"summary": "Earlier migration probe analysis"},
    "summary_through_turn_index": 6,
    "resolved_locations": {
        "active_location": {
            "label": "Zurich",
            "latitude": 47.3769,
            "longitude": 8.5417,
            "source": "t0-02-validation",
            "confidence": 1.0,
        }
    },
}


def _database() -> tuple[SQLiteRepository, Path]:
    data_dir_value = os.environ.get("AEGIS_DATA_DIR", "").strip()
    if not data_dir_value:
        raise RuntimeError("AEGIS_DATA_DIR must point to an isolated test directory")
    data_dir = Path(data_dir_value).resolve()
    if "test-runtime" not in data_dir.parts:
        raise RuntimeError(f"Refusing non-test database path: {data_dir}")
    database_path = data_dir / "database.db"
    return (
        SQLiteRepository(DatabaseSettings(database_path=str(database_path))),
        database_path,
    )


def _current_revision(database: SQLiteRepository) -> str:
    with database.engine.connect() as connection:
        return str(
            connection.exec_driver_sql(
                "SELECT version_num FROM alembic_version"
            ).scalar_one()
        )


def _downgrade(database: SQLiteRepository) -> None:
    config = Config(str(ALEMBIC_CONFIG_PATH))
    with database.engine.connect() as connection:
        config.attributes["connection"] = connection
        command.downgrade(config, PREVIOUS_REVISION)
        connection.commit()


def _model_settings_snapshot(database: SQLiteRepository) -> tuple[object, ...]:
    with database.session() as session:
        row = session.execute(
            select(ModelProviderSettingsRecord).order_by(
                ModelProviderSettingsRecord.id.asc()
            )
        ).scalars().first()
        if row is None:
            raise AssertionError("model provider settings were not seeded")
        return (
            row.id,
            row.active_provider_mode,
            row.agent_model_provider,
            row.agent_model_name,
            row.ollama_url,
            row.openai_base_url,
            row.google_base_url,
            row.deepseek_base_url,
        )


def _encryption_snapshot(database: SQLiteRepository) -> tuple[object, ...]:
    material = CredentialEncryptionMaterialRepository(database).get_active_material()
    if material is None:
        raise AssertionError("credential encryption material was not seeded")
    return (material.id, material.key_purpose, material.key_version, material.key_material)


def _seed_counts(database: SQLiteRepository) -> dict[str, object]:
    return {
        "credential_encryption_materials": database.count_records(
            CredentialEncryptionMaterial
        ),
        "reference_countries": database.count_records(ReferenceCountryRecord),
        "application_runtime_settings": database.count_records(
            ApplicationRuntimeSettingsRecord
        ),
        "model_settings_required": ModelSettingsRepository(database).has_required(),
    }


def _run_fresh_seed_check() -> None:
    database, _ = _database()
    first = initialize_database(
        database,
        on_ready=lambda: seed_reference_catalog(database),
    )
    tables = set(inspect(database.engine).get_table_names())
    counts = _seed_counts(database)
    required_tables = {
        "alembic_version",
        "application_runtime_settings",
        "conversations",
        "credential_encryption_materials",
        "reference_countries",
    }
    if first.final_revisions != (CURRENT_REVISION,):
        raise AssertionError(f"fresh startup did not reach head: {first!r}")
    if len(tables - {"alembic_version"}) != 17 or not required_tables.issubset(tables):
        raise AssertionError(f"fresh schema table contract failed: {sorted(tables)!r}")
    if counts["credential_encryption_materials"] != 1:
        raise AssertionError("credential encryption material seed is missing or duplicated")
    if counts["reference_countries"] != 249:
        raise AssertionError(f"unexpected reference country seed count: {counts!r}")
    if counts["application_runtime_settings"] != 1:
        raise AssertionError("application runtime settings seed is missing or duplicated")
    if counts["model_settings_required"] is not True:
        raise AssertionError("model settings were not seeded")
    database.engine.dispose()

    second_database, _ = _database()
    second = initialize_database(
        second_database,
        on_ready=lambda: seed_reference_catalog(second_database),
    )
    second_counts = _seed_counts(second_database)
    if second.final_revisions != (CURRENT_REVISION,) or second.migrations_applied:
        raise AssertionError(f"already-current startup was not idempotent: {second!r}")
    if second_counts != counts:
        raise AssertionError(f"idempotent startup changed seed counts: {second_counts!r}")
    second_database.engine.dispose()

    print(f"fresh_start_result={first!r}")
    print(f"application_table_count=17; tables={','.join(sorted(tables))}")
    print(f"seed_counts={counts}")
    print(f"second_start_result={second!r}")
    print("second_start_seed_counts=unchanged; already_current_idempotency=PASS")


def _prepare_supported_previous_revision(
    database: SQLiteRepository,
) -> tuple[tuple[object, ...], tuple[object, ...]]:
    initialized = initialize_database(
        database,
        on_ready=lambda: seed_reference_catalog(database),
    )
    if initialized.final_revisions != (CURRENT_REVISION,):
        raise AssertionError(f"initial database did not reach head: {initialized!r}")

    model_before = _model_settings_snapshot(database)
    encryption_before = _encryption_snapshot(database)
    if database.count_records(ReferenceCountryRecord) < 1:
        raise AssertionError("reference catalog was not populated")
    _downgrade(database)

    with database.session() as session:
        session.add(
            ConversationRecord(
                id=CONVERSATION_ID,
                title="Migration preservation probe",
                context_revision=7,
                next_message_sequence=0,
                conversation_state=CONVERSATION_STATE,
            )
        )
        session.commit()
    database.engine.dispose()
    return model_before, encryption_before


def _run_supported_upgrade() -> None:
    database, database_path = _database()
    model_before, encryption_before = _prepare_supported_previous_revision(database)
    previous = _current_revision(database)
    if previous != PREVIOUS_REVISION:
        raise AssertionError(f"expected previous revision, got {previous}")

    result = initialize_database(
        database,
        on_ready=lambda: seed_reference_catalog(database),
    )
    if result.current_revisions != (PREVIOUS_REVISION,):
        raise AssertionError(f"upgrade did not start at previous revision: {result!r}")
    if result.final_revisions != (CURRENT_REVISION,) or not result.migrations_applied:
        raise AssertionError(f"production migration runner did not apply the upgrade: {result!r}")

    with database.session() as session:
        conversation = session.get(ConversationRecord, CONVERSATION_ID)
        if conversation is None:
            raise AssertionError("conversation ID was not preserved")
        if conversation.conversation_state != CONVERSATION_STATE:
            raise AssertionError("conversation directives, summary, or location changed")
    if _model_settings_snapshot(database) != model_before:
        raise AssertionError("model settings changed during the upgrade")
    if _encryption_snapshot(database) != encryption_before:
        raise AssertionError("credential encryption material changed during the upgrade")
    if database.count_records(ApplicationRuntimeSettingsRecord) != 1:
        raise AssertionError("runtime settings were not seeded after upgrade")
    reference_count = database.count_records(ReferenceCountryRecord)
    if reference_count < 1:
        raise AssertionError("reference catalog was lost during the upgrade")
    with database.engine.connect() as connection:
        foreign_key_errors = list(connection.exec_driver_sql("PRAGMA foreign_key_check"))
    if foreign_key_errors:
        raise AssertionError(f"foreign key check failed: {foreign_key_errors!r}")
    database.engine.dispose()
    backups = list(database_path.parent.glob("database.db.migration-backup-*.db"))
    if backups:
        raise AssertionError(f"successful migration left backup files: {backups!r}")

    print(f"supported_previous_revision={previous}")
    print(f"production_upgrade_result={result!r}")
    print(f"preserved_conversation_id={CONVERSATION_ID}")
    print("conversation_state=model directives, summary, summary index, resolved location: PASS")
    print("model_settings=PASS; encryption_material=PASS; foreign_key_check=PASS")
    print(f"reference_countries={reference_count}; runtime_settings_rows=1; migration_backups=0")


def _logical_snapshot(path: Path) -> bytes:
    def quote_identifier(value: str) -> str:
        return '"' + value.replace('"', '""') + '"'

    def json_value(value: object) -> object:
        return {"blob_hex": value.hex()} if isinstance(value, bytes) else value

    with sqlite3.connect(path) as connection:
        schema = list(
            connection.execute(
                "SELECT type, name, tbl_name, sql FROM sqlite_master "
                "WHERE name NOT LIKE 'sqlite_%' ORDER BY type, name"
            )
        )
        table_names = [row[1] for row in schema if row[0] == "table"]
        contents: dict[str, object] = {}
        for table_name in table_names:
            table = quote_identifier(table_name)
            columns = [
                row[1]
                for row in connection.execute(f"PRAGMA table_info({table})")
            ]
            ordering = ", ".join(quote_identifier(column) for column in columns)
            rows = connection.execute(
                f"SELECT * FROM {table} ORDER BY {ordering}"
            ).fetchall()
            contents[table_name] = [
                [json_value(value) for value in row] for row in rows
            ]
    return json.dumps(
        {"schema": schema, "contents": contents},
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _run_failed_migration_recovery() -> None:
    database, database_path = _database()
    _prepare_supported_previous_revision(database)
    previous = _current_revision(database)
    if previous != PREVIOUS_REVISION:
        raise AssertionError(f"expected previous revision, got {previous}")

    with database.engine.begin() as connection:
        connection.exec_driver_sql(
            "CREATE TABLE application_runtime_settings (marker TEXT NOT NULL)"
        )
        connection.exec_driver_sql(
            "INSERT INTO application_runtime_settings(marker) VALUES ('preserve-me')"
        )
    database.engine.dispose()
    before_snapshot = _logical_snapshot(database_path)
    before_digest = hashlib.sha256(before_snapshot).hexdigest()

    try:
        initialize_database(
            database,
            on_ready=lambda: seed_reference_catalog(database),
        )
    except Exception as exc:
        print(f"expected_migration_failure={type(exc).__name__}: {exc}")
    else:
        raise AssertionError("the conflicting migration unexpectedly succeeded")

    database.engine.dispose()
    after_snapshot = _logical_snapshot(database_path)
    after_digest = hashlib.sha256(after_snapshot).hexdigest()
    if after_snapshot != before_snapshot:
        raise AssertionError("database schema or row data changed after failed migration recovery")
    if _current_revision(database) != PREVIOUS_REVISION:
        raise AssertionError("failed migration changed the stored Alembic revision")
    with database.engine.connect() as connection:
        marker = connection.exec_driver_sql(
            "SELECT marker FROM application_runtime_settings"
        ).scalar_one()
    if marker != "preserve-me":
        raise AssertionError("conflict-table data was not restored")
    database.engine.dispose()
    if _logical_snapshot(database_path) != before_snapshot:
        raise AssertionError("verification reopen changed the restored database")
    backups = list(database_path.parent.glob("database.db.migration-backup-*.db"))
    if backups:
        raise AssertionError(f"failed migration left backup files: {backups!r}")

    print(f"failed_migration_revision_retained={PREVIOUS_REVISION}")
    print(f"logical_snapshot_sha256_before={before_digest}")
    print(f"logical_snapshot_sha256_after={after_digest}")
    print("schema_and_all_rows=PASS; conflict_marker=preserved; migration_backups=0")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "scenario",
        choices=("fresh-seeds", "supported-upgrade", "failed-recovery"),
    )
    args = parser.parse_args()
    if args.scenario == "fresh-seeds":
        _run_fresh_seed_check()
    elif args.scenario == "supported-upgrade":
        _run_supported_upgrade()
    else:
        _run_failed_migration_recovery()


if __name__ == "__main__":
    main()

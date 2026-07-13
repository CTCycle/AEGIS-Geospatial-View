from __future__ import annotations

from pathlib import Path

from sqlalchemy import inspect, text
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.engine import Engine

from server.configurations import DatabaseSettings, get_server_settings
from server.repositories.database.orm_table_operations import (
    SqlAlchemyTableOperationsMixin,
)
from server.repositories.database.engine import build_engine, build_session_factory
from server.repositories.schemas import Base


# [SQLITE DATABASE]

###############################################################################
class SQLiteRepository(SqlAlchemyTableOperationsMixin):
    warn_on_missing_table = True

    # -------------------------------------------------------------------------
    def __init__(self, settings: DatabaseSettings | None = None) -> None:
        self.settings = settings or get_server_settings().database
        db_path = Path(self.settings.database_path)
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self.db_path = str(db_path)
        self.engine: Engine = build_engine(self.settings)
        self.session_factory = build_session_factory(self.engine)
        self.session = self.session_factory
        self.insert_batch_size = self.settings.insert_batch_size

    # -------------------------------------------------------------------------
    def ensure_schema(self) -> None:
        Base.metadata.create_all(self.engine)
        self._upgrade_legacy_schema()

    # -------------------------------------------------------------------------
    def _upgrade_legacy_schema(self) -> None:
        """Add columns introduced by persistence hardening to existing local DBs."""
        additions = {
            "reference_countries": {"name_key": "TEXT NOT NULL DEFAULT ''"},
            "model_credentials": {
                "label_key": "TEXT NOT NULL DEFAULT ''",
                "encryption_material_id": "INTEGER",
            },
            "credential_encryption_materials": {"active_slot": "INTEGER"},
            "chat_sessions": {"next_message_sequence": "INTEGER NOT NULL DEFAULT 0"},
            "chat_messages": {"request_id": "TEXT"},
            "agent_runs": {
                "client_request_id": "TEXT",
                "active_slot": "INTEGER",
                "next_event_sequence": "INTEGER NOT NULL DEFAULT 0",
            },
        }
        inspector = inspect(self.engine)
        with self.engine.begin() as connection:
            for table_name, columns in additions.items():
                existing = {
                    column["name"] for column in inspector.get_columns(table_name)
                }
                for column_name, definition in columns.items():
                    if column_name not in existing:
                        connection.execute(
                            text(
                                f"ALTER TABLE {table_name} ADD COLUMN {column_name} {definition}"
                            )
                        )

            connection.execute(
                text(
                    "UPDATE reference_countries SET name_key = lower(trim(name)) "
                    "WHERE name_key = ''"
                )
            )
            connection.execute(
                text(
                    "UPDATE model_credentials SET label_key = lower(trim(label)) "
                    "WHERE label_key = ''"
                )
            )
            connection.execute(
                text(
                    "UPDATE chat_sessions SET next_message_sequence = "
                    "COALESCE((SELECT max(turn_index) FROM chat_messages "
                    "WHERE chat_messages.session_id = chat_sessions.id), 0) "
                    "WHERE next_message_sequence = 0"
                )
            )
            connection.execute(
                text(
                    "CREATE UNIQUE INDEX IF NOT EXISTS ux_model_credentials_logical_key "
                    "ON model_credentials(provider, label_key)"
                )
            )
            connection.execute(
                text(
                    "CREATE UNIQUE INDEX IF NOT EXISTS ux_chat_messages_sequence "
                    "ON chat_messages(session_id, turn_index)"
                )
            )
            connection.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS ix_chat_messages_request_lookup "
                    "ON chat_messages(session_id, role, request_id)"
                )
            )

    # -------------------------------------------------------------------------
    def _insert_statement(
        self, table_cls: type[object], records: list[dict[str, object]]
    ):
        return sqlite_insert(table_cls).values(records)

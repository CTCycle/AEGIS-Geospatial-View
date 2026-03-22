from __future__ import annotations

import os
from typing import Any

import sqlalchemy
from sqlalchemy import UniqueConstraint, func, inspect, select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker

from AEGIS.server.configurations import DatabaseSettings
from AEGIS.server.repositories.schemas import Base
from AEGIS.server.utils.constants import DATABASE_FILENAME, RESOURCES_PATH
from AEGIS.server.utils.logger import logger


# [SQLITE DATABASE]
###############################################################################
class SQLiteRepository:
    def __init__(self, settings: DatabaseSettings) -> None:
        self.db_path: str | None = os.path.join(RESOURCES_PATH, DATABASE_FILENAME)
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        self.engine: Engine = sqlalchemy.create_engine(
            f"sqlite:///{self.db_path}", echo=False, future=True
        )
        self.session = sessionmaker(bind=self.engine, future=True)
        self.insert_batch_size = settings.insert_batch_size
        if self.db_path is not None and not os.path.exists(self.db_path):
            Base.metadata.create_all(self.engine)

    # -------------------------------------------------------------------------
    def get_table_class(self, table_name: str) -> Any:
        for cls in Base.__subclasses__():
            if getattr(cls, "__tablename__", None) == table_name:
                return cls
        raise ValueError(f"No table class found for name {table_name}")

    # -------------------------------------------------------------------------
    def get_upsert_constraint_columns(self, table_cls: Any) -> list[str]:
        mapper = inspect(table_cls)
        primary_key_columns = [column.key for column in mapper.primary_key]
        if primary_key_columns:
            return primary_key_columns

        for constraint in table_cls.__table__.constraints:
            if isinstance(constraint, UniqueConstraint):
                return list(constraint.columns.keys())
        raise ValueError(f"No unique constraint found for {table_cls.__name__}")

    # -------------------------------------------------------------------------
    def normalize_record(self, table_cls: Any, record: dict[str, Any]) -> dict[str, Any]:
        column_payload: dict[str, Any] = {}
        for column in table_cls.__table__.columns:
            if column.name not in record:
                continue
            value = record[column.name]
            if value is None and bool(column.autoincrement):
                continue
            column_payload[column.name] = value
        return column_payload

    # -------------------------------------------------------------------------
    def serialize_model(self, instance: Any) -> dict[str, Any]:
        return {
            column.name: getattr(instance, column.name)
            for column in instance.__table__.columns
        }

    # -------------------------------------------------------------------------
    def list_columns(self, table_name: str) -> list[str]:
        table_cls = self.get_table_class(table_name)
        return [column.name for column in table_cls.__table__.columns]

    # -------------------------------------------------------------------------
    def upsert_into_database(
        self, records: list[dict[str, Any]], table_name: str
    ) -> None:
        if not records:
            return

        table_cls = self.get_table_class(table_name)
        conflict_columns = self.get_upsert_constraint_columns(table_cls)
        normalized_records: list[dict[str, Any]] = []
        for record in records:
            normalized = self.normalize_record(table_cls, record)
            if normalized:
                normalized_records.append(normalized)
        if not normalized_records:
            return

        table_columns = [column.name for column in table_cls.__table__.columns]
        with self.session() as session:
            for offset in range(0, len(normalized_records), self.insert_batch_size):
                batch = normalized_records[offset : offset + self.insert_batch_size]
                if not batch:
                    continue
                statement = sqlite_insert(table_cls).values(batch)
                batch_columns = {key for row in batch for key in row}
                update_columns = {
                    column: getattr(statement.excluded, column)  # type: ignore[attr-defined]
                    for column in table_columns
                    if column not in conflict_columns and column in batch_columns
                }
                if update_columns:
                    statement = statement.on_conflict_do_update(
                        index_elements=conflict_columns,
                        set_=update_columns,
                    )
                else:
                    statement = statement.on_conflict_do_nothing(
                        index_elements=conflict_columns
                    )
                session.execute(statement)
            session.commit()

    # -------------------------------------------------------------------------
    def load_from_database(self, table_name: str) -> list[dict[str, Any]]:
        table_cls = self.get_table_class(table_name)
        canonical_name = str(table_cls.__tablename__)
        if not inspect(self.engine).has_table(canonical_name):
            logger.warning("Table %s does not exist", canonical_name)
            return []

        with self.session() as session:
            rows = session.execute(select(table_cls)).scalars().all()
        return [self.serialize_model(row) for row in rows]

    # -----------------------------------------------------------------------------
    def count_rows(self, table_name: str) -> int:
        table_cls = self.get_table_class(table_name)
        with self.session() as session:
            value = session.scalar(select(func.count()).select_from(table_cls)) or 0
        return int(value)

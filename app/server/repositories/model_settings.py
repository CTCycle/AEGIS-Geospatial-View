from __future__ import annotations

import json

from sqlalchemy import inspect, text
from sqlalchemy import select

from server.common.time import utc_now_naive
from server.common.constants import (
    DEFAULT_MODEL_NAME,
    DEFAULT_MODEL_PROVIDER,
    DEFAULT_MODEL_PROVIDER_MODE,
    OLLAMA_DEFAULT_HOST,
)
from server.repositories.database.backend import get_database
from server.repositories.schemas.models import ModelProviderSettingsRecord


class ModelSettingsRepository:
    def __init__(self) -> None:
        backend = get_database().backend
        ensure_schema = getattr(backend, "ensure_schema", None)
        if callable(ensure_schema):
            ensure_schema()
        self._ensure_model_capability_columns(backend)
        self._session_factory = backend.session

    def _ensure_model_capability_columns(self, backend) -> None:  # noqa: ANN001
        engine = getattr(backend, "engine", None)
        if engine is None:
            return
        inspector = inspect(engine)
        if not inspector.has_table("model_provider_settings"):
            return
        existing = {
            column["name"]
            for column in inspector.get_columns("model_provider_settings")
            if isinstance(column.get("name"), str)
        }
        column_sql = {
            "capabilities_json": "ALTER TABLE model_provider_settings ADD COLUMN capabilities_json TEXT",
            "supports_tools": "ALTER TABLE model_provider_settings ADD COLUMN supports_tools BOOLEAN NOT NULL DEFAULT 0",
            "supports_structured_output": "ALTER TABLE model_provider_settings ADD COLUMN supports_structured_output BOOLEAN NOT NULL DEFAULT 0",
            "tool_support_source": "ALTER TABLE model_provider_settings ADD COLUMN tool_support_source VARCHAR(40) NOT NULL DEFAULT 'unknown'",
        }
        missing = [name for name in column_sql if name not in existing]
        if not missing:
            return
        with engine.begin() as connection:
            for name in missing:
                connection.execute(text(column_sql[name]))

    def get_or_create(self) -> ModelProviderSettingsRecord:
        with self._session_factory() as session:
            statement = select(ModelProviderSettingsRecord).order_by(
                ModelProviderSettingsRecord.id.asc()
            )
            record = session.execute(statement).scalars().first()
            if record is not None:
                return record

            record = ModelProviderSettingsRecord(
                active_provider_mode=DEFAULT_MODEL_PROVIDER_MODE,
                chat_model_provider=DEFAULT_MODEL_PROVIDER,
                chat_model_name=DEFAULT_MODEL_NAME,
                parser_model_provider=DEFAULT_MODEL_PROVIDER,
                parser_model_name=DEFAULT_MODEL_NAME,
                agent_model_provider=DEFAULT_MODEL_PROVIDER,
                agent_model_name=DEFAULT_MODEL_NAME,
                ollama_url=OLLAMA_DEFAULT_HOST,
                capabilities_json=json.dumps([]),
                supports_tools=False,
                supports_structured_output=False,
                tool_support_source="unknown",
            )
            session.add(record)
            session.commit()
            session.refresh(record)
            return record

    def update(
        self,
        *,
        active_provider_mode: str,
        chat_model_provider: str,
        chat_model_name: str,
        parser_model_provider: str,
        parser_model_name: str,
        agent_model_provider: str,
        agent_model_name: str,
        ollama_url: str,
        openai_base_url: str | None,
        google_base_url: str | None,
    ) -> ModelProviderSettingsRecord:
        with self._session_factory() as session:
            statement = select(ModelProviderSettingsRecord).order_by(
                ModelProviderSettingsRecord.id.asc()
            )
            record = session.execute(statement).scalars().first()
            if record is None:
                record = ModelProviderSettingsRecord()
                session.add(record)

            record.active_provider_mode = active_provider_mode
            record.chat_model_provider = chat_model_provider
            record.chat_model_name = chat_model_name
            record.parser_model_provider = parser_model_provider
            record.parser_model_name = parser_model_name
            record.agent_model_provider = agent_model_provider
            record.agent_model_name = agent_model_name
            record.ollama_url = ollama_url
            record.openai_base_url = openai_base_url
            record.google_base_url = google_base_url
            if record.capabilities_json is None:
                record.capabilities_json = json.dumps([])
            record.supports_tools = bool(record.supports_tools)
            record.supports_structured_output = bool(record.supports_structured_output)
            record.tool_support_source = record.tool_support_source or "unknown"
            record.updated_at = utc_now_naive()
            session.commit()
            session.refresh(record)
            return record

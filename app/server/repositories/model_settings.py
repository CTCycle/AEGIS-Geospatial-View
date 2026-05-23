from __future__ import annotations

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
        self._session_factory = backend.session

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
            record.updated_at = utc_now_naive()
            session.commit()
            session.refresh(record)
            return record

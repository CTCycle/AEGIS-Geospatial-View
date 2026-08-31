from __future__ import annotations

from sqlalchemy import select

from server.common.constants import (
    DEFAULT_MODEL_NAME,
    DEFAULT_MODEL_PROVIDER,
    DEFAULT_MODEL_PROVIDER_MODE,
    OLLAMA_DEFAULT_HOST,
)
from server.common.time import utc_now_naive
from server.contracts.chat import ModelSettingsSnapshot
from server.repositories.database.sqlite import SQLiteRepository
from server.repositories.schemas.models import ModelProviderSettingsRecord


###############################################################################
class ModelSettingsRepository:
    # -------------------------------------------------------------------------
    def __init__(self, database: SQLiteRepository) -> None:
        self._session_factory = database.session

    # -------------------------------------------------------------------------
    def get_required(self) -> ModelSettingsSnapshot:
        with self._session_factory() as session:
            statement = select(ModelProviderSettingsRecord).order_by(
                ModelProviderSettingsRecord.id.asc()
            )
            record = session.execute(statement).scalars().first()
            if record is None:
                raise RuntimeError(
                    "The model settings record is missing; database initialization must seed it."
                )
            return self._to_snapshot(record)

    # -------------------------------------------------------------------------
    def seed_required(self) -> None:
        with self._session_factory() as session:
            statement = select(ModelProviderSettingsRecord).order_by(
                ModelProviderSettingsRecord.id.asc()
            )
            if session.execute(statement).scalars().first() is not None:
                return
            session.add(
                ModelProviderSettingsRecord(
                    active_provider_mode=DEFAULT_MODEL_PROVIDER_MODE,
                    agent_model_provider=DEFAULT_MODEL_PROVIDER,
                    agent_model_name=DEFAULT_MODEL_NAME,
                    ollama_url=OLLAMA_DEFAULT_HOST,
                )
            )
            session.commit()

    # -------------------------------------------------------------------------
    def update(
        self,
        *,
        active_provider_mode: str,
        agent_model_provider: str,
        agent_model_name: str,
        ollama_url: str,
        openai_base_url: str | None,
        google_base_url: str | None,
        deepseek_base_url: str | None,
    ) -> ModelSettingsSnapshot:
        with self._session_factory() as session:
            statement = select(ModelProviderSettingsRecord).order_by(
                ModelProviderSettingsRecord.id.asc()
            )
            record = session.execute(statement).scalars().first()
            if record is None:
                raise RuntimeError(
                    "The model settings record is missing; database initialization must seed it."
                )

            record.active_provider_mode = active_provider_mode
            record.agent_model_provider = agent_model_provider
            record.agent_model_name = agent_model_name
            record.ollama_url = ollama_url
            record.openai_base_url = openai_base_url
            record.google_base_url = google_base_url
            record.deepseek_base_url = deepseek_base_url
            record.updated_at = utc_now_naive()
            session.commit()
            session.refresh(record)
            return self._to_snapshot(record)

    # -------------------------------------------------------------------------
    @staticmethod
    def _to_snapshot(record: ModelProviderSettingsRecord) -> ModelSettingsSnapshot:
        return ModelSettingsSnapshot(
            id=record.id,
            active_provider_mode=record.active_provider_mode,
            agent_model_provider=record.agent_model_provider,
            agent_model_name=record.agent_model_name,
            ollama_url=record.ollama_url,
            openai_base_url=record.openai_base_url,
            google_base_url=record.google_base_url,
            deepseek_base_url=record.deepseek_base_url,
        )

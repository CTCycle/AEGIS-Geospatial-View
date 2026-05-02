from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


###############################################################################
class Base(DeclarativeBase):
    pass


###############################################################################
class GibsLayerRecord(Base):
    __tablename__ = "gibs_layers"

    layer_id: Mapped[str] = mapped_column(String(256), primary_key=True)
    title: Mapped[str | None] = mapped_column(String(512))
    abstract: Mapped[str | None] = mapped_column(Text)
    projections: Mapped[str | None] = mapped_column(Text)
    source_urls: Mapped[str | None] = mapped_column(Text)
    tile_matrix_sets: Mapped[str | None] = mapped_column(Text)
    meters_per_pixel: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (UniqueConstraint("layer_id"),)


class ModelProviderSettingsRecord(Base):
    __tablename__ = "model_provider_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    active_provider_mode: Mapped[str] = mapped_column(String(20), default="local")
    chat_model_provider: Mapped[str] = mapped_column(String(64), default="ollama")
    chat_model_name: Mapped[str] = mapped_column(String(200), default="llama3.2")
    parser_model_provider: Mapped[str] = mapped_column(String(64), default="ollama")
    parser_model_name: Mapped[str] = mapped_column(String(200), default="llama3.2")
    agent_model_provider: Mapped[str] = mapped_column(String(64), default="ollama")
    agent_model_name: Mapped[str] = mapped_column(String(200), default="llama3.2")
    ollama_url: Mapped[str] = mapped_column(
        String(400), default="http://localhost:11434"
    )
    openai_base_url: Mapped[str | None] = mapped_column(String(400))
    google_base_url: Mapped[str | None] = mapped_column(String(400))
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now(), onupdate=func.now()
    )


###############################################################################
class ModelCredentialRecord(Base):
    __tablename__ = "model_credentials"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    provider: Mapped[str] = mapped_column(String(64), nullable=False)
    label: Mapped[str] = mapped_column(String(120), nullable=False)
    encrypted_value: Mapped[str] = mapped_column(Text, nullable=False)
    key_version: Mapped[str] = mapped_column(String(64), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now(), onupdate=func.now()
    )
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime)


###############################################################################
class ChatSessionRecord(Base):
    __tablename__ = "chat_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    title: Mapped[str | None] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="active")
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now(), onupdate=func.now()
    )
    last_map_session_json: Mapped[str | None] = mapped_column(Text)


###############################################################################
class ChatMessageRecord(Base):
    __tablename__ = "chat_messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("chat_sessions.id", ondelete="CASCADE"),
        nullable=False,
    )
    turn_index: Mapped[int] = mapped_column(Integer, nullable=False)
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    structured_payload_json: Mapped[str | None] = mapped_column(Text)
    tool_payload_json: Mapped[str | None] = mapped_column(Text)
    map_session_json: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )


###############################################################################
class SessionCatalogRecord(Base):
    __tablename__ = "session_catalog"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str | None] = mapped_column(String(120))
    session_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("chat_sessions.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    models_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    start_time: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )
    duration_seconds: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    num_messages: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


###############################################################################
class SessionDetailsRecord(Base):
    __tablename__ = "session_details"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("chat_sessions.id", ondelete="CASCADE"),
        nullable=False,
    )
    message_id: Mapped[int] = mapped_column(Integer, nullable=False)
    user_message: Mapped[str] = mapped_column(Text, nullable=False)
    chat_response: Mapped[str] = mapped_column(Text, nullable=False)
    extracted_info_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    timestamp: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )
    response_time: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    has_triggered_search: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )


###############################################################################
class ManifestEmbeddingRecord(Base):
    __tablename__ = "manifest_embeddings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    manifest_id: Mapped[str] = mapped_column(String(255), nullable=False)
    manifest_kind: Mapped[str] = mapped_column(String(50), nullable=False)
    manifest_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    content_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    embedding_provider: Mapped[str] = mapped_column(String(64), nullable=False)
    embedding_model: Mapped[str] = mapped_column(String(200), nullable=False)
    last_embedded_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )
    vector_collection: Mapped[str] = mapped_column(String(120), nullable=False)
    vector_document_id: Mapped[str] = mapped_column(String(255), nullable=False)

    __table_args__ = (
        UniqueConstraint(
            "manifest_id", "manifest_kind", name="ux_manifest_embeddings_manifest"
        ),
    )

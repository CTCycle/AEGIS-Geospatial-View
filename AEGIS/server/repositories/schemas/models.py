from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


###############################################################################
class Base(DeclarativeBase):
    pass


###############################################################################
class GeonamesRecord(Base):
    __tablename__ = "GEONAMES"

    geonameid: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    name: Mapped[str | None] = mapped_column(String(200))
    asciiname: Mapped[str | None] = mapped_column(String(200))
    alternatenames: Mapped[str | None] = mapped_column(Text)
    latitude: Mapped[float | None] = mapped_column(Float)
    longitude: Mapped[float | None] = mapped_column(Float)
    feature_class: Mapped[str | None] = mapped_column(String(1))
    feature_code: Mapped[str | None] = mapped_column(String(10))
    country_code: Mapped[str | None] = mapped_column(String(2))
    cc2: Mapped[str | None] = mapped_column(String(200))
    admin1_code: Mapped[str | None] = mapped_column(String(20))
    admin2_code: Mapped[str | None] = mapped_column(String(80))
    admin3_code: Mapped[str | None] = mapped_column(String(20))
    admin4_code: Mapped[str | None] = mapped_column(String(20))
    population: Mapped[int | None] = mapped_column(BigInteger)
    elevation: Mapped[int | None] = mapped_column(Integer)
    dem: Mapped[int | None] = mapped_column(Integer)
    timezone: Mapped[str | None] = mapped_column(String(40))
    modification_date: Mapped[str | None] = mapped_column(String(10))

    __table_args__ = (UniqueConstraint("geonameid"),)


###############################################################################
class GibsLayerRecord(Base):
    __tablename__ = "GIBS_LAYERS"

    layer_id: Mapped[str] = mapped_column(String(256), primary_key=True)
    title: Mapped[str | None] = mapped_column(String(512))
    abstract: Mapped[str | None] = mapped_column(Text)
    projections: Mapped[str | None] = mapped_column(Text)
    source_urls: Mapped[str | None] = mapped_column(Text)
    tile_matrix_sets: Mapped[str | None] = mapped_column(Text)
    meters_per_pixel: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (UniqueConstraint("layer_id"),)


###############################################################################
class SearchSessionRecord(Base):
    __tablename__ = "SEARCH_SESSIONS"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )
    user: Mapped[str | None] = mapped_column(String(200))
    country: Mapped[str | None] = mapped_column(String(200))
    city: Mapped[str | None] = mapped_column(String(200))
    address: Mapped[str | None] = mapped_column(String(400))
    coordinates: Mapped[str | None] = mapped_column(String(128))
    base_map: Mapped[str | None] = mapped_column(String(200))
    geospatial_layers: Mapped[str | None] = mapped_column(Text)
    state: Mapped[str | None] = mapped_column(String(20))

    __table_args__ = (UniqueConstraint("id"),)


###############################################################################
class ModelProviderSettingsRecord(Base):
    __tablename__ = "MODEL_PROVIDER_SETTINGS"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    active_provider_mode: Mapped[str] = mapped_column(String(20), default="local")
    chat_model_provider: Mapped[str] = mapped_column(String(64), default="ollama")
    chat_model_name: Mapped[str] = mapped_column(String(200), default="llama3.2")
    agent_model_provider: Mapped[str] = mapped_column(String(64), default="ollama")
    agent_model_name: Mapped[str] = mapped_column(String(200), default="llama3.2")
    ollama_url: Mapped[str] = mapped_column(String(400), default="http://localhost:11434")
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
    __tablename__ = "MODEL_CREDENTIALS"

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
class AccessKeyRecord(Base):
    __tablename__ = "access_keys"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    encrypted_value: Mapped[str] = mapped_column(Text, nullable=False)
    fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now(), onupdate=func.now()
    )
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime)

    __table_args__ = (
        CheckConstraint("provider IN ('openai', 'gemini')", name="ck_access_keys_provider"),
        Index("ix_access_keys_provider", "provider"),
        Index(
            "ux_access_keys_provider_active",
            "provider",
            unique=True,
            sqlite_where=text("is_active = 1"),
            postgresql_where=text("is_active = true"),
        ),
    )


###############################################################################
class ChatSessionRecord(Base):
    __tablename__ = "CHAT_SESSIONS"

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
    __tablename__ = "CHAT_MESSAGES"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("CHAT_SESSIONS.id", ondelete="CASCADE"),
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

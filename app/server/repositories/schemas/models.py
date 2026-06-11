from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from server.common.constants import (
    REFERENCE_COUNTRIES_TABLE_NAME,
    REFERENCE_COUNTRY_ALIASES_TABLE_NAME,
    REFERENCE_GEOSPATIAL_LAYER_ALIASES_TABLE_NAME,
    REFERENCE_GEOSPATIAL_LAYER_KEYWORDS_TABLE_NAME,
    REFERENCE_GEOSPATIAL_LAYERS_TABLE_NAME,
    REFERENCE_GIBS_LAYER_DEFAULTS_TABLE_NAME,
    REFERENCE_GIBS_TILE_MATRIX_SETS_TABLE_NAME,
)

###############################################################################
class Base(DeclarativeBase):
    pass

###############################################################################
class ReferenceCountryRecord(Base):
    __tablename__ = REFERENCE_COUNTRIES_TABLE_NAME

    iso2: Mapped[str] = mapped_column(String(2), primary_key=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)


###############################################################################
class ReferenceCountryAliasRecord(Base):
    __tablename__ = REFERENCE_COUNTRY_ALIASES_TABLE_NAME

    alias_key: Mapped[str] = mapped_column(String(160), primary_key=True)
    alias: Mapped[str] = mapped_column(String(160), nullable=False)
    iso2: Mapped[str] = mapped_column(
        String(2),
        ForeignKey(f"{REFERENCE_COUNTRIES_TABLE_NAME}.iso2", ondelete="CASCADE"),
        nullable=False,
    )

    __table_args__ = (Index("ix_reference_country_aliases_iso2", "iso2"),)


###############################################################################
class ReferenceGeospatialLayerRecord(Base):
    __tablename__ = REFERENCE_GEOSPATIAL_LAYERS_TABLE_NAME

    layer_id: Mapped[str] = mapped_column(String(256), primary_key=True)
    display_name: Mapped[str] = mapped_column(String(256), nullable=False)
    group: Mapped[str] = mapped_column(String(64), nullable=False)
    provider: Mapped[str | None] = mapped_column(String(64))


###############################################################################
class ReferenceGeospatialLayerAliasRecord(Base):
    __tablename__ = REFERENCE_GEOSPATIAL_LAYER_ALIASES_TABLE_NAME

    alias_key: Mapped[str] = mapped_column(String(256), primary_key=True)
    alias: Mapped[str] = mapped_column(String(256), nullable=False)
    layer_id: Mapped[str] = mapped_column(
        String(256),
        ForeignKey(
            f"{REFERENCE_GEOSPATIAL_LAYERS_TABLE_NAME}.layer_id",
            ondelete="CASCADE",
        ),
        nullable=False,
    )

    __table_args__ = (Index("ix_reference_geospatial_layer_aliases_layer_id", "layer_id"),)


###############################################################################
class ReferenceGeospatialLayerKeywordRecord(Base):
    __tablename__ = REFERENCE_GEOSPATIAL_LAYER_KEYWORDS_TABLE_NAME

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    keyword_key: Mapped[str] = mapped_column(String(256), nullable=False)
    keyword: Mapped[str] = mapped_column(String(256), nullable=False)
    layer_id: Mapped[str] = mapped_column(
        String(256),
        ForeignKey(
            f"{REFERENCE_GEOSPATIAL_LAYERS_TABLE_NAME}.layer_id",
            ondelete="CASCADE",
        ),
        nullable=False,
    )

    __table_args__ = (
        UniqueConstraint("layer_id", "keyword_key", name="ux_reference_layer_keyword"),
    )


###############################################################################
class ReferenceGibsTileMatrixSetRecord(Base):
    __tablename__ = REFERENCE_GIBS_TILE_MATRIX_SETS_TABLE_NAME

    tile_matrix_set_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    meters_per_pixel: Mapped[float] = mapped_column(Float, nullable=False)


###############################################################################
class ReferenceGibsLayerDefaultRecord(Base):
    __tablename__ = REFERENCE_GIBS_LAYER_DEFAULTS_TABLE_NAME

    layer_id: Mapped[str] = mapped_column(String(256), primary_key=True)
    native_resolution_m: Mapped[float | None] = mapped_column(Float)
    date_fallback_days: Mapped[int | None] = mapped_column(Integer)


###############################################################################
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
    deepseek_base_url: Mapped[str | None] = mapped_column(String(400))
    capabilities_json: Mapped[str | None] = mapped_column(Text)
    supports_tools: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    supports_structured_output: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    tool_support_source: Mapped[str] = mapped_column(
        String(40), nullable=False, default="unknown"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now(), onupdate=func.now()
    )

###############################################################################
class CredentialEncryptionMaterial(Base):
    __tablename__ = "credential_encryption_materials"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    key_purpose: Mapped[str] = mapped_column(String(64), nullable=False)
    key_version: Mapped[int] = mapped_column(Integer, nullable=False)
    key_material: Mapped[str] = mapped_column(Text, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    seeded_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )
    activated_at: Mapped[datetime | None] = mapped_column(DateTime)
    deactivated_at: Mapped[datetime | None] = mapped_column(DateTime)

###############################################################################
class ModelCredentialRecord(Base):
    __tablename__ = "model_credentials"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    provider: Mapped[str] = mapped_column(String(64), nullable=False)
    label: Mapped[str] = mapped_column(String(120), nullable=False)
    encrypted_value: Mapped[str] = mapped_column(Text, nullable=False)
    key_version: Mapped[int] = mapped_column(Integer, nullable=False)
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


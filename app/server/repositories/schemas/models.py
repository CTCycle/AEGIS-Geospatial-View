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
    CheckConstraint,
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
from server.repositories.database.types import PortableJSON


###############################################################################
class Base(DeclarativeBase):
    pass


###############################################################################
class ReferenceCountryRecord(Base):
    __tablename__ = REFERENCE_COUNTRIES_TABLE_NAME

    iso2: Mapped[str] = mapped_column(String(2), primary_key=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    name_key: Mapped[str] = mapped_column(
        String(128), nullable=False, unique=True, default=""
    )

    __table_args__ = (
        CheckConstraint(
            "length(iso2) = 2 AND iso2 = upper(iso2)", name="ck_reference_country_iso2"
        ),
    )


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

    __table_args__ = (
        Index("ix_reference_geospatial_layer_aliases_layer_id", "layer_id"),
    )


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
    __table_args__ = (
        CheckConstraint(
            "meters_per_pixel > 0", name="ck_gibs_meters_per_pixel_positive"
        ),
    )


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
    active_provider_mode: Mapped[str] = mapped_column(String(20), default="cloud")
    agent_model_provider: Mapped[str] = mapped_column(String(64), default="")
    agent_model_name: Mapped[str] = mapped_column(String(200), default="")
    ollama_url: Mapped[str] = mapped_column(
        String(400), default="http://127.0.0.1:11434"
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
    active_slot: Mapped[int | None] = mapped_column(Integer)
    seeded_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )
    activated_at: Mapped[datetime | None] = mapped_column(DateTime)
    deactivated_at: Mapped[datetime | None] = mapped_column(DateTime)
    __table_args__ = (
        UniqueConstraint(
            "key_purpose", "key_version", name="ux_credential_material_version"
        ),
        UniqueConstraint(
            "key_purpose", "active_slot", name="ux_credential_material_active_slot"
        ),
        CheckConstraint(
            "active_slot IS NULL OR active_slot = 1",
            name="ck_credential_material_active_slot",
        ),
    )


###############################################################################
class ModelCredentialRecord(Base):
    __tablename__ = "model_credentials"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    provider: Mapped[str] = mapped_column(String(64), nullable=False)
    label: Mapped[str] = mapped_column(String(120), nullable=False)
    label_key: Mapped[str] = mapped_column(String(120), nullable=False, default="")
    encrypted_value: Mapped[str] = mapped_column(Text, nullable=False)
    key_version: Mapped[int] = mapped_column(Integer, nullable=False)
    encryption_material_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("credential_encryption_materials.id", ondelete="RESTRICT")
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now(), onupdate=func.now()
    )
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime)
    __table_args__ = (
        UniqueConstraint(
            "provider", "label_key", name="ux_model_credentials_logical_key"
        ),
        Index(
            "ix_model_credentials_active_provider_label",
            "is_active",
            "provider",
            "label_key",
        ),
    )


###############################################################################
class ChatMessageRecord(Base):
    __tablename__ = "chat_messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    conversation_id: Mapped[str] = mapped_column(
        String(80),
        ForeignKey("conversations.id", ondelete="CASCADE"),
        nullable=False,
    )
    turn_index: Mapped[int] = mapped_column(Integer, nullable=False)
    request_id: Mapped[str | None] = mapped_column(String(160))
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    structured_payload: Mapped[object | None] = mapped_column(PortableJSON)
    tool_payload: Mapped[object | None] = mapped_column(PortableJSON)
    map_session: Mapped[object | None] = mapped_column(PortableJSON)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )
    __table_args__ = (
        UniqueConstraint("conversation_id", "turn_index", name="ux_chat_messages_sequence"),
        UniqueConstraint(
            "conversation_id", "role", "request_id", name="ux_chat_messages_request"
        ),
        Index(
            "ix_chat_messages_conversation_role_sequence", "conversation_id", "role", "turn_index"
        ),
        CheckConstraint(
            "turn_index >= 0", name="ck_chat_messages_sequence_nonnegative"
        ),
    )


###############################################################################
class ConversationRecord(Base):
    __tablename__ = "conversations"

    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    owner_user_id: Mapped[str | None] = mapped_column(String(120))
    title: Mapped[str | None] = mapped_column(String(200))
    context_revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    active_instructions: Mapped[object | None] = mapped_column(PortableJSON)
    task_snapshot: Mapped[object | None] = mapped_column(PortableJSON)
    memory_snapshot: Mapped[object | None] = mapped_column(PortableJSON)
    conversation_summary: Mapped[object | None] = mapped_column(PortableJSON)
    summary_through_turn_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    next_message_sequence: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now(), onupdate=func.now()
    )


###############################################################################
###############################################################################
class AgentRunRecord(Base):
    __tablename__ = "agent_runs"

    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    conversation_id: Mapped[str] = mapped_column(
        String(80), ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False
    )
    client_request_id: Mapped[str | None] = mapped_column(String(160))
    original_request: Mapped[str] = mapped_column(Text, nullable=False)
    aggregated_request: Mapped[str] = mapped_column(Text, nullable=False)
    active_run_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    state: Mapped[str] = mapped_column(String(40), nullable=False, default="pending")
    observed_by_worker_version: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0
    )
    active_slot: Mapped[int | None] = mapped_column(Integer)
    next_event_sequence: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    cancel_requested_at: Mapped[datetime | None] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime)
    error_code: Mapped[str | None] = mapped_column(String(120))
    error_message: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (
        Index("ix_agent_runs_conversation_id", "conversation_id"),
        UniqueConstraint(
            "conversation_id", "client_request_id", name="ux_agent_runs_client_request"
        ),
        UniqueConstraint(
            "conversation_id", "active_slot", name="ux_agent_runs_active_slot"
        ),
        CheckConstraint(
            "active_slot IS NULL OR active_slot = 1", name="ck_agent_runs_active_slot"
        ),
    )


###############################################################################
class AgentSteeringMessageRecord(Base):
    __tablename__ = "agent_steering_messages"

    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    run_id: Mapped[str] = mapped_column(
        String(80), ForeignKey("agent_runs.id", ondelete="CASCADE"), nullable=False
    )
    run_version: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    client_mutation_id: Mapped[str | None] = mapped_column(String(160))
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )

    __table_args__ = (
        Index("ix_agent_steering_messages_run_id", "run_id"),
        UniqueConstraint(
            "run_id", "client_mutation_id", name="ux_agent_steering_mutation"
        ),
        UniqueConstraint("run_id", "run_version", name="ux_agent_steering_version"),
    )


###############################################################################
class AgentRunEventRecord(Base):
    __tablename__ = "agent_run_events"

    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    run_id: Mapped[str] = mapped_column(
        String(80), ForeignKey("agent_runs.id", ondelete="CASCADE"), nullable=False
    )
    conversation_id: Mapped[str] = mapped_column(
        String(80), ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False
    )
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    run_version: Mapped[int] = mapped_column(Integer, nullable=False)
    type: Mapped[str] = mapped_column(String(60), nullable=False)
    visibility: Mapped[str] = mapped_column(String(20), nullable=False)
    payload_json: Mapped[object] = mapped_column(PortableJSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )

    __table_args__ = (
        UniqueConstraint("run_id", "sequence", name="ux_agent_run_events_sequence"),
        Index("ix_agent_run_events_run_id_sequence", "run_id", "sequence"),
    )

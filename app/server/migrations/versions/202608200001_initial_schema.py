"""Create the initial SQLite schema.

This revision is the authoritative baseline for the SQLite database layout.
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "202608200001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "reference_countries",
        sa.Column("iso2", sa.String(length=2), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False, unique=True),
        sa.Column("name_key", sa.String(length=128), nullable=False, unique=True),
        sa.CheckConstraint(
            "length(iso2) = 2 AND iso2 = upper(iso2)",
            name="ck_reference_country_iso2",
        ),
        sa.PrimaryKeyConstraint("iso2"),
    )
    op.create_table(
        "reference_geospatial_layers",
        sa.Column("layer_id", sa.String(length=256), nullable=False),
        sa.Column("display_name", sa.String(length=256), nullable=False),
        sa.Column("group", sa.String(length=64), nullable=False),
        sa.Column("provider", sa.String(length=64), nullable=True),
        sa.PrimaryKeyConstraint("layer_id"),
    )
    op.create_table(
        "reference_gibs_tile_matrix_sets",
        sa.Column("tile_matrix_set_id", sa.String(length=128), nullable=False),
        sa.Column("meters_per_pixel", sa.Float(), nullable=False),
        sa.CheckConstraint(
            "meters_per_pixel > 0", name="ck_gibs_meters_per_pixel_positive"
        ),
        sa.PrimaryKeyConstraint("tile_matrix_set_id"),
    )
    op.create_table(
        "reference_gibs_layer_defaults",
        sa.Column("layer_id", sa.String(length=256), nullable=False),
        sa.Column("native_resolution_m", sa.Float(), nullable=True),
        sa.Column("date_fallback_days", sa.Integer(), nullable=True),
        sa.PrimaryKeyConstraint("layer_id"),
    )
    op.create_table(
        "model_provider_settings",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("active_provider_mode", sa.String(length=20), nullable=False),
        sa.Column("agent_model_provider", sa.String(length=64), nullable=False),
        sa.Column("agent_model_name", sa.String(length=200), nullable=False),
        sa.Column("ollama_url", sa.String(length=400), nullable=False),
        sa.Column("openai_base_url", sa.String(length=400), nullable=True),
        sa.Column("google_base_url", sa.String(length=400), nullable=True),
        sa.Column("deepseek_base_url", sa.String(length=400), nullable=True),
        sa.Column("capabilities_json", sa.Text(), nullable=True),
        sa.Column("supports_tools", sa.Boolean(), nullable=False),
        sa.Column("supports_structured_output", sa.Boolean(), nullable=False),
        sa.Column("tool_support_source", sa.String(length=40), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "credential_encryption_materials",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("key_purpose", sa.String(length=64), nullable=False),
        sa.Column("key_version", sa.Integer(), nullable=False),
        sa.Column("key_material", sa.Text(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("active_slot", sa.Integer(), nullable=True),
        sa.Column(
            "seeded_at",
            sa.DateTime(),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column("activated_at", sa.DateTime(), nullable=True),
        sa.Column("deactivated_at", sa.DateTime(), nullable=True),
        sa.CheckConstraint(
            "active_slot IS NULL OR active_slot = 1",
            name="ck_credential_material_active_slot",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "key_purpose", "key_version", name="ux_credential_material_version"
        ),
        sa.UniqueConstraint(
            "key_purpose", "active_slot", name="ux_credential_material_active_slot"
        ),
    )
    op.create_table(
        "conversations",
        sa.Column("id", sa.String(length=80), nullable=False),
        sa.Column("owner_user_id", sa.String(length=120), nullable=True),
        sa.Column("title", sa.String(length=200), nullable=True),
        sa.Column("context_revision", sa.Integer(), nullable=False),
        sa.Column("active_instructions", sa.JSON(), nullable=True),
        sa.Column("task_snapshot", sa.JSON(), nullable=True),
        sa.Column("memory_snapshot", sa.JSON(), nullable=True),
        sa.Column("conversation_summary", sa.JSON(), nullable=True),
        sa.Column("summary_through_turn_index", sa.Integer(), nullable=False),
        sa.Column("next_message_sequence", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "model_credentials",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("provider", sa.String(length=64), nullable=False),
        sa.Column("label", sa.String(length=120), nullable=False),
        sa.Column("label_key", sa.String(length=120), nullable=False),
        sa.Column("encrypted_value", sa.Text(), nullable=False),
        sa.Column("key_version", sa.Integer(), nullable=False),
        sa.Column(
            "encryption_material_id",
            sa.Integer(),
            nullable=True,
        ),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column("last_used_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(
            ["encryption_material_id"],
            ["credential_encryption_materials.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "provider", "label_key", name="ux_model_credentials_logical_key"
        ),
    )
    op.create_table(
        "chat_messages",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("conversation_id", sa.String(length=80), nullable=False),
        sa.Column("turn_index", sa.Integer(), nullable=False),
        sa.Column("request_id", sa.String(length=160), nullable=True),
        sa.Column("role", sa.String(length=20), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("structured_payload", sa.JSON(), nullable=True),
        sa.Column("tool_payload", sa.JSON(), nullable=True),
        sa.Column("map_session", sa.JSON(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["conversation_id"], ["conversations.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "conversation_id", "turn_index", name="ux_chat_messages_sequence"
        ),
        sa.UniqueConstraint(
            "conversation_id", "role", "request_id", name="ux_chat_messages_request"
        ),
        sa.CheckConstraint(
            "turn_index >= 0", name="ck_chat_messages_sequence_nonnegative"
        ),
    )
    op.create_table(
        "agent_runs",
        sa.Column("id", sa.String(length=80), nullable=False),
        sa.Column("conversation_id", sa.String(length=80), nullable=False),
        sa.Column("client_request_id", sa.String(length=160), nullable=True),
        sa.Column("original_request", sa.Text(), nullable=False),
        sa.Column("aggregated_request", sa.Text(), nullable=False),
        sa.Column("active_run_version", sa.Integer(), nullable=False),
        sa.Column("state", sa.String(length=40), nullable=False),
        sa.Column("observed_by_worker_version", sa.Integer(), nullable=False),
        sa.Column("active_slot", sa.Integer(), nullable=True),
        sa.Column("next_event_sequence", sa.Integer(), nullable=False),
        sa.Column("cancel_requested_at", sa.DateTime(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column("error_code", sa.String(length=120), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(
            ["conversation_id"], ["conversations.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "conversation_id", "client_request_id", name="ux_agent_runs_client_request"
        ),
        sa.UniqueConstraint(
            "conversation_id", "active_slot", name="ux_agent_runs_active_slot"
        ),
        sa.CheckConstraint(
            "active_slot IS NULL OR active_slot = 1",
            name="ck_agent_runs_active_slot",
        ),
    )
    op.create_table(
        "reference_country_aliases",
        sa.Column("alias_key", sa.String(length=160), nullable=False),
        sa.Column("alias", sa.String(length=160), nullable=False),
        sa.Column("iso2", sa.String(length=2), nullable=False),
        sa.ForeignKeyConstraint(
            ["iso2"], ["reference_countries.iso2"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("alias_key"),
    )
    op.create_table(
        "reference_geospatial_layer_aliases",
        sa.Column("alias_key", sa.String(length=256), nullable=False),
        sa.Column("alias", sa.String(length=256), nullable=False),
        sa.Column("layer_id", sa.String(length=256), nullable=False),
        sa.ForeignKeyConstraint(
            ["layer_id"],
            ["reference_geospatial_layers.layer_id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("alias_key"),
    )
    op.create_table(
        "reference_geospatial_layer_keywords",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("keyword_key", sa.String(length=256), nullable=False),
        sa.Column("keyword", sa.String(length=256), nullable=False),
        sa.Column("layer_id", sa.String(length=256), nullable=False),
        sa.ForeignKeyConstraint(
            ["layer_id"],
            ["reference_geospatial_layers.layer_id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "layer_id", "keyword_key", name="ux_reference_layer_keyword"
        ),
    )
    op.create_table(
        "agent_steering_messages",
        sa.Column("id", sa.String(length=80), nullable=False),
        sa.Column("run_id", sa.String(length=80), nullable=False),
        sa.Column("run_version", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("client_mutation_id", sa.String(length=160), nullable=True),
        sa.Column("state_delta_applied", sa.Boolean(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["run_id"], ["agent_runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("run_id", "client_mutation_id", name="ux_agent_steering_mutation"),
        sa.UniqueConstraint("run_id", "run_version", name="ux_agent_steering_version"),
    )
    op.create_table(
        "agent_run_events",
        sa.Column("id", sa.String(length=80), nullable=False),
        sa.Column("run_id", sa.String(length=80), nullable=False),
        sa.Column("conversation_id", sa.String(length=80), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("run_version", sa.Integer(), nullable=False),
        sa.Column("type", sa.String(length=60), nullable=False),
        sa.Column("visibility", sa.String(length=20), nullable=False),
        sa.Column("payload_json", sa.JSON(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["run_id"], ["agent_runs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["conversation_id"], ["conversations.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("run_id", "sequence", name="ux_agent_run_events_sequence"),
    )

    op.create_index(
        "ix_reference_country_aliases_iso2",
        "reference_country_aliases",
        ["iso2"],
    )
    op.create_index(
        "ix_reference_geospatial_layer_aliases_layer_id",
        "reference_geospatial_layer_aliases",
        ["layer_id"],
    )
    op.create_index(
        "ix_model_credentials_active_provider_label",
        "model_credentials",
        ["is_active", "provider", "label_key"],
    )
    op.create_index(
        "ix_chat_messages_conversation_role_sequence",
        "chat_messages",
        ["conversation_id", "role", "turn_index"],
    )
    op.create_index(
        "ix_agent_runs_conversation_id", "agent_runs", ["conversation_id"]
    )
    op.create_index(
        "ix_agent_steering_messages_run_id",
        "agent_steering_messages",
        ["run_id"],
    )
    op.create_index(
        "ix_agent_run_events_run_id_sequence",
        "agent_run_events",
        ["run_id", "sequence"],
    )


def downgrade() -> None:
    op.drop_index("ix_agent_run_events_run_id_sequence", table_name="agent_run_events")
    op.drop_index("ix_agent_steering_messages_run_id", table_name="agent_steering_messages")
    op.drop_index("ix_agent_runs_conversation_id", table_name="agent_runs")
    op.drop_index(
        "ix_chat_messages_conversation_role_sequence", table_name="chat_messages"
    )
    op.drop_index(
        "ix_model_credentials_active_provider_label", table_name="model_credentials"
    )
    op.drop_index(
        "ix_reference_geospatial_layer_aliases_layer_id",
        table_name="reference_geospatial_layer_aliases",
    )
    op.drop_index(
        "ix_reference_country_aliases_iso2", table_name="reference_country_aliases"
    )
    op.drop_table("agent_run_events")
    op.drop_table("agent_steering_messages")
    op.drop_table("reference_geospatial_layer_keywords")
    op.drop_table("reference_geospatial_layer_aliases")
    op.drop_table("reference_country_aliases")
    op.drop_table("agent_runs")
    op.drop_table("chat_messages")
    op.drop_table("model_credentials")
    op.drop_table("conversations")
    op.drop_table("credential_encryption_materials")
    op.drop_table("model_provider_settings")
    op.drop_table("reference_gibs_layer_defaults")
    op.drop_table("reference_gibs_tile_matrix_sets")
    op.drop_table("reference_geospatial_layers")
    op.drop_table("reference_countries")

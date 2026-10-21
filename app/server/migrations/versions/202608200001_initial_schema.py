"""Create the initial SQLite schema.

This revision is the authoritative baseline for the SQLite database
layout. It is the squashed 2026-08/10 migration chain: the disposable
data-directory SQLite file is recreated when the schema changes
instead of being extended in place.
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "202608200001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

###############################################################################
_SCHEMA_STATEMENTS: tuple[str, ...] = (
    # Table: agent_evidence
    """
CREATE TABLE agent_evidence (
	id VARCHAR(96) NOT NULL, 
	conversation_id VARCHAR(80) NOT NULL, 
	run_id VARCHAR(80), 
	kind VARCHAR(48) NOT NULL, 
	media_type VARCHAR(120) NOT NULL, 
	status VARCHAR(24) NOT NULL, 
	summary_json JSON NOT NULL, 
	provenance_json JSON NOT NULL, 
	payload_blob BLOB NOT NULL, 
	uncompressed_byte_size INTEGER NOT NULL, 
	sha256 VARCHAR(64) NOT NULL, 
	parent_evidence_ids JSON NOT NULL, 
	created_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT ck_agent_evidence_status CHECK (status IN ('available', 'partial', 'valid_empty', 'failed', 'superseded')), 
	CONSTRAINT ck_agent_evidence_size_nonnegative CHECK (uncompressed_byte_size >= 0), 
	FOREIGN KEY(conversation_id) REFERENCES conversations (id) ON DELETE CASCADE, 
	FOREIGN KEY(run_id) REFERENCES agent_runs (id) ON DELETE SET NULL
)""",

    # Table: agent_run_events
    """
CREATE TABLE agent_run_events (
	id VARCHAR(80) NOT NULL, 
	run_id VARCHAR(80) NOT NULL, 
	conversation_id VARCHAR(80) NOT NULL, 
	sequence INTEGER NOT NULL, 
	run_version INTEGER NOT NULL, 
	type VARCHAR(60) NOT NULL, 
	visibility VARCHAR(20) NOT NULL, 
	payload_json JSON NOT NULL, 
	created_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(run_id) REFERENCES agent_runs (id) ON DELETE CASCADE, 
	FOREIGN KEY(conversation_id) REFERENCES conversations (id) ON DELETE CASCADE, 
	CONSTRAINT ux_agent_run_events_sequence UNIQUE (run_id, sequence)
)""",

    # Table: agent_runs
    """
CREATE TABLE agent_runs (
	id VARCHAR(80) NOT NULL, 
	conversation_id VARCHAR(80) NOT NULL, 
	client_request_id VARCHAR(160), 
	original_request TEXT NOT NULL, 
	aggregated_request TEXT NOT NULL, 
	active_run_version INTEGER NOT NULL, 
	state VARCHAR(40) NOT NULL, 
	observed_by_worker_version INTEGER NOT NULL, 
	active_slot INTEGER, 
	next_event_sequence INTEGER NOT NULL, 
	cancel_requested_at DATETIME, 
	created_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL, 
	started_at DATETIME, 
	completed_at DATETIME, 
	error_code VARCHAR(120), 
	error_message TEXT, presentation_status VARCHAR(24) DEFAULT 'not_required' NOT NULL, presentation_json JSON, request_timezone VARCHAR(64), render_prepared_at DATETIME, 
	PRIMARY KEY (id), 
	FOREIGN KEY(conversation_id) REFERENCES conversations (id) ON DELETE CASCADE, 
	CONSTRAINT ux_agent_runs_client_request UNIQUE (conversation_id, client_request_id), 
	CONSTRAINT ux_agent_runs_active_slot UNIQUE (conversation_id, active_slot), 
	CONSTRAINT ck_agent_runs_active_slot CHECK (active_slot IS NULL OR active_slot = 1)
)""",

    # Table: agent_steering_messages
    """
CREATE TABLE agent_steering_messages (
	id VARCHAR(80) NOT NULL, 
	run_id VARCHAR(80) NOT NULL, 
	run_version INTEGER NOT NULL, 
	content TEXT NOT NULL, 
	client_mutation_id VARCHAR(160), 
	state_delta_applied BOOLEAN NOT NULL, 
	created_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(run_id) REFERENCES agent_runs (id) ON DELETE CASCADE, 
	CONSTRAINT ux_agent_steering_mutation UNIQUE (run_id, client_mutation_id), 
	CONSTRAINT ux_agent_steering_version UNIQUE (run_id, run_version)
)""",

    # Table: application_runtime_settings
    """
CREATE TABLE application_runtime_settings (
	id INTEGER NOT NULL, 
	schema_version INTEGER NOT NULL, 
	payload_json JSON NOT NULL, 
	created_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL, 
	updated_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL, 
	PRIMARY KEY (id)
)""",

    # Table: chat_messages
    """
CREATE TABLE chat_messages (
	id INTEGER NOT NULL, 
	conversation_id VARCHAR(80) NOT NULL, 
	turn_index INTEGER NOT NULL, 
	request_id VARCHAR(160), 
	role VARCHAR(20) NOT NULL, 
	content TEXT NOT NULL, 
	structured_payload JSON, 
	tool_payload JSON, 
	map_session JSON, 
	created_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(conversation_id) REFERENCES conversations (id) ON DELETE CASCADE, 
	CONSTRAINT ux_chat_messages_sequence UNIQUE (conversation_id, turn_index), 
	CONSTRAINT ux_chat_messages_request UNIQUE (conversation_id, role, request_id), 
	CONSTRAINT ck_chat_messages_sequence_nonnegative CHECK (turn_index >= 0)
)""",

    # Table: conversations
    """
CREATE TABLE "conversations" (
	id VARCHAR(80) NOT NULL, 
	owner_user_id VARCHAR(120), 
	title VARCHAR(200), 
	context_revision INTEGER NOT NULL, 
	next_message_sequence INTEGER NOT NULL, 
	created_at DATETIME DEFAULT (CURRENT_TIMESTAMP) NOT NULL, 
	updated_at DATETIME DEFAULT (CURRENT_TIMESTAMP) NOT NULL, 
	conversation_state JSON, 
	PRIMARY KEY (id)
)""",

    # Table: credential_encryption_materials
    """
CREATE TABLE credential_encryption_materials (
	id INTEGER NOT NULL, 
	key_purpose VARCHAR(64) NOT NULL, 
	key_version INTEGER NOT NULL, 
	key_material TEXT NOT NULL, 
	is_active BOOLEAN NOT NULL, 
	active_slot INTEGER, 
	seeded_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL, 
	activated_at DATETIME, 
	deactivated_at DATETIME, 
	PRIMARY KEY (id), 
	CONSTRAINT ck_credential_material_active_slot CHECK (active_slot IS NULL OR active_slot = 1), 
	CONSTRAINT ux_credential_material_version UNIQUE (key_purpose, key_version), 
	CONSTRAINT ux_credential_material_active_slot UNIQUE (key_purpose, active_slot)
)""",

    # Table: model_credentials
    """
CREATE TABLE model_credentials (
	id INTEGER NOT NULL, 
	provider VARCHAR(64) NOT NULL, 
	label VARCHAR(120) NOT NULL, 
	label_key VARCHAR(120) NOT NULL, 
	encrypted_value TEXT NOT NULL, 
	key_version INTEGER NOT NULL, 
	encryption_material_id INTEGER, 
	is_active BOOLEAN NOT NULL, 
	created_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL, 
	updated_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL, 
	last_used_at DATETIME, 
	PRIMARY KEY (id), 
	FOREIGN KEY(encryption_material_id) REFERENCES credential_encryption_materials (id) ON DELETE RESTRICT, 
	CONSTRAINT ux_model_credentials_logical_key UNIQUE (provider, label_key)
)""",

    # Table: model_provider_settings
    """
CREATE TABLE model_provider_settings (
	id INTEGER NOT NULL, 
	active_provider_mode VARCHAR(20) NOT NULL, 
	agent_model_provider VARCHAR(64) NOT NULL, 
	agent_model_name VARCHAR(200) NOT NULL, 
	ollama_url VARCHAR(400) NOT NULL, 
	openai_base_url VARCHAR(400), 
	google_base_url VARCHAR(400), 
	deepseek_base_url VARCHAR(400), 
	created_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL, 
	updated_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL, 
	PRIMARY KEY (id)
)""",

    # Table: reference_countries
    """
CREATE TABLE reference_countries (
	iso2 VARCHAR(2) NOT NULL, 
	name VARCHAR(128) NOT NULL, 
	name_key VARCHAR(128) NOT NULL, 
	PRIMARY KEY (iso2), 
	CONSTRAINT ck_reference_country_iso2 CHECK (length(iso2) = 2 AND iso2 = upper(iso2)), 
	UNIQUE (name), 
	UNIQUE (name_key)
)""",

    # Table: reference_country_aliases
    """
CREATE TABLE reference_country_aliases (
	alias_key VARCHAR(160) NOT NULL, 
	alias VARCHAR(160) NOT NULL, 
	iso2 VARCHAR(2) NOT NULL, 
	PRIMARY KEY (alias_key), 
	FOREIGN KEY(iso2) REFERENCES reference_countries (iso2) ON DELETE CASCADE
)""",

    # Table: reference_geospatial_layer_aliases
    """
CREATE TABLE reference_geospatial_layer_aliases (
	alias_key VARCHAR(256) NOT NULL, 
	alias VARCHAR(256) NOT NULL, 
	layer_id VARCHAR(256) NOT NULL, 
	PRIMARY KEY (alias_key), 
	FOREIGN KEY(layer_id) REFERENCES reference_geospatial_layers (layer_id) ON DELETE CASCADE
)""",

    # Table: reference_geospatial_layer_keywords
    """
CREATE TABLE reference_geospatial_layer_keywords (
	id INTEGER NOT NULL, 
	keyword_key VARCHAR(256) NOT NULL, 
	keyword VARCHAR(256) NOT NULL, 
	layer_id VARCHAR(256) NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(layer_id) REFERENCES reference_geospatial_layers (layer_id) ON DELETE CASCADE, 
	CONSTRAINT ux_reference_layer_keyword UNIQUE (layer_id, keyword_key)
)""",

    # Table: reference_geospatial_layers
    """
CREATE TABLE reference_geospatial_layers (
	layer_id VARCHAR(256) NOT NULL, 
	display_name VARCHAR(256) NOT NULL, 
	"group" VARCHAR(64) NOT NULL, 
	provider VARCHAR(64), 
	PRIMARY KEY (layer_id)
)""",

    # Table: reference_gibs_layer_defaults
    """
CREATE TABLE reference_gibs_layer_defaults (
	layer_id VARCHAR(256) NOT NULL, 
	native_resolution_m FLOAT, 
	date_fallback_days INTEGER, 
	PRIMARY KEY (layer_id)
)""",

    # Table: reference_gibs_tile_matrix_sets
    """
CREATE TABLE reference_gibs_tile_matrix_sets (
	tile_matrix_set_id VARCHAR(128) NOT NULL, 
	meters_per_pixel FLOAT NOT NULL, 
	PRIMARY KEY (tile_matrix_set_id), 
	CONSTRAINT ck_gibs_meters_per_pixel_positive CHECK (meters_per_pixel > 0)
)""",

    # Index: ix_agent_evidence_conversation_created
    """
CREATE INDEX ix_agent_evidence_conversation_created ON agent_evidence (conversation_id, created_at)""",

    # Index: ix_agent_evidence_run_id
    """
CREATE INDEX ix_agent_evidence_run_id ON agent_evidence (run_id)""",

    # Index: ix_agent_run_events_run_id_sequence
    """
CREATE INDEX ix_agent_run_events_run_id_sequence ON agent_run_events (run_id, sequence)""",

    # Index: ix_agent_runs_conversation_id
    """
CREATE INDEX ix_agent_runs_conversation_id ON agent_runs (conversation_id)""",

    # Index: ix_agent_steering_messages_run_id
    """
CREATE INDEX ix_agent_steering_messages_run_id ON agent_steering_messages (run_id)""",

    # Index: ix_chat_messages_conversation_role_sequence
    """
CREATE INDEX ix_chat_messages_conversation_role_sequence ON chat_messages (conversation_id, role, turn_index)""",

    # Index: ix_model_credentials_active_provider_label
    """
CREATE INDEX ix_model_credentials_active_provider_label ON model_credentials (is_active, provider, label_key)""",

    # Index: ix_reference_country_aliases_iso2
    """
CREATE INDEX ix_reference_country_aliases_iso2 ON reference_country_aliases (iso2)""",

    # Index: ix_reference_geospatial_layer_aliases_layer_id
    """
CREATE INDEX ix_reference_geospatial_layer_aliases_layer_id ON reference_geospatial_layer_aliases (layer_id)""",

)

###############################################################################
def upgrade() -> None:
    for statement in _SCHEMA_STATEMENTS:
        op.execute(sa.text(statement))

###############################################################################
def downgrade() -> None:
    for name in reversed([
        "agent_evidence",
        "agent_run_events",
        "agent_runs",
        "agent_steering_messages",
        "application_runtime_settings",
        "chat_messages",
        "conversations",
        "credential_encryption_materials",
        "model_credentials",
        "model_provider_settings",
        "reference_countries",
        "reference_country_aliases",
        "reference_geospatial_layer_aliases",
        "reference_geospatial_layer_keywords",
        "reference_geospatial_layers",
        "reference_gibs_layer_defaults",
        "reference_gibs_tile_matrix_sets",
    ]):
        op.execute(sa.text('DROP TABLE IF EXISTS "' + name + '"'))

"""Persist bounded native-agent evidence for a conversation lifetime."""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "202609090001"
down_revision: Union[str, None] = "202609050002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

###############################################################################
def upgrade() -> None:
    op.create_table(
        "agent_evidence",
        sa.Column("id", sa.String(length=96), nullable=False),
        sa.Column("conversation_id", sa.String(length=80), nullable=False),
        sa.Column("run_id", sa.String(length=80), nullable=True),
        sa.Column("kind", sa.String(length=48), nullable=False),
        sa.Column("media_type", sa.String(length=120), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("summary_json", sa.JSON(), nullable=False),
        sa.Column("provenance_json", sa.JSON(), nullable=False),
        sa.Column("payload_blob", sa.LargeBinary(), nullable=False),
        sa.Column("uncompressed_byte_size", sa.Integer(), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("parent_evidence_ids", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(
            "status IN ('available', 'partial', 'valid_empty', 'failed', 'superseded')",
            name="ck_agent_evidence_status",
        ),
        sa.CheckConstraint(
            "uncompressed_byte_size >= 0", name="ck_agent_evidence_size_nonnegative"
        ),
        sa.ForeignKeyConstraint(
            ["conversation_id"], ["conversations.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["run_id"], ["agent_runs.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_agent_evidence_conversation_created",
        "agent_evidence",
        ["conversation_id", "created_at"],
    )
    op.create_index("ix_agent_evidence_run_id", "agent_evidence", ["run_id"])

###############################################################################
def downgrade() -> None:
    op.drop_index("ix_agent_evidence_run_id", table_name="agent_evidence")
    op.drop_index(
        "ix_agent_evidence_conversation_created", table_name="agent_evidence"
    )
    op.drop_table("agent_evidence")

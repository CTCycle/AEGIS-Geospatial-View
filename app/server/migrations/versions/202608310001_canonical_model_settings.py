"""Remove derived model capability metadata from persisted settings."""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "202608310001"
down_revision: Union[str, None] = "202608200001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


###############################################################################
def upgrade() -> None:
    op.drop_column("model_provider_settings", "capabilities_json")
    op.drop_column("model_provider_settings", "supports_tools")
    op.drop_column("model_provider_settings", "supports_structured_output")
    op.drop_column("model_provider_settings", "tool_support_source")


###############################################################################
def downgrade() -> None:
    op.add_column(
        "model_provider_settings",
        sa.Column("capabilities_json", sa.Text(), nullable=True),
    )
    op.add_column(
        "model_provider_settings",
        sa.Column(
            "supports_tools",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.add_column(
        "model_provider_settings",
        sa.Column(
            "supports_structured_output",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.add_column(
        "model_provider_settings",
        sa.Column(
            "tool_support_source",
            sa.String(length=40),
            nullable=False,
            server_default="unknown",
        ),
    )

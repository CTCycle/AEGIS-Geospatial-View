"""Persist the prepared map presentation and browser acknowledgment state."""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "202609050001"
down_revision: Union[str, None] = "202608310001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

###############################################################################
def upgrade() -> None:
    op.add_column(
        "agent_runs",
        sa.Column(
            "presentation_status",
            sa.String(length=24),
            nullable=False,
            server_default="not_required",
        ),
    )
    op.add_column(
        "agent_runs",
        sa.Column("presentation_json", sa.JSON(), nullable=True),
    )

###############################################################################
def downgrade() -> None:
    op.drop_column("agent_runs", "presentation_json")
    op.drop_column("agent_runs", "presentation_status")

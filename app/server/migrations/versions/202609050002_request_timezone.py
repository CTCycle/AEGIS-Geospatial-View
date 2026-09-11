"""Persist the client timezone captured for an agent run."""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "202609050002"
down_revision: Union[str, None] = "202609050001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

###############################################################################
def upgrade() -> None:
    op.add_column(
        "agent_runs",
        sa.Column("request_timezone", sa.String(length=64), nullable=True),
    )

###############################################################################
def downgrade() -> None:
    op.drop_column("agent_runs", "request_timezone")

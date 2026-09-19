"""Add the canonical durable native conversation state."""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "202609140001"
down_revision: Union[str, None] = "202609090002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


###############################################################################
def upgrade() -> None:
    op.add_column(
        "conversations",
        sa.Column("conversation_state", sa.JSON(), nullable=True),
    )


###############################################################################
def downgrade() -> None:
    op.drop_column("conversations", "conversation_state")

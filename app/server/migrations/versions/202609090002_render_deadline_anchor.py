from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "202609090002"
down_revision: Union[str, None] = "202609090001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


###############################################################################
def upgrade() -> None:
    op.add_column(
        "agent_runs",
        sa.Column("render_prepared_at", sa.DateTime(), nullable=True),
    )


###############################################################################
def downgrade() -> None:
    op.drop_column("agent_runs", "render_prepared_at")

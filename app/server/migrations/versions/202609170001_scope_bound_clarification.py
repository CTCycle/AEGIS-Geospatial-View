"""Migrate legacy unresolved questions to scoped native clarification state."""

from __future__ import annotations

import json
from typing import Any, Sequence, Union, cast

from alembic import op
import sqlalchemy as sa

from server.domain.agent.conversation import ConversationState


revision: str = "202609170001"
down_revision: Union[str, None] = "202609150001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _state(value: object) -> dict[str, Any] | None:
    if isinstance(value, dict):
        return dict(cast(dict[str, Any], value))
    if isinstance(value, str):
        try:
            parsed: object = json.loads(value)
        except json.JSONDecodeError:
            return None
        return (
            dict(cast(dict[str, Any], parsed))
            if isinstance(parsed, dict)
            else None
        )
    return None


def upgrade() -> None:
    bind = op.get_bind()
    conversations = sa.table(
        "conversations",
        sa.column("id", sa.String()),
        sa.column("context_revision", sa.Integer()),
        sa.column("conversation_state", sa.JSON()),
    )
    rows = bind.execute(
        sa.select(
            conversations.c.id,
            conversations.c.context_revision,
            conversations.c.conversation_state,
        )
    ).mappings()
    for row in rows:
        raw = _state(row.get("conversation_state"))
        if raw is None:
            continue
        migrated = ConversationState.from_persisted(
            str(row["id"]),
            raw,
            revision=int(row.get("context_revision") or 0),
        ).model_dump(mode="json")
        if migrated != raw:
            bind.execute(
                conversations.update()
                .where(conversations.c.id == row["id"])
                .values(conversation_state=migrated)
            )


def downgrade() -> None:
    # The schema-v2 record is backward readable through ConversationState's
    # migration path.  Keep the data intact on downgrade rather than dropping
    # a user's clarification audit trail.
    return None

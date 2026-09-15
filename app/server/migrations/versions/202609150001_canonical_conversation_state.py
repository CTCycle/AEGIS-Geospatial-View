"""Make native conversation state the only durable conversation snapshot."""

from __future__ import annotations

import json
from typing import Any, Sequence, Union

from alembic import op
import sqlalchemy as sa

from server.domain.agent.conversation import ConversationState
from server.domain.agent.decision import ResolvedLocation
from server.contracts.geospatial import MapSession

revision: str = "202609150001"
down_revision: Union[str, None] = "202609140001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _json_value(value: Any) -> Any:
    if isinstance(value, (dict, list)):
        return value
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return None
    return None


def _migrate_state(row: dict[str, Any]) -> dict[str, Any]:
    conversation_id = str(row["id"])
    revision = max(0, int(row.get("context_revision") or 0))
    state = ConversationState.empty(conversation_id, revision=revision)

    active_directives = _json_value(row.get("active_instructions"))
    if isinstance(active_directives, list):
        state.active_directives = [
            item for item in active_directives if isinstance(item, dict)
        ]

    summary = _json_value(row.get("conversation_summary"))
    if isinstance(summary, dict):
        state.summary = summary
    state.summary_through_turn_index = max(
        0, int(row.get("summary_through_turn_index") or 0)
    )

    memory = _json_value(row.get("memory_snapshot"))
    if isinstance(memory, dict):
        raw_location = memory.get("active_location")
        if isinstance(raw_location, dict):
            try:
                location = ResolvedLocation.model_validate(raw_location)
            except (TypeError, ValueError):
                location = None
            if location is not None:
                state.resolved_locations["active_location"] = location

    task_snapshot = _json_value(row.get("task_snapshot"))
    if isinstance(task_snapshot, dict):
        raw_map = task_snapshot.get("active_map_session")
        if isinstance(raw_map, dict):
            try:
                map_session = MapSession.model_validate(raw_map)
            except (TypeError, ValueError):
                map_session = None
            if map_session is not None:
                state.committed_map_session = map_session
                state.resolved_locations.setdefault(
                    "active_location", map_session.resolved_location
                )

    return state.model_dump(mode="json")


def upgrade() -> None:
    bind = op.get_bind()
    conversations = sa.table(
        "conversations",
        sa.column("id", sa.String()),
        sa.column("context_revision", sa.Integer()),
        sa.column("active_instructions", sa.JSON()),
        sa.column("task_snapshot", sa.JSON()),
        sa.column("memory_snapshot", sa.JSON()),
        sa.column("conversation_summary", sa.JSON()),
        sa.column("summary_through_turn_index", sa.Integer()),
        sa.column("conversation_state", sa.JSON()),
    )
    rows = bind.execute(
        sa.select(
            conversations.c.id,
            conversations.c.context_revision,
            conversations.c.active_instructions,
            conversations.c.task_snapshot,
            conversations.c.memory_snapshot,
            conversations.c.conversation_summary,
            conversations.c.summary_through_turn_index,
            conversations.c.conversation_state,
        )
    ).mappings()
    for row in rows:
        if row.get("conversation_state") is not None:
            continue
        bind.execute(
            conversations.update()
            .where(conversations.c.id == row["id"])
            .values(conversation_state=_migrate_state(dict(row)))
        )

    with op.batch_alter_table("conversations") as batch:
        for column in (
            "active_instructions",
            "task_snapshot",
            "memory_snapshot",
            "conversation_summary",
            "summary_through_turn_index",
        ):
            batch.drop_column(column)


def downgrade() -> None:
    with op.batch_alter_table("conversations") as batch:
        batch.add_column(sa.Column("active_instructions", sa.JSON(), nullable=True))
        batch.add_column(sa.Column("task_snapshot", sa.JSON(), nullable=True))
        batch.add_column(sa.Column("memory_snapshot", sa.JSON(), nullable=True))
        batch.add_column(sa.Column("conversation_summary", sa.JSON(), nullable=True))
        batch.add_column(
            sa.Column(
                "summary_through_turn_index",
                sa.Integer(),
                nullable=False,
                server_default="0",
            )
        )

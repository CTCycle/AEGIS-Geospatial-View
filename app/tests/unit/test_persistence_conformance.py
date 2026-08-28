from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import inspect, select
from sqlalchemy.exc import IntegrityError

from server.configurations import DatabaseSettings
from server.repositories.database.initializer import initialize_database
from server.repositories.database.sqlite import SQLiteRepository
from server.repositories.schemas.models import (
    AgentRunRecord,
    Base,
    ChatMessageRecord,
    ConversationRecord,
)

###############################################################################
@pytest.fixture
def backend(tmp_path: Path):
    repository = SQLiteRepository(
        DatabaseSettings(database_path=str(tmp_path / "conformance.db"))
    )
    initialize_database(repository)
    yield repository
    Base.metadata.drop_all(repository.engine)
    repository.engine.dispose()

###############################################################################
def test_canonical_schema_has_fifteen_application_tables_and_version_table(backend) -> None:
    tables = set(inspect(backend.engine).get_table_names())
    assert "alembic_version" in tables
    assert len(tables - {"alembic_version"}) == 15
    assert {"chat_sessions", "conversation_contexts"}.isdisjoint(tables)
    assert "active_run_id" not in {
        column["name"]
        for column in inspect(backend.engine).get_columns("conversations")
    }

###############################################################################
def test_conversation_messages_use_atomic_sequence_and_native_json(backend) -> None:
    with backend.session() as session:
        session.add(ConversationRecord(id="conv_conformance", title="Conformance"))
        session.commit()

    with backend.session() as session:
        session.execute(
            ConversationRecord.__table__.update()
            .where(ConversationRecord.id == "conv_conformance")
            .values(next_message_sequence=1)
        )
        session.add(
            ChatMessageRecord(
                conversation_id="conv_conformance",
                turn_index=1,
                role="user",
                content="Where is Rome?",
                structured_payload={"request_id": "req-1", "nested": [1, 2]},
            )
        )
        session.commit()

    with backend.session() as session:
        message = session.scalar(select(ChatMessageRecord))
        assert message is not None
        assert message.structured_payload == {"request_id": "req-1", "nested": [1, 2]}
        conversation = session.get(ConversationRecord, "conv_conformance")
        assert conversation is not None
        assert conversation.next_message_sequence == 1

###############################################################################
def test_conversation_allows_one_active_run_by_constraint(backend) -> None:
    with backend.session() as session:
        session.add(ConversationRecord(id="conv_run", title="Runs"))
        session.commit()

    with backend.session() as session:
        session.add(
            AgentRunRecord(
                id="run-1",
                conversation_id="conv_run",
                original_request="one",
                aggregated_request="one",
                active_slot=1,
            )
        )
        session.commit()
        session.add(
            AgentRunRecord(
                id="run-2",
                conversation_id="conv_run",
                original_request="two",
                aggregated_request="two",
                active_slot=1,
            )
        )
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()

    with backend.session() as session:
        assert session.get(AgentRunRecord, "run-1") is not None
        assert session.get(AgentRunRecord, "run-2") is None

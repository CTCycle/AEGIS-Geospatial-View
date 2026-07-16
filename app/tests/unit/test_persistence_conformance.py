from __future__ import annotations

import os
from pathlib import Path

import pytest
from sqlalchemy import inspect, select

from server.configurations import DatabaseSettings
from server.repositories.database.postgres import PostgresRepository
from server.repositories.database.sqlite import SQLiteRepository
from server.repositories.schemas.models import (
    AgentRunRecord,
    Base,
    ChatMessageRecord,
    ConversationRecord,
)


###############################################################################
def _sqlite_settings(path: Path) -> DatabaseSettings:
    return DatabaseSettings(
        database_path=str(path),
        embedded_database=True,
        engine=None,
        host=None,
        port=None,
        database_name=None,
        username=None,
        password=None,
        ssl=False,
        ssl_ca=None,
        connect_timeout=10,
        insert_batch_size=100,
    )


###############################################################################
@pytest.fixture(params=["sqlite", "postgres"])
def backend(request: pytest.FixtureRequest, tmp_path: Path):
    if request.param == "sqlite":
        repository = SQLiteRepository(_sqlite_settings(tmp_path / "conformance.db"))
    else:
        url = os.getenv("AEGIS_TEST_POSTGRES_URL")
        if not url:
            pytest.skip("AEGIS_TEST_POSTGRES_URL is not configured")
        repository = PostgresRepository(
            DatabaseSettings(
                database_path=str(tmp_path / "unused.db"),
                embedded_database=False,
                engine="postgresql+psycopg",
                host=url.split("@")[1].split(":")[0],
                port=5432,
                database_name="aegis_test",
                username="aegis",
                password="aegis",
                ssl=False,
                ssl_ca=None,
                connect_timeout=10,
                insert_batch_size=100,
            )
        )
    Base.metadata.drop_all(repository.engine)
    Base.metadata.create_all(repository.engine)
    yield repository
    Base.metadata.drop_all(repository.engine)


###############################################################################
def test_canonical_schema_has_fifteen_tables_and_no_legacy_tables(backend) -> None:
    tables = set(inspect(backend.engine).get_table_names())
    assert len(tables) == 15
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
        with pytest.raises(Exception):
            session.commit()

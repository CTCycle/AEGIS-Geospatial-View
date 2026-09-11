from __future__ import annotations

from server.configurations import DatabaseSettings
from server.repositories.agent_evidence import AgentEvidenceRepository
from server.repositories.conversations import ConversationRepository
from server.repositories.database.sqlite import SQLiteRepository
from server.repositories.schemas import Base


###############################################################################
def _database(tmp_path):  # noqa: ANN001
    database = SQLiteRepository(DatabaseSettings(database_path=str(tmp_path / "evidence.db")))
    Base.metadata.create_all(database.engine)
    return database


###############################################################################
def test_evidence_round_trip_checksum_and_parent_provenance(tmp_path) -> None:  # noqa: ANN001
    database = _database(tmp_path)
    conversation = ConversationRepository(database).create_conversation("Evidence")
    repository = AgentEvidenceRepository(database)

    parent = repository.create(
        conversation_id=conversation.id,
        run_id=None,
        kind="tabular",
        media_type="application/json",
        status="available",
        payload={
            "records": [{"id": "a", "value": 3}],
            "provider_metadata": {"access_token": "must-not-persist"},
        },
        summary={"record_count": 1, "api_key": "must-not-persist"},
        provenance={"provider": "test", "authorization": "redacted"},
    )
    child = repository.create(
        conversation_id=conversation.id,
        run_id=None,
        kind="derived",
        media_type="application/json",
        status="available",
        payload={"records": [{"id": "a"}]},
        summary={"record_count": 1},
        provenance={"operation": "field_projection"},
        parent_evidence_ids=[parent.evidence_id],
    )

    loaded = repository.get_payload(child.evidence_id)
    assert loaded is not None
    summary, raw = loaded
    assert summary.parent_evidence_ids == [parent.evidence_id]
    assert b'"id":"a"' in raw
    assert b"access_token" not in raw
    assert "api_key" not in parent.summary
    assert "authorization" not in parent.provenance


###############################################################################
def test_evidence_metadata_cascade_deletes_with_conversation(tmp_path) -> None:  # noqa: ANN001
    database = _database(tmp_path)
    conversation = ConversationRepository(database).create_conversation("Cascade")
    repository = AgentEvidenceRepository(database)
    item = repository.create(
        conversation_id=conversation.id,
        run_id=None,
        kind="diagnostic",
        media_type="application/json",
        status="failed",
        payload={"error": {"code": "provider_unavailable"}},
        summary={"status": "failed"},
    )
    assert repository.get_summary(item.evidence_id) is not None
    other = ConversationRepository(database).create_conversation("Other")
    assert repository.get_summary(item.evidence_id, conversation_id=other.id) is None
    assert repository.get_payload(item.evidence_id, conversation_id=other.id) is None
    with database.session() as session:
        record = session.get(type(conversation), conversation.id)
        session.delete(record)
        session.commit()
    assert repository.get_summary(item.evidence_id) is None

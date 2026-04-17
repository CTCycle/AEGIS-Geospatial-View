from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from AEGIS.server.repositories.chat_history import ChatHistoryRepository
from AEGIS.server.repositories.schemas.models import Base


###############################################################################
class _Backend:
    def __init__(self) -> None:
        self.engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
        Base.metadata.create_all(self.engine)
        self.session = sessionmaker(bind=self.engine, future=True)


###############################################################################
class _Database:
    def __init__(self) -> None:
        self.backend = _Backend()


###############################################################################
def test_get_latest_extracted_state_reads_nested_payload(monkeypatch) -> None:  # noqa: ANN001
    monkeypatch.setattr(
        "AEGIS.server.repositories.chat_history.get_database",
        lambda: _Database(),
    )
    repo = ChatHistoryRepository()
    session = repo.create_session(title="test")
    repo.append_message(session_id=session.id, role="user", content="Find Rome")
    repo.append_message(
        session_id=session.id,
        role="assistant",
        content="ok",
        structured_payload={
            "stage_a": {"has_location": True},
            "extracted_state": {
                "location": {"city": "Rome", "country": "Italy"},
                "coordinates": {"latitude": None, "longitude": None},
                "location_type": "city",
                "filters": ["traffic"],
                "user_goal": "Find Rome",
                "certainty": 0.9,
            },
        },
    )
    latest = repo.get_latest_extracted_state(session.id)
    assert latest is not None
    assert latest.location.city == "Rome"
    assert latest.filters == ["traffic"]
    assert latest.location_type == "city"


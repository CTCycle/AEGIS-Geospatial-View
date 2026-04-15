from __future__ import annotations

from AEGIS.server.repositories.chat_history import ChatHistoryRepository
from AEGIS.server.repositories.session_catalog import SessionCatalogRepository
from AEGIS.server.repositories.session_details import SessionDetailsRepository


def test_session_analytics_repositories_write_rows() -> None:
    history = ChatHistoryRepository()
    session = history.upsert_session(None, title="analytics")
    history.append_message(session_id=session.id, role="user", content="u")
    history.append_message(session_id=session.id, role="assistant", content="a")

    catalog = SessionCatalogRepository()
    details = SessionDetailsRepository()
    catalog.upsert_for_session(
        session_id=session.id,
        models={
            "parser": {"provider": "ollama", "name": "llama3.2"},
            "agent": {"provider": "ollama", "name": "llama3.2"},
            "chat": {"provider": "ollama", "name": "llama3.2"},
        },
    )
    details.insert_turn(
        session_id=session.id,
        message_id=2,
        user_message="u",
        chat_response="a",
        extracted_info={},
        response_time=0.1,
        has_triggered_search=False,
    )

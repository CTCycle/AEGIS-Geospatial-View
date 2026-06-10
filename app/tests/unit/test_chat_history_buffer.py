from __future__ import annotations

from server.services.chat.history_buffer import ChatHistoryBuffer


###############################################################################
class _HistoryRepoStub:

    # -------------------------------------------------------------------------
    def __init__(self) -> None:
        self.calls: int = 0
        self.messages: list[dict[str, object]] = [
            {"role": "user", "content": "first"},
            {"role": "assistant", "content": "second"},
        ]

    # -------------------------------------------------------------------------
    def list_recent_messages(
        self, session_id: int, limit: int
    ) -> list[dict[str, object]]:
        self.calls += 1
        return self.messages[-limit:]


###############################################################################
def test_history_buffer_hydrates_once_and_reuses_cache() -> None:
    repo = _HistoryRepoStub()
    buffer = ChatHistoryBuffer(history_repo=repo, max_messages=3)
    first = buffer.get_or_hydrate(7)
    second = buffer.get_or_hydrate(7)
    assert first == second
    assert repo.calls == 1


###############################################################################
def test_history_buffer_appends_and_trims() -> None:
    repo = _HistoryRepoStub()
    buffer = ChatHistoryBuffer(history_repo=repo, max_messages=2)
    buffer.get_or_hydrate(11)
    buffer.append(11, {"role": "user", "content": "third"})
    recent = buffer.list_recent(11)
    assert len(recent) == 2
    assert recent[0]["content"] == "second"
    assert recent[1]["content"] == "third"

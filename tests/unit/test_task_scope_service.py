from __future__ import annotations

from AEGIS.server.domain.extraction.models import ExtractedIntent
from AEGIS.server.services.agent.task_scope_service import TaskScopeService


def test_task_scope_reuses_location_for_referential_phrase() -> None:
    service = TaskScopeService()
    history = [
        {"role": "user", "content": "The Coliseum in Rome, Italy"},
        {"role": "assistant", "content": "Mapped."},
        {"role": "user", "content": "same place, show traffic"},
    ]
    decision = service.decide_scope(
        history=history,
        user_message="same place, show traffic",
        latest_state=ExtractedIntent(location={"city": "Rome"}, location_type="city"),
    )
    assert decision.starts_new_task is False
    assert decision.carry_forward_location is True
    assert decision.history_start_index == 0


def test_task_scope_starts_new_task_for_new_address() -> None:
    service = TaskScopeService()
    history = [
        {"role": "user", "content": "Find coordinates of Rome"},
        {"role": "assistant", "content": "41.9, 12.5"},
        {"role": "user", "content": "Via San Bernardo 17 Canobbio"},
    ]
    decision = service.decide_scope(
        history=history,
        user_message="Via San Bernardo 17 Canobbio",
        latest_state=ExtractedIntent(
            coordinates={"latitude": 41.9, "longitude": 12.5},
            filters=["traffic"],
            location_type="coordinates",
        ),
    )
    assert decision.starts_new_task is True
    assert decision.carry_forward_location is False
    assert decision.carry_forward_filters is False

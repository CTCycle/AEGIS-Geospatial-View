from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any

import pytest

from AEGIS.server.domain.chat import ChatTurnRequest
from AEGIS.server.domain.extraction.models import ExtractedIntent
from AEGIS.server.services.agent.orchestrator_turn import run_turn_impl


class _HistoryBufferStub:
    def append(self, *_args: Any, **_kwargs: Any) -> None:
        return None

    def get_or_hydrate(self, _session_id: int) -> list[dict[str, Any]]:
        return []

    def list_scoped(self, _session_id: int, *, start_index: int) -> list[dict[str, Any]]:
        assert start_index == 0
        return []


class _HistoryRepoStub:
    def __init__(self) -> None:
        self._counter = 0

    def upsert_session(self, _session_id: int | None, title: str | None = None) -> Any:
        return SimpleNamespace(id=1, title=title)

    def append_message(self, *, session_id: int, role: str, content: str, **_kwargs: Any) -> Any:
        self._counter += 1
        return SimpleNamespace(
            id=self._counter,
            session_id=session_id,
            turn_index=self._counter,
            role=role,
            content=content,
            created_at=datetime.now(UTC),
        )

    def get_latest_extracted_state(self, _session_id: int) -> None:
        return None


@dataclass
class _StageAStub:
    requires_data: bool = True
    requires_search: bool = False
    has_location: bool = False

    def model_dump(self, mode: str = "json") -> dict[str, Any]:
        _ = mode
        return {
            "requires_data": self.requires_data,
            "requires_search": self.requires_search,
            "has_location": self.has_location,
        }


@dataclass
class _LocationStub:
    address: str | None = None
    city: str | None = None
    country: str | None = None


@dataclass
class _CoordinatesStub:
    latitude: float | None = None
    longitude: float | None = None


@dataclass
class _StageBStub:
    location: _LocationStub = field(default_factory=_LocationStub)
    coordinates: _CoordinatesStub = field(default_factory=_CoordinatesStub)

    def model_dump(self, mode: str = "json") -> dict[str, Any]:
        _ = mode
        return {
            "location": {
                "address": self.location.address,
                "city": self.location.city,
                "country": self.location.country,
            },
            "coordinates": {
                "latitude": self.coordinates.latitude,
                "longitude": self.coordinates.longitude,
            },
        }


@dataclass
class _DecisionStub:
    execution_mode: str = "clarify"
    should_trigger_search: bool = False
    selected_basemap_id: str | None = None
    selected_overlay_ids: list[str] | None = None
    decision: str = "clarify"
    tool_target: str | None = None
    clarification_question: str | None = "Need a location."
    requires_geocoding: bool = False

    def model_dump(self, mode: str = "json") -> dict[str, Any]:
        _ = mode
        return {
            "execution_mode": self.execution_mode,
            "should_trigger_search": self.should_trigger_search,
            "selected_basemap_id": self.selected_basemap_id,
            "selected_overlay_ids": self.selected_overlay_ids or [],
        }

    def model_copy(self, *, update: dict[str, Any]) -> "_DecisionStub":
        data = self.__dict__.copy()
        data.update(update)
        return _DecisionStub(**data)


class _ParserServiceStub:
    def __init__(self, **_kwargs: Any) -> None:
        pass

    def parse_stage_a_intent(self, **_kwargs: Any) -> _StageAStub:
        return _StageAStub()

    def parse_stage_b_enrichment(self, **_kwargs: Any) -> _StageBStub:
        return _StageBStub()


class _DecisionServiceStub:
    def __init__(self, **_kwargs: Any) -> None:
        pass

    def _build_missing_location_decision(self) -> _DecisionStub:
        return _DecisionStub()


class _ChatResponseServiceStub:
    calls: list[dict[str, Any]] = []

    def __init__(self, **_kwargs: Any) -> None:
        pass

    def generate(self, **kwargs: Any) -> str:
        _ChatResponseServiceStub.calls.append(kwargs)
        return "stub-response"


class _VectorRetrieverStub:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def retrieve_candidates(self, query: str, **kwargs: Any) -> dict[str, list[dict[str, Any]]]:
        self.calls.append({"query": query, **kwargs})
        return {"basemaps": [], "overlays": [], "providers": []}


def _build_orchestrator() -> Any:
    vector_retriever = _VectorRetrieverStub()
    return SimpleNamespace(
        settings_repo=SimpleNamespace(
            get_or_create=lambda: SimpleNamespace(
                parser_model_provider="ollama",
                parser_model_name="model-a",
                agent_model_provider="ollama",
                agent_model_name="model-b",
                chat_model_provider="ollama",
                chat_model_name="model-c",
                ollama_url="http://localhost:11434",
            )
        ),
        history_repo=_HistoryRepoStub(),
        history_buffer=_HistoryBufferStub(),
        task_scope_service=SimpleNamespace(
            decide_scope=lambda **_kwargs: SimpleNamespace(
                history_start_index=0,
                starts_new_task=False,
                model_dump=lambda mode="json": {"starts_new_task": False},
            )
        ),
        session_catalog_repo=SimpleNamespace(upsert_for_session=lambda **_kwargs: None),
        session_details_repo=SimpleNamespace(insert_turn=lambda **_kwargs: None),
        llm_factory=object(),
        vector_retriever=vector_retriever,
        agent_tools=None,
        search_orchestrator=SimpleNamespace(),
        _check_ollama_availability=lambda _settings: (True, ""),
        _annotate_retrieval_candidates=lambda retrieval: retrieval,
        _overlay_candidates_by_provider=lambda overlays: overlays,
        _build_patch_from_stage_b=lambda **_kwargs: {},
        _apply_task_scope_to_state=lambda latest_state, merged_state, task_scope: merged_state,
        _normalize_extracted_state_for_turn=lambda extracted_state, user_message: extracted_state,
        _summarize_retrieval_for_context=lambda retrieval: {},
        _select_direct_tool_from_stage_a=lambda stage_a, available_tools: None,
        _fallback_overlay_ids_from_retrieval=lambda **_kwargs: [],
        _debug_log=lambda *_args, **_kwargs: None,
    )


async def _run_turn(monkeypatch: pytest.MonkeyPatch) -> tuple[Any, list[dict[str, Any]]]:
    from AEGIS.server.services.agent import orchestrator_turn

    _ChatResponseServiceStub.calls = []
    monkeypatch.setattr(orchestrator_turn, "ParserService", _ParserServiceStub)
    monkeypatch.setattr(orchestrator_turn, "DecisionService", _DecisionServiceStub)
    monkeypatch.setattr(orchestrator_turn, "ChatResponseService", _ChatResponseServiceStub)
    monkeypatch.setattr(
        orchestrator_turn,
        "build_conversation_context",
        lambda **_kwargs: "context",
    )
    monkeypatch.setattr(
        orchestrator_turn,
        "merge_extracted_intent",
        lambda base, patch: base,
    )

    orchestrator = _build_orchestrator()
    request = ChatTurnRequest(message="show me Rome weather")
    await run_turn_impl(orchestrator, request)
    return orchestrator.vector_retriever, _ChatResponseServiceStub.calls


def test_retriever_called_with_basemap_k(monkeypatch: pytest.MonkeyPatch) -> None:
    retriever, _ = asyncio.run(_run_turn(monkeypatch))
    assert retriever.calls
    assert retriever.calls[0]["basemap_k"] == 1
    assert retriever.calls[0]["top_k"] == 10
    assert retriever.calls[0]["overlay_k"] == 10


def test_chat_generate_called_with_execution_feedback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, calls = asyncio.run(_run_turn(monkeypatch))
    assert calls
    assert "execution_feedback" in calls[0]
    assert isinstance(calls[0]["execution_feedback"], dict)

"""Replay recorded live runs through the real final-answer gate and fallbacks.

The corpus (``fixtures/agent/final_answer_replay.json``) is exported by
``assets/QA/agent-loop/agent-loop-reliability-20261105/extract_final_answer_corpus.py``:
each case is a run's restored checkpoint, an answer and its human verdict.
"""

from __future__ import annotations

import copy
import json
from collections import deque
from pathlib import Path
from typing import Any

import pytest

from server.domain.agent.capability_route import AgentRunState
from server.domain.agent.reliability import AgentExecutionBudget
from server.domain.llm.types import LLMResult
from server.services.agent.agent_loop import AgentLoop, AgentLoopRequest
from server.services.agent.capability_router import CapabilityRouter
from server.services.agent.tool_executor import ToolExecutor
from server.services.agent.tool_registry import ToolRegistry

_CORPUS: dict[str, Any] = json.loads(
    (Path(__file__).parents[3] / "fixtures/agent/final_answer_replay.json").read_text(encoding="utf-8")
)
_CASES: list[dict[str, Any]] = _CORPUS["cases"]
_EMPTY_TEMPLATE = ("the place .", "place at .", "place at ;", "the place ;", " for .", " for ;")


###############################################################################
class _Provider:
    def __init__(self, answer: str) -> None:
        self.results = deque([LLMResult(content=answer)])

    # -------------------------------------------------------------------------
    async def achat(self, request: Any, **kwargs: Any) -> LLMResult:
        return self.results.popleft()


###############################################################################
class _Factory:
    def __init__(self, provider: _Provider) -> None:
        self.provider = provider

    # -------------------------------------------------------------------------
    def get_provider(self, provider: str) -> _Provider:
        return self.provider


###############################################################################
class _Catalog:
    def is_enabled(self, capability_id: str) -> bool:
        return True

    # -------------------------------------------------------------------------
    def access_available(self, capability_id: str) -> bool:
        return True

    # -------------------------------------------------------------------------
    def list_basemaps(self) -> list[dict[str, object]]:
        return []


###############################################################################
def _restore(run: str) -> AgentRunState:
    return AgentRunState.from_checkpoint(copy.deepcopy(_CORPUS["states"][run]))


###############################################################################
def _request(state: AgentRunState) -> AgentLoopRequest:
    return AgentLoopRequest(
        provider="fake", model="fake-model", state=state,
        budget=AgentExecutionBudget(total_seconds=10, hard_max_seconds=10),
    )


###############################################################################
def _loop(provider: _Provider) -> AgentLoop:
    catalog = _Catalog()
    registry = ToolRegistry(runtime_registry=catalog)  # type: ignore[arg-type]
    return AgentLoop(
        provider_factory=_Factory(provider),  # type: ignore[arg-type]
        capability_router=CapabilityRouter(
            capability_registry=catalog,  # type: ignore[arg-type]
            runtime_registry=catalog,  # type: ignore[arg-type]
        ),
        tool_registry=registry,
        tool_executor=ToolExecutor(tool_registry=registry),
    )


###############################################################################
async def _user_text(case: dict[str, Any]) -> tuple[str, str]:
    """Return the gate's verdict on the candidate and the text the user would get."""

    candidate = case["candidate"]
    provider = _Provider(candidate)
    loop = _loop(provider)
    verdict = await loop._verified_answer_text(  # pyright: ignore[reportPrivateUsage]
        _request(_restore(case["run"])), candidate, reason="replay"
    )
    state = _restore(case["run"])
    state.finalization_attempted = False
    if case["path"] == "verified_render":
        final = await loop._finalize_verified_render(_request(state), provider, [])  # pyright: ignore[reportPrivateUsage]
    elif case["path"] == "completed":
        final = await loop._finalize_completed_request(_request(state), provider, [])  # pyright: ignore[reportPrivateUsage]
    else:
        final = verdict
    return verdict, final


###############################################################################
@pytest.mark.asyncio
@pytest.mark.parametrize("case", _CASES, ids=[case["id"] for case in _CASES])
async def test_recorded_answer_gets_its_human_verdict(case: dict[str, Any]) -> None:
    verdict, final = await _user_text(case)

    if case["label"] == "accept":
        assert verdict == case["candidate"]
    else:
        assert verdict == ""
        assert final != case["candidate"]
    for expected in case.get("must_contain", []):
        assert expected in final
    for excluded in case.get("must_not_contain", []):
        assert excluded not in final
    assert not any(fragment in final for fragment in _EMPTY_TEMPLATE)


###############################################################################
def test_disclosure_names_a_targetless_obligation_without_an_empty_value() -> None:
    """A run with nothing resolved discloses what is missing in whole sentences."""

    state = _restore("9ab214")
    state.location_refs = {}
    state.render_verified = False
    state.completion_contract = None
    disclosure = AgentLoop.completion_summary(state).disclosure()

    assert "the name of the requested place" in disclosure
    assert "the requested place" in disclosure.replace("the name of the requested place", "")
    assert not any(fragment in disclosure for fragment in _EMPTY_TEMPLATE)

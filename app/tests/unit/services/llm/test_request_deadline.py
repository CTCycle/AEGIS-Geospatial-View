from __future__ import annotations

from time import monotonic

import pytest

from server.services.llm.ollama import OllamaProvider
from server.services.llm.request_deadline import remaining_request_seconds
from server.services.llm.types import LLMRequest


###############################################################################
class _Provider(OllamaProvider):
    # -------------------------------------------------------------------------
    def __init__(self) -> None:
        super().__init__(base_url="http://ollama-deadline.test")
        self.post_calls = 0
        self.stream_calls = 0

    # -------------------------------------------------------------------------
    def _post_json(self, path: str, payload: dict, **kwargs):  # noqa: ANN003, ANN201
        self.post_calls += 1
        return {}

    # -------------------------------------------------------------------------
    def _stream_post(self, path: str, payload: dict, **kwargs):  # noqa: ANN003, ANN201
        self.stream_calls += 1
        yield {}


###############################################################################
def _expired_request() -> LLMRequest:
    return LLMRequest(
        model="runtime-model",
        messages=[],
        metadata={"deadline_monotonic": monotonic() - 1.0},
    )


###############################################################################
def test_expired_ollama_request_never_starts_transport() -> None:
    provider = _Provider()
    request = _expired_request()

    with pytest.raises(TimeoutError):
        provider._post_json_for_request("/api/chat", {}, request)
    with pytest.raises(TimeoutError):
        list(provider._stream_post_for_request("/api/chat", {}, request))

    assert provider.post_calls == 0
    assert provider.stream_calls == 0


###############################################################################
@pytest.mark.parametrize("value", [None, True, False, "not-a-number", float("nan")])
def test_invalid_deadline_metadata_is_not_treated_as_a_bound(value) -> None:
    request = LLMRequest(
        model="runtime-model",
        messages=[],
        metadata={"deadline_monotonic": value},
    )

    assert remaining_request_seconds(request) is None

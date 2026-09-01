from __future__ import annotations

from types import SimpleNamespace

from server.services.llm.response_serialization import dump_response_payload


###############################################################################
def test_dump_response_payload_preserves_usage_from_sdk_like_objects() -> None:
    payload = dump_response_payload(
        SimpleNamespace(
            usage=SimpleNamespace(prompt_tokens=123, completion_tokens=9),
            response=SimpleNamespace(input_tokens=88),
        )
    )

    assert payload["usage"] == {"prompt_tokens": 123, "completion_tokens": 9}
    assert payload["response"] == {"input_tokens": 88}

from __future__ import annotations

from typing import Any
from unittest.mock import Mock, call

import pytest

from tests.e2e.helpers.model_capability_metadata import (
    selected_model_tool_support_metadata,
)


class _Response:
    def __init__(self, status: int, payload: dict[str, Any]) -> None:
        self.status = status
        self._payload = payload

    def json(self) -> dict[str, Any]:
        return self._payload


@pytest.mark.parametrize(
    ("supports_tools", "expected_ready", "expected_reason"),
    [
        (True, True, ""),
        (False, False, "Selected model metadata reports no tool-calling support."),
        (
            None,
            False,
            "Selected model tool-calling support is not verified by metadata.",
        ),
    ],
)
def test_selected_model_tool_support_uses_metadata_without_inference(
    supports_tools: bool | None,
    expected_ready: bool,
    expected_reason: str,
) -> None:
    request = Mock()
    request.get.side_effect = [
        _Response(
            200,
            {
                "agent_model_provider": "opencode-go",
                "agent_model_name": "beam-free",
            },
        ),
        _Response(
            200,
            {
                "cloud": [
                    {
                        "provider": "opencode-go",
                        "name": "beam-free",
                        "supports_tools": supports_tools,
                        "tool_support_source": "provider_protocol_registry",
                        "protocol": "openai-chat-completions",
                    }
                ],
                "local": [],
            },
        ),
    ]
    page = Mock(request=request)

    ready, reason, evidence = selected_model_tool_support_metadata(
        page, "http://127.0.0.1:8000/"
    )

    assert ready is expected_ready
    assert reason == expected_reason
    assert evidence["provider"] == "opencode-go"
    assert evidence["model"] == "beam-free"
    assert evidence["supports_tools"] is supports_tools
    assert request.get.call_args_list == [
        call("http://127.0.0.1:8000/api/chat/settings", timeout=10_000),
        call("http://127.0.0.1:8000/api/chat/models", timeout=10_000),
    ]
    request.post.assert_not_called()

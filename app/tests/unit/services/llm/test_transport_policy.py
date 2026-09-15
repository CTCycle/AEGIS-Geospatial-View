from __future__ import annotations

from types import SimpleNamespace

import pytest

from server.services.llm.errors import LLMProviderRequestError, safe_failure_detail
from server.services.llm.transport import LLMTransportPolicy


def test_transport_policy_controls_timeout_retry_proxy_and_environment() -> None:
    policy = LLMTransportPolicy(
        request_timeout_seconds=11.0,
        catalog_timeout_seconds=3.0,
        stream_timeout_seconds=19.0,
        structured_timeout_seconds=23.0,
        max_attempts=4,
        retry_backoff_base_seconds=0.5,
        retry_backoff_max_seconds=1.5,
        proxy="http://proxy.test:8080",
        trust_env=False,
    )

    assert policy.timeout_for("chat") == 11.0
    assert policy.timeout_for("catalog") == 3.0
    assert policy.timeout_for("stream") == 19.0
    assert policy.timeout_for("structured_output") == 23.0
    assert policy.retry_delay(1) == 0.5
    assert policy.retry_delay(4) == 1.5
    assert policy.httpx_options("chat") == {
        "timeout": 11.0,
        "trust_env": False,
        "proxy": "http://proxy.test:8080",
    }
    assert policy.client_args() == {
        "trust_env": False,
        "proxy": "http://proxy.test:8080",
    }


def test_transport_policy_rejects_invalid_values() -> None:
    with pytest.raises(ValueError, match="max_attempts"):
        LLMTransportPolicy(max_attempts=0)
    with pytest.raises(ValueError, match="proxy"):
        LLMTransportPolicy(proxy=42)  # type: ignore[arg-type]


def test_transport_policy_can_be_built_from_native_execution_settings() -> None:
    policy = LLMTransportPolicy.from_execution_settings(
        SimpleNamespace(
            native_model_call_seconds=7.5,
            model_max_attempts=3,
            retry_backoff_base_seconds=0.0,
            retry_backoff_max_seconds=0.0,
        )
    )

    assert policy.request_timeout_seconds == 7.5
    assert policy.stream_timeout_seconds == 7.5
    assert policy.max_attempts == 3
    assert policy.retry_delay(1) == 0.0


def test_winerror_10013_is_safe_and_not_retryable() -> None:
    class _PermissionDenied(OSError):
        winerror = 10013

    error = LLMProviderRequestError.from_exception(
        _PermissionDenied("provider secret should never be retained"),
        provider="opencode-go",
        model="deepseek-v4-flash",
        stage="chat",
    )

    assert error.retryable is False
    assert error.diagnostics["winerror"] == 10013
    assert "provider secret" not in str(error)
    assert "provider secret" not in safe_failure_detail(
        _PermissionDenied("provider secret should never be retained"),
        "Provider request failed.",
    )

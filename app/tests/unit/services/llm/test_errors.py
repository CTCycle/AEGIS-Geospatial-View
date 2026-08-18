from server.services.llm.errors import LLMProviderRequestError


def test_provider_connection_errors_are_retryable() -> None:
    error = LLMProviderRequestError.from_exception(
        ConnectionError("socket unavailable"),
        provider="opencode-go",
        model="mimo-v2.5",
        stage="structured_output",
    )

    assert error.code == "provider_request_failed"
    assert error.retryable is True


def test_non_transient_provider_errors_are_not_retryable() -> None:
    error = LLMProviderRequestError.from_exception(
        ValueError("invalid request"),
        provider="opencode-go",
        model="mimo-v2.5",
        stage="structured_output",
    )

    assert error.retryable is False

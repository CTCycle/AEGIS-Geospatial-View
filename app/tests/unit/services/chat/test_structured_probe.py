from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from server.domain.llm.types import LLMResult, LLMToolCall
from server.services.llm.errors import LLMProviderRequestError
from server.services.chat.structured_probe import StructuredProbeService


###############################################################################
def _settings() -> SimpleNamespace:
    return SimpleNamespace(
        agent_model_provider="opencode-go",
        agent_model_name="deepseek-v4-flash",
        ollama_url="http://127.0.0.1:11434",
        openai_base_url=None,
        google_base_url=None,
        deepseek_base_url="https://api.deepseek.com",
        credentials={"opencode-go": {"api_key": True}},
        credential_health={"opencode-go": {"api_key": "healthy"}},
    )


###############################################################################
class _SettingsService:

    # -------------------------------------------------------------------------
    def __init__(self) -> None:
        self.settings = _settings()

    # -------------------------------------------------------------------------
    def get_settings(self) -> SimpleNamespace:
        return self.settings


###############################################################################
class _Provider:

    # -------------------------------------------------------------------------
    def __init__(self, result: LLMResult | None = None, error: Exception | None = None) -> None:
        self.result = result
        self.error = error
        self.calls = 0
        self.requests: list[object] = []

    # -------------------------------------------------------------------------
    async def achat(self, *args: object, **_kwargs: object) -> LLMResult:
        self.calls += 1
        if args:
            self.requests.append(args[0])
        if self.error is not None:
            raise self.error
        if self.result is None:
            raise RuntimeError("missing probe result")
        return self.result


###############################################################################
class _ProviderFactory:

    # -------------------------------------------------------------------------
    def __init__(self, provider: _Provider) -> None:
        self.provider = provider

    # -------------------------------------------------------------------------
    def get_provider(self, _provider: str) -> _Provider:
        return self.provider

    # -------------------------------------------------------------------------
    def protocol_for_model(self, _model: str) -> str:
        return "openai-compatible"


def _parser_result() -> LLMResult:
    return LLMResult(
        content="",
        tool_calls=[
            LLMToolCall(
                id="route-1",
                name="route_request",
                arguments={
                    "primary_domain": "data_retrieval",
                    "task_mode": "execute",
                    "presentation": "map",
                    "requires_location": True,
                },
            )
        ],
    )


def _service(provider: _Provider) -> StructuredProbeService:
    return StructuredProbeService(
        provider_factory=_ProviderFactory(provider),
        settings_service=_SettingsService(),
    )


###############################################################################
@pytest.mark.asyncio
async def test_probe_is_not_tested_then_passed_and_cached() -> None:
    parser = _Provider(result=_parser_result())
    service = _service(parser)

    assert service.latest().status == "not_tested"
    result = await service.run()

    assert result.status == "passed"
    assert result.parse_status == "complete"
    assert result.checked_at is not None
    assert result.expires_at is not None
    assert result.expires_at > datetime.now(timezone.utc)
    assert service.latest() == result
    assert parser.calls == 1
    assert parser.requests[0].metadata["thinking_mode"] == "disabled"


###############################################################################
@pytest.mark.asyncio
async def test_probe_sanitizes_provider_failures_and_expires() -> None:
    parser = _Provider(
        error=LLMProviderRequestError(
            provider="opencode-go",
            model="deepseek-v4-flash",
            stage="probe",
            code="provider_http_error",
        )
    )
    settings_service = _SettingsService()
    service = StructuredProbeService(
        provider_factory=_ProviderFactory(parser),
        settings_service=settings_service,
    )

    result = await service.run()

    assert result.status == "failed"
    assert result.message == "Native tool probe failed."
    assert "secret" not in result.message.lower()

    protocol = service._protocol(
        settings_service.settings.agent_model_provider,
        settings_service.settings.agent_model_name,
        _ProviderFactory(parser),
    )
    key = service._cache_key(settings_service.settings, protocol)
    service._cache[key] = result.model_copy(
        update={
            "expires_at": datetime.now(timezone.utc) - timedelta(seconds=1),
        }
    )
    assert service.latest().status == "not_tested"


###############################################################################
@pytest.mark.asyncio
async def test_probe_timeout_does_not_retry_or_expose_provider_detail() -> None:
    parser = _Provider(error=asyncio.TimeoutError())
    service = _service(parser)

    result = await service.run()

    assert result.status == "timeout"
    assert result.parse_status == "timeout"
    assert result.message == "Native tool probe timed out."
    assert parser.calls == 1


###############################################################################
@pytest.mark.asyncio
async def test_probe_marks_model_capability_failure_unsupported() -> None:
    parser = _Provider(
        error=LLMProviderRequestError(
            provider="opencode-go",
            model="deepseek-v4-flash",
            stage="probe",
            code="provider_model_incompatible",
            category="model_capability",
        )
    )
    service = _service(parser)

    result = await service.run()

    assert result.status == "unsupported"
    assert result.parse_status == "unsupported"

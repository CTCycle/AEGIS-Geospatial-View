from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

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
class _Parser:

    # -------------------------------------------------------------------------
    def __init__(self, result: object | None = None, error: Exception | None = None) -> None:
        self.result = result
        self.error = error
        self.calls = 0

    # -------------------------------------------------------------------------
    async def parse_turn_with_usage_async(self, **_: object) -> object:
        self.calls += 1
        if self.error is not None:
            raise self.error
        return self.result


###############################################################################
def _parser_result(
    *,
    parse_status: str = "complete",
    provider_error: dict[str, object] | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        parser_contract={"response_parse_status": parse_status},
        turn_contract=SimpleNamespace(provider_error=provider_error),
    )


###############################################################################
@pytest.mark.asyncio
async def test_probe_is_not_tested_then_passed_and_cached() -> None:
    parser = _Parser(result=_parser_result())
    service = StructuredProbeService(
        parser_service=parser,
        settings_service=_SettingsService(),
    )

    assert service.latest().status == "not_tested"
    result = await service.run()

    assert result.status == "passed"
    assert result.parse_status == "complete"
    assert result.checked_at is not None
    assert result.expires_at is not None
    assert result.expires_at > datetime.now(timezone.utc)
    assert service.latest() == result
    assert parser.calls == 1


###############################################################################
@pytest.mark.asyncio
async def test_probe_sanitizes_provider_failures_and_expires() -> None:
    parser = _Parser(
        result=_parser_result(
            provider_error={
                "code": "provider_http_error",
                "message": "secret prompt and bearer token",
            }
        )
    )
    settings_service = _SettingsService()
    service = StructuredProbeService(
        parser_service=parser,
        settings_service=settings_service,
    )

    result = await service.run()

    assert result.status == "failed"
    assert result.message == "Structured parser probe failed."
    assert "secret" not in result.message.lower()

    protocol = service._protocol(
        settings_service.settings.agent_model_provider,
        settings_service.settings.agent_model_name,
        parser,
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
    parser = _Parser(error=asyncio.TimeoutError())
    service = StructuredProbeService(
        parser_service=parser,
        settings_service=_SettingsService(),
    )

    result = await service.run()

    assert result.status == "timeout"
    assert result.parse_status == "timeout"
    assert result.message == "Structured parser probe timed out."
    assert parser.calls == 1


###############################################################################
@pytest.mark.asyncio
async def test_probe_marks_model_capability_failure_unsupported() -> None:
    parser = _Parser(
        result=_parser_result(
            provider_error={
                "code": "provider_model_incompatible",
                "category": "model_capability",
            }
        )
    )
    service = StructuredProbeService(
        parser_service=parser,
        settings_service=_SettingsService(),
    )

    result = await service.run()

    assert result.status == "unsupported"
    assert result.parse_status == "unsupported"

from __future__ import annotations

import asyncio
import hashlib
import json
from datetime import datetime, timedelta, timezone
from time import monotonic, perf_counter
from typing import Any, Awaitable, Callable, Literal, cast

from server.common.typing import is_json_object
from server.contracts.chat import StructuredProbeResponse
from server.services.llm.errors import (
    LLMConfigurationError,
    LLMProviderRequestError,
    LLMStructuredOutputError,
)

ProbeStatus = Literal["not_tested", "passed", "failed", "timeout", "unsupported"]
PROBE_TTL_SECONDS = 15 * 60
PROBE_TIMEOUT_SECONDS = 30.0
PROBE_REQUEST = "Show a map of Italy"


###############################################################################
class StructuredProbeService:
    """Runs the real parser contract without creating a conversation side effect."""

    # -------------------------------------------------------------------------
    def __init__(self, *, parser_service: Any, settings_service: Any) -> None:
        self.parser_service = parser_service
        self.settings_service = settings_service
        self._cache: dict[str, StructuredProbeResponse] = {}

    # -------------------------------------------------------------------------
    def clear(self) -> None:
        self._cache.clear()

    # -------------------------------------------------------------------------
    def _settings(self) -> Any:
        return self.settings_service.get_settings()

    # -------------------------------------------------------------------------
    @staticmethod
    def _protocol(provider: str, model: str, parser_service: Any) -> str:
        normalized_provider = provider.strip().lower()
        if normalized_provider == "ollama":
            return "ollama-chat"
        if normalized_provider == "openai":
            return "openai-responses"
        if normalized_provider == "google":
            return "google-model"
        factory = getattr(parser_service, "llm_factory", None)
        if factory is not None:
            try:
                selected_provider = factory.get_provider(normalized_provider)
                protocol_for_model = getattr(selected_provider, "protocol_for_model", None)
                if callable(protocol_for_model):
                    protocol = protocol_for_model(model)
                    if isinstance(protocol, str) and protocol.strip():
                        return protocol.strip()
            except Exception:
                pass
        if normalized_provider == "deepseek":
            return "openai-chat-completions"
        if normalized_provider in {"opencode", "opencode-go"}:
            return "openai-compatible"
        return "unknown"

    # -------------------------------------------------------------------------
    @staticmethod
    def _credential_fingerprint(settings: Any) -> str:
        payload = {
            "provider": getattr(settings, "agent_model_provider", ""),
            "model": getattr(settings, "agent_model_name", ""),
            "ollama_url": getattr(settings, "ollama_url", ""),
            "openai_base_url": getattr(settings, "openai_base_url", None),
            "google_base_url": getattr(settings, "google_base_url", None),
            "deepseek_base_url": getattr(settings, "deepseek_base_url", None),
            "credentials": getattr(settings, "credentials", {}),
            "credential_health": getattr(settings, "credential_health", {}),
        }
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest()[:24]

    # -------------------------------------------------------------------------
    def _cache_key(self, settings: Any, protocol: str) -> str:
        provider = str(getattr(settings, "agent_model_provider", "")).strip()
        model = str(getattr(settings, "agent_model_name", "")).strip()
        return "|".join((provider, model, protocol, self._credential_fingerprint(settings)))

    # -------------------------------------------------------------------------
    @staticmethod
    def _not_tested(provider: str, model: str, protocol: str) -> StructuredProbeResponse:
        return StructuredProbeResponse(
            provider=provider,
            model=model,
            protocol=protocol,
            status="not_tested",
            parse_status="not_tested",
            duration_ms=None,
            checked_at=None,
            expires_at=None,
            message="This model has not been verified against the parser contract.",
        )

    # -------------------------------------------------------------------------
    def latest(self) -> StructuredProbeResponse:
        settings = self._settings()
        provider = str(getattr(settings, "agent_model_provider", "")).strip()
        model = str(getattr(settings, "agent_model_name", "")).strip()
        protocol = self._protocol(provider, model, self.parser_service)
        cached = self._cache.get(self._cache_key(settings, protocol))
        if cached is None:
            return self._not_tested(provider, model, protocol)
        if cached.expires_at is not None and cached.expires_at <= datetime.now(timezone.utc):
            self._cache.pop(self._cache_key(settings, protocol), None)
            return self._not_tested(provider, model, protocol)
        return cached

    # -------------------------------------------------------------------------
    @staticmethod
    def source_status(result: StructuredProbeResponse) -> dict[str, object]:
        return {
            "structured_probe_status": result.status,
            "structured_probe_checked_at": result.checked_at,
            "structured_probe_expires_at": result.expires_at,
        }

    # -------------------------------------------------------------------------
    @staticmethod
    def _safe_message(status: ProbeStatus) -> str:
        return {
            "not_tested": "This model has not been verified against the parser contract.",
            "passed": "Structured parser probe passed.",
            "failed": "Structured parser probe failed.",
            "timeout": "Structured parser probe timed out.",
            "unsupported": "The selected model does not support the structured parser contract.",
        }[status]

    # -------------------------------------------------------------------------
    async def run(self) -> StructuredProbeResponse:
        settings = self._settings()
        provider = str(getattr(settings, "agent_model_provider", "")).strip()
        model = str(getattr(settings, "agent_model_name", "")).strip()
        protocol = self._protocol(provider, model, self.parser_service)
        key = self._cache_key(settings, protocol)
        checked_at = datetime.now(timezone.utc)
        started = perf_counter()
        status: ProbeStatus = "failed"
        parse_status = "failed"
        try:
            deadline = monotonic() + PROBE_TIMEOUT_SECONDS
            parser_candidate = getattr(
                self.parser_service, "parse_turn_with_usage_async", None
            )
            if not callable(parser_candidate):
                raise LLMConfigurationError("The selected parser does not expose an async probe path.")
            parser = cast(Callable[..., Awaitable[Any]], parser_candidate)
            result = await asyncio.wait_for(
                parser(
                    user_message=PROBE_REQUEST,
                    memory_snapshot={},
                    conversation_messages=[],
                    deadline_monotonic=deadline,
                    provider_session_id=f"structured-probe-{self._credential_fingerprint(settings)}",
                ),
                timeout=PROBE_TIMEOUT_SECONDS + 0.5,
            )
            contract = getattr(result, "parser_contract", None)
            if is_json_object(contract):
                parse_status = str(contract.get("response_parse_status") or "failed")
            turn_contract = getattr(result, "turn_contract", None)
            provider_error = getattr(turn_contract, "provider_error", None)
            if is_json_object(provider_error):
                code = str(provider_error.get("code") or "")
                category = str(provider_error.get("category") or "")
                if (
                    category == "model_capability"
                    or "unsupported" in code
                    or "incompatible" in code
                    or code
                    in {
                        "model_structured_output_unsupported",
                        "structured_schema_unsupported",
                    }
                ):
                    status = "unsupported"
                elif "timeout" in code or "deadline" in code:
                    status = "timeout"
                else:
                    status = "failed"
                parse_status = status
            elif parse_status in {"complete", "intentional_ambiguity"}:
                status = "passed"
            else:
                status = "failed"
        except (asyncio.TimeoutError, TimeoutError):
            status = "timeout"
            parse_status = "timeout"
        except LLMProviderRequestError as exc:
            code = str(getattr(exc, "code", "") or "")
            category = str(getattr(exc, "category", "") or "")
            if category == "model_capability" or "unsupported" in code or "incompatible" in code:
                status = "unsupported"
            else:
                status = "timeout" if "timeout" in code or "deadline" in code else "failed"
            parse_status = status
        except LLMStructuredOutputError as exc:
            code = str(getattr(exc, "code", "") or "")
            category = str(getattr(exc, "category", "") or "")
            status = (
                "unsupported"
                if category == "model_capability"
                or "unsupported" in code
                or "incompatible" in code
                else "failed"
            )
            parse_status = status
        except LLMConfigurationError:
            status = "failed"
            parse_status = "failed"
        except Exception:
            status = "failed"
            parse_status = "failed"
        duration_ms = max(0, int((perf_counter() - started) * 1000))
        expires_at = checked_at + timedelta(seconds=PROBE_TTL_SECONDS)
        result = StructuredProbeResponse(
            provider=provider,
            model=model,
            protocol=protocol,
            status=status,
            parse_status=parse_status,
            duration_ms=duration_ms,
            checked_at=checked_at,
            expires_at=expires_at,
            message=self._safe_message(status),
        )
        self._cache[key] = result
        return result

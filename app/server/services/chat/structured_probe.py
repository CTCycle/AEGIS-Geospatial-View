from __future__ import annotations

import asyncio
import hashlib
import json
from datetime import datetime, timezone
from time import monotonic, perf_counter
from typing import Any, Literal

from server.contracts.chat import StructuredProbeResponse
from server.domain.agent.capability_route import CapabilityRoute
from server.domain.llm.types import LLMRequest, LLMToolDefinition
from server.prompts.capability_route import build_capability_route_prompt
from server.repositories.model_probe_results import ModelProbeResultRepository
from server.services.llm.errors import (
    LLMConfigurationError,
    LLMProviderRequestError,
    LLMStructuredOutputError,
)
from server.services.llm.provider_contract import require_canonical_provider

ProbeStatus = Literal["not_tested", "passed", "failed", "timeout", "unsupported"]
PROBE_TIMEOUT_SECONDS = 30.0
PROBE_REQUEST = "Show a map of Italy"

###############################################################################
class StructuredProbeService:
    """Probe the native route/tool contract without creating conversation state."""

    # -------------------------------------------------------------------------
    def __init__(
        self,
        *,
        provider_factory: Any,
        settings_service: Any,
        repository: ModelProbeResultRepository,
    ) -> None:
        self.provider_factory = provider_factory
        self.settings_service = settings_service
        self.repository = repository

    # -------------------------------------------------------------------------
    def _settings(self) -> Any:
        return self.settings_service.get_settings()

    # -------------------------------------------------------------------------
    @staticmethod
    def _protocol(provider: str, model: str, provider_factory: Any) -> str:
        if provider == "ollama":
            return "ollama-chat"
        if provider == "openai":
            return "openai-responses"
        if provider == "google":
            return "google-model"
        if provider == "deepseek":
            return "openai-chat-completions"
        if provider_factory is not None:
            try:
                selected_provider = provider_factory.get_provider(provider)
                protocol_for_model = getattr(selected_provider, "protocol_for_model", None)
                if callable(protocol_for_model):
                    protocol = protocol_for_model(model)
                    if isinstance(protocol, str) and protocol.strip():
                        return protocol.strip()
            except Exception:
                pass
        return "unknown"

    # -------------------------------------------------------------------------
    def _credential_fingerprint(self, settings: Any) -> str:
        """Identify what a verdict depends on: the selected model's endpoint and key.

        Unrelated settings (other providers, geospatial keys) must not
        invalidate a verdict, but replacing the selected provider's key or
        endpoint must.
        """

        provider = str(getattr(settings, "agent_model_provider", ""))
        endpoint_attribute = {
            "ollama": "ollama_url",
            "openai": "openai_base_url",
            "google": "google_base_url",
            "deepseek": "deepseek_base_url",
        }.get(provider)
        identity = getattr(self.settings_service, "credential_identity", None)
        payload = {
            "provider": provider,
            "model": getattr(settings, "agent_model_name", ""),
            "endpoint": getattr(settings, endpoint_attribute, None)
            if endpoint_attribute
            else None,
            "credential": identity(provider) if callable(identity) else "",
        }
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest()[:24]

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
            message="This model has not been verified against the native tool contract.",
        )

    # -------------------------------------------------------------------------
    def latest(self) -> StructuredProbeResponse:
        settings = self._settings()
        provider = str(getattr(settings, "agent_model_provider", ""))
        model = str(getattr(settings, "agent_model_name", "")).strip()
        protocol = self._protocol(provider, model, self.provider_factory)
        stored = self.repository.get(
            provider=provider,
            model=model,
            protocol=protocol,
            fingerprint=self._credential_fingerprint(settings),
        )
        return stored or self._not_tested(provider, model, protocol)

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
            "not_tested": "This model has not been verified against the native tool contract.",
            "passed": "Native tool probe passed.",
            "failed": "Native tool probe failed.",
            "timeout": "Native tool probe timed out.",
            "unsupported": "The selected model does not support the native tool contract.",
        }[status]

    # -------------------------------------------------------------------------
    async def run(self) -> StructuredProbeResponse:
        settings = self._settings()
        provider_id = str(getattr(settings, "agent_model_provider", ""))
        model = str(getattr(settings, "agent_model_name", "")).strip()
        try:
            require_canonical_provider(provider_id)
        except ValueError:
            protocol = "unknown"
            checked_at = datetime.now(timezone.utc)
            result = StructuredProbeResponse(
                provider=provider_id,
                model=model,
                protocol=protocol,
                status="failed",
                parse_status="failed",
                duration_ms=0,
                checked_at=checked_at,
                expires_at=None,
                message="The selected provider ID is not canonical and cannot be probed.",
            )
            return result
        protocol = self._protocol(provider_id, model, self.provider_factory)
        checked_at = datetime.now(timezone.utc)
        started = perf_counter()
        status: ProbeStatus = "failed"
        parse_status = "failed"
        try:
            deadline = monotonic() + PROBE_TIMEOUT_SECONDS
            provider = self.provider_factory.get_provider(provider_id)
            request_metadata: dict[str, Any] = {
                "supports_tools": True,
                "deadline_monotonic": deadline,
            }
            if provider_id == "opencode-go":
                # OpenCode Go thinking-mode models reject explicit tool_choice
                # values.  The native agent route uses the same compatible
                # no-thinking mode for tool calls; keep the structured probe
                # on that exact transport contract as well.
                request_metadata["thinking_mode"] = "disabled"
            request = LLMRequest(
                model=model,
                provider=provider_id,
                provider_session_id=f"structured-probe-{self._credential_fingerprint(settings)}",
                messages=[
                    {"role": "system", "content": build_capability_route_prompt()},
                    {"role": "user", "content": PROBE_REQUEST},
                ],
                tools=[
                    LLMToolDefinition(
                        name="route_request",
                        description="Select one bounded high-level AEGIS capability route.",
                        parameters_json_schema=CapabilityRoute.model_json_schema(),
                    )
                ],
                tool_choice="required",
                metadata=request_metadata,
            )
            result = await asyncio.wait_for(
                provider.achat(
                    request,
                    tools=request.tools,
                    tool_choice="required",
                ),
                timeout=PROBE_TIMEOUT_SECONDS + 0.5,
            )
            call = result.tool_calls[0] if result.tool_calls else None
            if (
                call is not None
                and call.name == "route_request"
                and call.parse_error is None
                and call.arguments is not None
            ):
                CapabilityRoute.model_validate(call.arguments)
                parse_status = "complete"
                status = "passed"
            else:
                status = "failed"
                parse_status = "failed"
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
        result = StructuredProbeResponse(
            provider=provider_id,
            model=model,
            protocol=protocol,
            status=status,
            parse_status=parse_status,
            duration_ms=duration_ms,
            checked_at=checked_at,
            expires_at=None,
            message=self._safe_message(status),
        )
        if status == "timeout":
            # A timeout says nothing about the model; drop the previous verdict
            # so the UI reflects the test just run rather than a stale result.
            self.repository.discard(provider=provider_id, model=model)
        else:
            self.repository.save(
                result, fingerprint=self._credential_fingerprint(settings)
            )
        return result

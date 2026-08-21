from __future__ import annotations

from typing import Any

from server.services.llm.types import FailureCategory

###############################################################################
class LLMConfigurationError(ValueError):
    """Raised when a selected LLM provider cannot be used due to local settings."""


###############################################################################
class LLMStructuredOutputError(RuntimeError):
    """Safe structured-output failure with a user-actionable category."""

    # -------------------------------------------------------------------------
    def __init__(
        self,
        *,
        category: FailureCategory,
        provider: str,
        model: str,
        stage: str,
        code: str,
        detail: str,
        retryable: bool = False,
        http_status: int | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        self.category = category
        self.provider = provider
        self.model = model
        self.stage = stage
        self.code = code
        self.detail = detail
        self.retryable = retryable
        self.http_status = http_status
        self.metadata = dict(metadata or {})
        super().__init__(detail)


###############################################################################
class LLMContextLimitError(LLMStructuredOutputError):
    """Raised when the selected model cannot accept the prepared context."""

    # -------------------------------------------------------------------------
    def __init__(self, *, provider: str, model: str, stage: str, detail: str) -> None:
        super().__init__(
            category="context_limit",
            provider=provider,
            model=model,
            stage=stage,
            code="context_limit_exceeded",
            detail=detail,
        )


###############################################################################
class LLMRequestSchemaError(LLMStructuredOutputError):
    """Raised for invalid local response schemas or native tool definitions."""

    # -------------------------------------------------------------------------
    def __init__(self, *, provider: str, model: str, stage: str, detail: str) -> None:
        super().__init__(
            category="schema_definition",
            provider=provider,
            model=model,
            stage=stage,
            code="invalid_schema_definition",
            detail=detail,
        )


###############################################################################
class LLMResponseParsingError(LLMStructuredOutputError):
    """Raised when a provider response cannot satisfy the requested schema."""

    # -------------------------------------------------------------------------
    def __init__(self, *, provider: str, model: str, stage: str, detail: str) -> None:
        super().__init__(
            category="response_parsing",
            provider=provider,
            model=model,
            stage=stage,
            code="response_parsing_failed",
            detail=detail,
        )

###############################################################################
class LLMProviderRequestError(RuntimeError):
    """Safe, structured provider failure without response-body or credential leakage."""

    # -------------------------------------------------------------------------
    def __init__(
        self,
        *,
        provider: str,
        model: str,
        stage: str,
        code: str,
        http_status: int | None = None,
        retryable: bool = False,
        category: FailureCategory = "provider_api",
    ) -> None:
        self.provider = provider
        self.model = model
        self.stage = stage
        self.code = code
        self.http_status = http_status
        self.retryable = retryable
        self.category = category
        detail = f"{provider} rejected {model} during {stage}"
        if http_status is not None:
            detail += f" (HTTP {http_status})"
        super().__init__(detail + ".")

    # -------------------------------------------------------------------------
    @classmethod
    def from_exception(cls, exc: Exception, *, provider: str, model: str, stage: str) -> "LLMProviderRequestError":
        status = getattr(getattr(exc, "response", None), "status_code", None)
        if not isinstance(status, int):
            status = getattr(exc, "status_code", None)
        if not isinstance(status, int):
            status = getattr(exc, "code", None)
        text = str(exc).lower()
        if any(
            marker in text
            for marker in (
                "context length",
                "context window",
                "context_length_exceeded",
                "maximum context",
                "prompt is too long",
                "too many tokens",
                "token limit",
            )
        ) and status in {None, 400, 413}:
            code, retryable = "context_limit_exceeded", False
            category: FailureCategory = "context_limit"
        elif status == 400:
            capability_markers = (
                "does not support",
                "unsupported model",
                "tool calling is not",
                "structured output is not",
                "response format is not supported",
            )
            schema_markers = (
                "invalid schema",
                "malformed schema",
                "invalid tool",
                "tool definition",
                "json schema",
            )
            if any(marker in text for marker in capability_markers):
                code, retryable = "provider_model_incompatible", False
                category = "model_capability"
            elif any(marker in text for marker in schema_markers):
                code, retryable = "provider_schema_rejected", False
                category = "schema_definition"
            else:
                code, retryable = "provider_bad_request", False
                category = "provider_api"
        elif status in {401, 403}:
            code, retryable = "provider_authentication_failed", False
            category = "provider_api"
        elif status == 429:
            code, retryable = "provider_rate_limited", True
            category = "provider_api"
        elif isinstance(status, int) and status >= 500:
            code, retryable = "provider_unavailable", True
            category = "provider_api"
        elif cls._is_transient_connection_error(exc):
            code, retryable = "provider_request_failed", True
            category = "provider_api"
        else:
            code, retryable = "provider_request_failed", False
            category = "provider_api"
        return cls(
            provider=provider,
            model=model,
            stage=stage,
            code=code,
            http_status=status if isinstance(status, int) else None,
            retryable=retryable,
            category=category,
        )

    # -------------------------------------------------------------------------
    @staticmethod
    def _is_transient_connection_error(exc: Exception) -> bool:
        current: BaseException | None = exc
        for _ in range(4):
            if current is None:
                break
            class_name = type(current).__name__.casefold()
            detail = str(current).casefold()
            if (
                isinstance(current, (TimeoutError, ConnectionError))
                or any(
                    marker in class_name
                    for marker in ("connection", "connecterror", "timeout")
                )
                or any(
                    marker in detail
                    for marker in ("connection error", "winerror 100", "timed out")
                )
            ):
                return True
            current = current.__cause__ or current.__context__
        return False


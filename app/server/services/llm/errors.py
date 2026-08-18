from __future__ import annotations

###############################################################################
class LLMConfigurationError(ValueError):
    """Raised when a selected LLM provider cannot be used due to local settings."""

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
    ) -> None:
        self.provider = provider
        self.model = model
        self.stage = stage
        self.code = code
        self.http_status = http_status
        self.retryable = retryable
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
        if status == 400:
            code, retryable = "provider_model_incompatible", False
        elif status in {401, 403}:
            code, retryable = "provider_authentication_failed", False
        elif status == 429:
            code, retryable = "provider_rate_limited", True
        elif isinstance(status, int) and status >= 500:
            code, retryable = "provider_unavailable", True
        elif cls._is_transient_connection_error(exc):
            code, retryable = "provider_request_failed", True
        else:
            code, retryable = "provider_request_failed", False
        return cls(
            provider=provider,
            model=model,
            stage=stage,
            code=code,
            http_status=status if isinstance(status, int) else None,
            retryable=retryable,
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


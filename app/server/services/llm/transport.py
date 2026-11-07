from __future__ import annotations

import math

from dataclasses import dataclass
from typing import Any, cast

###############################################################################
@dataclass(frozen=True)
class LLMTransportPolicy:
    """Canonical transport and retry policy shared by every LLM adapter."""

    request_timeout_seconds: float = 30.0
    catalog_timeout_seconds: float = 5.0
    stream_timeout_seconds: float = 60.0
    structured_timeout_seconds: float = 90.0
    max_attempts: int = 2
    retry_backoff_base_seconds: float = 0.25
    retry_backoff_max_seconds: float = 2.0
    retry_after_max_seconds: float = 20.0
    # A rate-limited provider usually throttles for longer than its Retry-After
    # hint; its retries back off 2, 4, 8, 16, 16 s (about 46 s) before giving up.
    rate_limit_max_attempts: int = 6
    rate_limit_backoff_base_seconds: float = 2.0
    rate_limit_backoff_max_seconds: float = 16.0
    proxy: str | None = None
    trust_env: bool = False

    # -------------------------------------------------------------------------
    def __post_init__(self) -> None:
        for name in (
            "request_timeout_seconds",
            "catalog_timeout_seconds",
            "stream_timeout_seconds",
            "structured_timeout_seconds",
        ):
            value = float(getattr(self, name))
            if not math.isfinite(value) or value <= 0:
                raise ValueError(f"{name} must be finite and positive")
        if self.max_attempts < 1 or self.rate_limit_max_attempts < 1:
            raise ValueError("max_attempts must be positive")
        proxy = cast(object, self.proxy)
        if proxy is not None and not isinstance(proxy, str):
            raise ValueError("proxy must be a string when configured")
        if isinstance(proxy, str) and not proxy.strip():
            raise ValueError("proxy must be a non-empty string when configured")
        for name in (
            "retry_backoff_base_seconds",
            "retry_backoff_max_seconds",
            "retry_after_max_seconds",
            "rate_limit_backoff_base_seconds",
            "rate_limit_backoff_max_seconds",
        ):
            value = float(getattr(self, name))
            if not math.isfinite(value) or value < 0:
                raise ValueError(f"{name} must be finite and non-negative")

    # -------------------------------------------------------------------------
    @classmethod
    def from_execution_settings(
        cls, settings: Any | None = None
    ) -> "LLMTransportPolicy":
        """Build one policy from the existing native execution settings."""

        model_timeout = _positive_float(
            getattr(settings, "native_model_call_seconds", None),
            default=30.0,
        )
        max_attempts = _positive_int(
            getattr(settings, "model_max_attempts", None),
            default=2,
        )
        return cls(
            request_timeout_seconds=model_timeout,
            stream_timeout_seconds=model_timeout,
            max_attempts=max_attempts,
            retry_backoff_base_seconds=_non_negative_float(
                getattr(settings, "retry_backoff_base_seconds", None),
                default=0.25,
            ),
            retry_backoff_max_seconds=_non_negative_float(
                getattr(settings, "retry_backoff_max_seconds", None),
                default=2.0,
            ),
        )

    # -------------------------------------------------------------------------
    def httpx_options(self, stage: str) -> dict[str, Any]:
        options: dict[str, Any] = {
            "timeout": self.timeout_for(stage),
            "trust_env": self.trust_env,
        }
        if self.proxy:
            options["proxy"] = self.proxy
        return options

    # -------------------------------------------------------------------------
    def client_args(self) -> dict[str, Any]:
        options: dict[str, Any] = {"trust_env": self.trust_env}
        if self.proxy:
            options["proxy"] = self.proxy
        return options

    # -------------------------------------------------------------------------
    def timeout_for(self, stage: str) -> float:
        if stage == "catalog":
            return self.catalog_timeout_seconds
        if stage == "stream":
            return self.stream_timeout_seconds
        if stage == "structured_output":
            return self.structured_timeout_seconds
        return self.request_timeout_seconds

    # -------------------------------------------------------------------------
    def attempts_for(self, *, rate_limited: bool) -> int:
        """Attempts allowed for a failing call; rate limits get the longer schedule."""

        if rate_limited:
            return max(self.max_attempts, self.rate_limit_max_attempts)
        return self.max_attempts

    # -------------------------------------------------------------------------
    def retry_delay(
        self,
        attempt: int,
        retry_after_seconds: float | None = None,
        *,
        rate_limited: bool = False,
    ) -> float:
        """Return the delay before the next attempt.

        Bounded exponential backoff (the slower rate-limit schedule for a
        rate-limited call), raised to the provider's Retry-After hint (itself
        capped by ``retry_after_max_seconds``) when one was supplied.
        """

        exponent = max(0, int(attempt) - 1)
        base, ceiling = (
            (self.rate_limit_backoff_base_seconds, self.rate_limit_backoff_max_seconds)
            if rate_limited
            else (self.retry_backoff_base_seconds, self.retry_backoff_max_seconds)
        )
        backoff = min(ceiling, base * (2**exponent))
        if retry_after_seconds is None:
            return backoff
        return max(backoff, min(retry_after_seconds, self.retry_after_max_seconds))

###############################################################################
def close_sync_client(client: object) -> None:
    close = getattr(client, "close", None)
    if not callable(close):
        return
    try:
        close()
    except Exception:
        return

###############################################################################
def _positive_float(value: object, *, default: float) -> float:
    if isinstance(value, bool):
        return default
    try:
        parsed = float(value)  # type: ignore[arg-type]
    except TypeError, ValueError:
        return default
    return parsed if math.isfinite(parsed) and parsed > 0 else default

###############################################################################
def _non_negative_float(value: object, *, default: float) -> float:
    if isinstance(value, bool):
        return default
    try:
        parsed = float(value)  # type: ignore[arg-type]
    except TypeError, ValueError:
        return default
    return parsed if math.isfinite(parsed) and parsed >= 0 else default

###############################################################################
def _positive_int(value: object, *, default: int) -> int:
    if isinstance(value, bool):
        return default
    try:
        parsed = int(value)  # type: ignore[arg-type]
    except TypeError, ValueError:
        return default
    return parsed if parsed > 0 else default

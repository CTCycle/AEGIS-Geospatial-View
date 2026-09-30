from __future__ import annotations

import json
import inspect
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from email.utils import parsedate_to_datetime
from datetime import UTC, datetime
from collections.abc import Awaitable, Callable
from typing import Any, Generator
from urllib.parse import urlsplit

import httpx

from server.services.geospatial.providers.base import (
    ProviderAuthError,
    ProviderError,
    ProviderInvalidQueryError,
    ProviderMalformedPayloadError,
    ProviderRateLimitError,
    ProviderTimeoutError,
    ProviderUnavailableError,
)

JsonFetcher = Callable[[str, dict[str, str] | None], Awaitable[Any] | Any]
BytesFetcher = Callable[[str, dict[str, str] | None], Awaitable[bytes] | bytes]
TextFetcher = Callable[[str, dict[str, str] | None], Awaitable[str] | str]


@dataclass(frozen=True, slots=True)
class RasterHttpDiagnostic:
    """Safe operational metadata for a raster request failure."""

    category: str
    failure_phase: str
    upstream: str
    status_code: int | None = None
    content_type: str | None = None
    content_length: int | None = None
    provider_id: str | None = None
    capability_id: str | None = None


class RasterHttpError(ProviderError):
    """Internal raster error carrying sanitized upstream diagnostics."""

    def __init__(self, message: str, diagnostic: RasterHttpDiagnostic) -> None:
        super().__init__(message)
        self.diagnostic = diagnostic


@dataclass(frozen=True, slots=True)
class _RasterDiagnosticContext:
    provider_id: str
    capability_id: str


_RASTER_DIAGNOSTIC_CONTEXT: ContextVar[_RasterDiagnosticContext | None] = ContextVar(
    "raster_diagnostic_context",
    default=None,
)

_DEFAULT_TIMEOUT = httpx.Timeout(20.0)
DEFAULT_MAX_RESPONSE_BYTES = 16 * 1024 * 1024
_ASYNC_HTTP_CLIENT = httpx.AsyncClient(
    timeout=_DEFAULT_TIMEOUT,
    follow_redirects=False,
)
_REQUEST_TIMEOUT_SECONDS: ContextVar[float | None] = ContextVar(
    "provider_request_timeout_seconds",
    default=None,
)


@contextmanager
def raster_diagnostic_scope(
    *, provider_id: str, capability_id: str
) -> Generator[None, None, None]:
    """Attach safe provider/capability identifiers to raster diagnostics."""

    token = _RASTER_DIAGNOSTIC_CONTEXT.set(
        _RasterDiagnosticContext(
            provider_id=provider_id,
            capability_id=capability_id,
        )
    )
    try:
        yield
    finally:
        _RASTER_DIAGNOSTIC_CONTEXT.reset(token)

###############################################################################
@contextmanager
def request_timeout_scope(timeout_seconds: float | None) -> Generator[None, None, None]:
    """Apply one provider request's remaining timeout to shared HTTP helpers."""

    token = _REQUEST_TIMEOUT_SECONDS.set(
        None
        if timeout_seconds is None
        else max(0.001, float(timeout_seconds))
    )
    try:
        yield
    finally:
        _REQUEST_TIMEOUT_SECONDS.reset(token)

###############################################################################
async def fetch_json_url(url: str, headers: dict[str, str] | None = None) -> Any:
    body = await fetch_bytes_url(url, headers)
    try:
        return json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ProviderMalformedPayloadError(
            "Provider returned malformed JSON."
        ) from exc

###############################################################################
async def fetch_bytes_url(
    url: str,
    headers: dict[str, str] | None = None,
    *,
    max_bytes: int = DEFAULT_MAX_RESPONSE_BYTES,
) -> bytes:
    try:
        request_kwargs: dict[str, Any] = {"headers": headers or {}}
        timeout_seconds = _REQUEST_TIMEOUT_SECONDS.get()
        if timeout_seconds is not None:
            request_kwargs["timeout"] = timeout_seconds
        async with _ASYNC_HTTP_CLIENT.stream(
            "GET", url, **request_kwargs
        ) as response:
            _raise_for_status(response)
            content_length = response.headers.get("content-length")
            if content_length and _valid_content_length(content_length) > max_bytes:
                raise ProviderUnavailableError(
                    "Provider response exceeded the configured size limit."
                )
            chunks: list[bytes] = []
            total = 0
            async for chunk in response.aiter_bytes():
                total += len(chunk)
                if total > max_bytes:
                    raise ProviderUnavailableError(
                        "Provider response exceeded the configured size limit."
                    )
                chunks.append(chunk)
            return b"".join(chunks)
    except ProviderError:
        raise
    except httpx.TimeoutException as exc:
        raise ProviderTimeoutError("Provider request timed out.") from exc
    except httpx.HTTPError as exc:
        raise ProviderUnavailableError("Provider request failed.") from exc


async def fetch_raster_image_url(
    url: str,
    headers: dict[str, str] | None = None,
    *,
    max_bytes: int = DEFAULT_MAX_RESPONSE_BYTES,
) -> bytes:
    """Fetch and validate a raster body while retaining safe failure metadata.

    This helper is intentionally separate from ``fetch_bytes_url`` so existing
    provider adapters keep their public error behavior unchanged.
    """

    safe_upstream = _safe_upstream_url(url)
    context = _RASTER_DIAGNOSTIC_CONTEXT.get()
    content_type: str | None = None
    content_length: int | None = None
    failure_phase = "request"
    try:
        request_kwargs: dict[str, Any] = {"headers": headers or {}}
        timeout_seconds = _REQUEST_TIMEOUT_SECONDS.get()
        if timeout_seconds is not None:
            request_kwargs["timeout"] = timeout_seconds
        async with _ASYNC_HTTP_CLIENT.stream(
            "GET", url, **request_kwargs
        ) as response:
            content_type = _safe_content_type(response.headers.get("content-type"))
            content_length = _content_length(response.headers.get("content-length"))
            failure_phase = "response_headers"
            try:
                _raise_for_status(response)
            except ProviderError as exc:
                raise _raster_http_error(
                    message=str(exc),
                    url=safe_upstream,
                    context=context,
                    category=_status_category(response.status_code),
                    failure_phase=failure_phase,
                    status_code=response.status_code,
                    content_type=content_type,
                    content_length=content_length,
                ) from exc
            if content_length is not None and content_length > max_bytes:
                raise _raster_http_error(
                    message="Provider response exceeded the configured size limit.",
                    url=safe_upstream,
                    context=context,
                    category="response_too_large",
                    failure_phase=failure_phase,
                    status_code=response.status_code,
                    content_type=content_type,
                    content_length=content_length,
                )

            failure_phase = "response_body"
            chunks: list[bytes] = []
            total = 0
            try:
                async for chunk in response.aiter_bytes():
                    total += len(chunk)
                    if total > max_bytes:
                        raise _raster_http_error(
                            message="Provider response exceeded the configured size limit.",
                            url=safe_upstream,
                            context=context,
                            category="response_too_large",
                            failure_phase=failure_phase,
                            status_code=response.status_code,
                            content_type=content_type,
                            content_length=content_length or total,
                        )
                    chunks.append(chunk)
            except RasterHttpError:
                raise
            except httpx.ConnectTimeout as exc:
                raise _raster_http_error(
                    message="Provider request timed out.",
                    url=safe_upstream,
                    context=context,
                    category="connect_timeout",
                    failure_phase=failure_phase,
                    status_code=response.status_code,
                    content_type=content_type,
                    content_length=content_length,
                ) from exc
            except httpx.ReadTimeout as exc:
                raise _raster_http_error(
                    message="Provider response timed out.",
                    url=safe_upstream,
                    context=context,
                    category="read_timeout",
                    failure_phase=failure_phase,
                    status_code=response.status_code,
                    content_type=content_type,
                    content_length=content_length,
                ) from exc
            except httpx.ProxyError as exc:
                raise _raster_http_error(
                    message="Provider proxy request failed.",
                    url=safe_upstream,
                    context=context,
                    category="proxy_failure",
                    failure_phase=failure_phase,
                    status_code=response.status_code,
                    content_type=content_type,
                    content_length=content_length,
                ) from exc
            except (httpx.RemoteProtocolError, httpx.ReadError) as exc:
                raise _raster_http_error(
                    message="Provider connection was interrupted.",
                    url=safe_upstream,
                    context=context,
                    category="remote_protocol_failure",
                    failure_phase=failure_phase,
                    status_code=response.status_code,
                    content_type=content_type,
                    content_length=content_length,
                ) from exc
            except httpx.ConnectError as exc:
                raise _raster_http_error(
                    message="Provider connection failed.",
                    url=safe_upstream,
                    context=context,
                    category="connection_failure",
                    failure_phase=failure_phase,
                    status_code=response.status_code,
                    content_type=content_type,
                    content_length=content_length,
                ) from exc
            except httpx.TimeoutException as exc:
                raise _raster_http_error(
                    message="Provider request timed out.",
                    url=safe_upstream,
                    context=context,
                    category="timeout",
                    failure_phase=failure_phase,
                    status_code=response.status_code,
                    content_type=content_type,
                    content_length=content_length,
                ) from exc
            except httpx.HTTPError as exc:
                raise _raster_http_error(
                    message="Provider response body could not be read.",
                    url=safe_upstream,
                    context=context,
                    category="body_read_failure",
                    failure_phase=failure_phase,
                    status_code=response.status_code,
                    content_type=content_type,
                    content_length=content_length,
                ) from exc
            except Exception as exc:  # pragma: no cover - defensive transport boundary
                raise _raster_http_error(
                    message="Provider response body could not be read.",
                    url=safe_upstream,
                    context=context,
                    category="body_read_failure",
                    failure_phase=failure_phase,
                    status_code=response.status_code,
                    content_type=content_type,
                    content_length=content_length,
                ) from exc

            body = b"".join(chunks)
            actual_length = content_length if content_length is not None else len(body)
            if not body:
                raise _raster_http_error(
                    message="Provider returned an empty tile body.",
                    url=safe_upstream,
                    context=context,
                    category="empty_body",
                    failure_phase="validation",
                    status_code=response.status_code,
                    content_type=content_type,
                    content_length=actual_length,
                )
            if not _looks_like_image(body):
                raise _raster_http_error(
                    message="Provider returned a non-image tile body.",
                    url=safe_upstream,
                    context=context,
                    category="non_image_body",
                    failure_phase="validation",
                    status_code=response.status_code,
                    content_type=content_type,
                    content_length=actual_length,
                )
            return body
    except RasterHttpError:
        raise
    except httpx.ConnectTimeout as exc:
        raise _raster_http_error(
            message="Provider request timed out.",
            url=safe_upstream,
            context=context,
            category="connect_timeout",
            failure_phase=failure_phase,
            content_type=content_type,
            content_length=content_length,
        ) from exc
    except httpx.ReadTimeout as exc:
        raise _raster_http_error(
            message="Provider response timed out.",
            url=safe_upstream,
            context=context,
            category="read_timeout",
            failure_phase=failure_phase,
            content_type=content_type,
            content_length=content_length,
        ) from exc
    except httpx.ProxyError as exc:
        raise _raster_http_error(
            message="Provider proxy request failed.",
            url=safe_upstream,
            context=context,
            category="proxy_failure",
            failure_phase=failure_phase,
            content_type=content_type,
            content_length=content_length,
        ) from exc
    except (httpx.RemoteProtocolError, httpx.ReadError) as exc:
        raise _raster_http_error(
            message="Provider connection was interrupted.",
            url=safe_upstream,
            context=context,
            category="remote_protocol_failure",
            failure_phase=failure_phase,
            content_type=content_type,
            content_length=content_length,
        ) from exc
    except httpx.ConnectError as exc:
        raise _raster_http_error(
            message="Provider connection failed.",
            url=safe_upstream,
            context=context,
            category="connection_failure",
            failure_phase=failure_phase,
            content_type=content_type,
            content_length=content_length,
        ) from exc
    except httpx.TimeoutException as exc:
        raise _raster_http_error(
            message="Provider request timed out.",
            url=safe_upstream,
            context=context,
            category="timeout",
            failure_phase=failure_phase,
            content_type=content_type,
            content_length=content_length,
        ) from exc
    except httpx.HTTPError as exc:
        raise _raster_http_error(
            message="Provider request failed.",
            url=safe_upstream,
            context=context,
            category="transport_error",
            failure_phase=failure_phase,
            content_type=content_type,
            content_length=content_length,
        ) from exc


def _raster_http_error(
    *,
    message: str,
    url: str,
    context: _RasterDiagnosticContext | None,
    category: str,
    failure_phase: str,
    status_code: int | None = None,
    content_type: str | None = None,
    content_length: int | None = None,
) -> RasterHttpError:
    return RasterHttpError(
        message,
        RasterHttpDiagnostic(
            category=category,
            failure_phase=failure_phase,
            upstream=url,
            status_code=status_code,
            content_type=content_type,
            content_length=content_length,
            provider_id=context.provider_id if context else None,
            capability_id=context.capability_id if context else None,
        ),
    )


def _status_category(status_code: int) -> str:
    if 300 <= status_code < 400:
        return "unexpected_redirect"
    if status_code in {401, 403}:
        return "authentication_rejected"
    if status_code == 429:
        return "rate_limited"
    if status_code in {400, 404, 409, 410, 422}:
        return "invalid_request"
    if 400 <= status_code < 500:
        return "upstream_http_4xx"
    if 500 <= status_code < 600:
        return "upstream_http_5xx"
    return "transport_error"


def _content_length(value: str | None) -> int | None:
    if value is None:
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return max(0, parsed)


def _safe_content_type(value: str | None) -> str | None:
    if not value:
        return None
    return value.split(";", 1)[0].strip().lower()[:128] or None


def _safe_upstream_url(url: str) -> str:
    parsed = urlsplit(url)
    host = parsed.hostname or ""
    if parsed.port is not None:
        host = f"{host}:{parsed.port}"
    return f"{parsed.scheme.lower()}://{host}{parsed.path or '/'}"


def _looks_like_image(body: bytes) -> bool:
    return body.startswith(
        (
            b"\x89PNG\r\n\x1a\n",
            b"\xff\xd8\xff",
            b"RIFF",
        )
    )

###############################################################################
def _raise_for_status(response: httpx.Response) -> None:
    status_code = response.status_code
    if 300 <= status_code < 400:
        raise ProviderUnavailableError("Provider returned an unexpected redirect.")
    if 200 <= status_code < 300:
        return
    if status_code in {401, 403}:
        raise ProviderAuthError("Provider rejected the configured credential.")
    if status_code == 429:
        raise ProviderRateLimitError(
            "Provider rate limit exceeded.",
            retry_after_seconds=_retry_after_seconds(response.headers),
        )
    if status_code in {400, 404, 409, 410, 422}:
        raise ProviderInvalidQueryError("Provider rejected the requested query.")
    raise ProviderUnavailableError(f"Provider HTTP error {status_code}.")

###############################################################################
def _valid_content_length(value: str) -> int:
    try:
        parsed = int(value)
    except ValueError:
        return 0
    return max(0, parsed)

###############################################################################
def _retry_after_seconds(headers: httpx.Headers) -> float | None:
    raw = headers.get("retry-after")
    if not raw:
        return None
    try:
        return max(0.0, float(raw))
    except ValueError:
        pass
    try:
        retry_at = parsedate_to_datetime(raw)
        if retry_at.tzinfo is None:
            retry_at = retry_at.replace(tzinfo=UTC)
        return max(0.0, (retry_at.astimezone(UTC) - datetime.now(UTC)).total_seconds())
    except (TypeError, ValueError, OverflowError):
        return None

###############################################################################
async def fetch_text_url(url: str, headers: dict[str, str] | None = None) -> str:
    body = await fetch_bytes_url(url, headers)
    return body.decode("utf-8", errors="replace")

###############################################################################
async def call_json_fetcher(
    fetcher: JsonFetcher, url: str, headers: dict[str, str] | None = None
) -> Any:
    value = fetcher(url, headers)
    if inspect.isawaitable(value):
        return await value
    return value

###############################################################################
async def call_text_fetcher(
    fetcher: TextFetcher, url: str, headers: dict[str, str] | None = None
) -> str:
    value = fetcher(url, headers)
    if inspect.isawaitable(value):
        return await value
    return value

###############################################################################
async def call_bytes_fetcher(
    fetcher: BytesFetcher, url: str, headers: dict[str, str] | None = None
) -> bytes:
    value = fetcher(url, headers)
    if inspect.isawaitable(value):
        return await value
    return value

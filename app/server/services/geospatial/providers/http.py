from __future__ import annotations

import json
import inspect
from email.utils import parsedate_to_datetime
from datetime import UTC, datetime
from collections.abc import Awaitable, Callable
from typing import Any

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

_DEFAULT_TIMEOUT = httpx.Timeout(20.0)
DEFAULT_MAX_RESPONSE_BYTES = 16 * 1024 * 1024
_ASYNC_HTTP_CLIENT = httpx.AsyncClient(
    timeout=_DEFAULT_TIMEOUT,
    follow_redirects=False,
)


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
        async with _ASYNC_HTTP_CLIENT.stream(
            "GET", url, headers=headers or {}
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
    except TypeError, ValueError, OverflowError:
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

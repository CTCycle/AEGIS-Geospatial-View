from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from typing import Any

import httpx

from server.services.geospatial.providers.base import (
    ProviderAuthError,
    ProviderRateLimitError,
    ProviderTimeoutError,
    ProviderUnavailableError,
)

JsonFetcher = Callable[[str, dict[str, str] | None], Awaitable[Any] | Any]
BytesFetcher = Callable[[str, dict[str, str] | None], Awaitable[bytes] | bytes]

_DEFAULT_TIMEOUT = httpx.Timeout(20.0)
_ASYNC_HTTP_CLIENT = httpx.AsyncClient(
    timeout=_DEFAULT_TIMEOUT,
    follow_redirects=True,
)


###############################################################################
async def fetch_json_url(url: str, headers: dict[str, str] | None = None) -> Any:
    body = await fetch_bytes_url(url, headers)
    try:
        return json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ProviderUnavailableError("Provider returned malformed JSON.") from exc


###############################################################################
async def fetch_bytes_url(url: str, headers: dict[str, str] | None = None) -> bytes:
    try:
        response = await _ASYNC_HTTP_CLIENT.get(url, headers=headers or {})
        response.raise_for_status()
        return response.content
    except httpx.HTTPStatusError as exc:
        status_code = exc.response.status_code
        if status_code in {401, 403}:
            raise ProviderAuthError("Provider rejected the configured credential.") from exc
        if status_code == 429:
            raise ProviderRateLimitError("Provider rate limit exceeded.") from exc
        raise ProviderUnavailableError(f"Provider HTTP error {status_code}.") from exc
    except httpx.TimeoutException as exc:
        raise ProviderTimeoutError("Provider request timed out.") from exc
    except httpx.HTTPError as exc:
        raise ProviderUnavailableError(f"Provider unavailable: {exc}") from exc


###############################################################################
async def call_json_fetcher(
    fetcher: JsonFetcher, url: str, headers: dict[str, str] | None = None
) -> Any:
    value = fetcher(url, headers)
    if hasattr(value, "__await__"):
        return await value
    return value


###############################################################################
async def call_bytes_fetcher(
    fetcher: BytesFetcher, url: str, headers: dict[str, str] | None = None
) -> bytes:
    value = fetcher(url, headers)
    if hasattr(value, "__await__"):
        return await value
    return value

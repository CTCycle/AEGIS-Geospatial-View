from __future__ import annotations

import asyncio
import json
import socket
import urllib.error
import urllib.request
from collections.abc import Awaitable, Callable
from typing import Any

from server.services.geospatial.providers.base import (
    ProviderAuthError,
    ProviderRateLimitError,
    ProviderTimeoutError,
    ProviderUnavailableError,
)

JsonFetcher = Callable[[str, dict[str, str] | None], Awaitable[Any] | Any]


async def fetch_json_url(url: str, headers: dict[str, str] | None = None) -> Any:
    return await asyncio.to_thread(_fetch_json_url_sync, url, headers or {})


async def call_json_fetcher(
    fetcher: JsonFetcher, url: str, headers: dict[str, str] | None = None
) -> Any:
    value = fetcher(url, headers)
    if hasattr(value, "__await__"):
        return await value
    return value


def _fetch_json_url_sync(url: str, headers: dict[str, str]) -> Any:
    request = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            body = response.read()
    except urllib.error.HTTPError as exc:
        if exc.code in {401, 403}:
            raise ProviderAuthError("Provider rejected the configured credential.") from exc
        if exc.code == 429:
            raise ProviderRateLimitError("Provider rate limit exceeded.") from exc
        raise ProviderUnavailableError(f"Provider HTTP error {exc.code}.") from exc
    except (TimeoutError, socket.timeout) as exc:
        raise ProviderTimeoutError("Provider request timed out.") from exc
    except urllib.error.URLError as exc:
        reason = exc.reason
        if isinstance(reason, TimeoutError | socket.timeout):
            raise ProviderTimeoutError("Provider request timed out.") from exc
        raise ProviderUnavailableError(f"Provider unavailable: {reason}") from exc
    try:
        return json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ProviderUnavailableError("Provider returned malformed JSON.") from exc

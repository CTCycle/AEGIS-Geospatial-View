from __future__ import annotations

from server.common.typing import is_json_object, json_array, json_object

import asyncio
import math
import re
import threading
import time
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlsplit

from server.configurations.settings import JsonRainViewerSettings, RainViewerSettings
from server.services.geospatial.providers.base import ProviderUnavailableError
from server.services.geospatial.providers.http import (
    JsonFetcher,
    call_json_fetcher,
    fetch_json_url,
)

###############################################################################
class RainViewerServiceError(Exception):
    """Base exception for RainViewer failures."""

###############################################################################
class RainViewerRequestError(RainViewerServiceError):
    """Raised when RainViewer metadata cannot be fetched."""

###############################################################################
class RainViewerService:

    MAX_TILE_ZOOM = 7
    COLOR_SCHEME = 2
    _FRAME_PATH = re.compile(r"^/v2/radar/[A-Za-z0-9._~/-]+$")

    # -------------------------------------------------------------------------
    def __init__(
        self,
        *,
        settings: RainViewerSettings | None = None,
        metadata_url: str | None = None,
        user_agent: str | None = None,
        timeout_s: float | None = None,
        cache_ttl_s: float | None = None,
        min_call_interval_s: float | None = None,
        tile_color_scheme: int | None = None,
        tile_smooth: int | None = None,
        tile_snow: int | None = None,
        fetcher: JsonFetcher | None = None,
    ) -> None:
        configured = settings or RainViewerSettings(
            **JsonRainViewerSettings().model_dump()
        )
        self.metadata_url = metadata_url or configured.metadata_url
        self.user_agent = user_agent or configured.user_agent
        self.timeout_s = timeout_s if timeout_s is not None else configured.timeout
        self.cache_ttl_s = max(
            cache_ttl_s if cache_ttl_s is not None else configured.cache_ttl_s,
            30.0,
        )
        self.min_call_interval_s = max(
            min_call_interval_s
            if min_call_interval_s is not None
            else configured.min_call_interval_s,
            0.05,
        )
        # Universal Blue is the stable public palette for this capability.
        self.tile_color_scheme = self.COLOR_SCHEME
        self.tile_smooth = (
            tile_smooth if tile_smooth is not None else configured.tile_smooth
        )
        self.tile_snow = tile_snow if tile_snow is not None else configured.tile_snow
        self.fetcher = fetcher or fetch_json_url
        self._lock = threading.Lock()
        self._last_call = 0.0
        self._cache: tuple[float, dict[str, Any]] | None = None

    # -------------------------------------------------------------------------
    async def get_latest_radar_metadata(self) -> dict[str, Any]:
        payload = await self._fetch_metadata_payload()
        radar = json_object(payload.get("radar"))
        past_frames = self._validated_past_frames(radar.get("past"))
        if not past_frames:
            raise RainViewerRequestError("RainViewer did not return recent radar history frames.")

        latest, latest_time = max(past_frames, key=lambda item: item[1])
        host = self._validated_host(payload.get("host"))
        latest_path = self._validated_frame_path(latest.get("path"))
        if latest_path is None:
            raise RainViewerRequestError("RainViewer radar frame path is invalid.")

        frame_times = sorted(timestamp for _, timestamp in past_frames)
        tile_url_template = (
            f"{host}{latest_path}/256/{{z}}/{{x}}/{{y}}/"
            f"{self.tile_color_scheme}/{self.tile_smooth}_{self.tile_snow}.png"
        )
        return {
            "provider": "rainviewer",
            "kind": "recent_precipitation_radar",
            "latest_time": latest_time,
            "history_start_time": frame_times[0] if frame_times else None,
            "history_end_time": frame_times[-1] if frame_times else latest_time,
            "tile_url_template": tile_url_template,
            "frame_count": len(past_frames),
            "max_zoom": self.MAX_TILE_ZOOM,
            "host": host,
            "resolved_at": datetime.now(UTC).isoformat(),
            "attribution": "© RainViewer",
        }

    # -------------------------------------------------------------------------
    @classmethod
    def _validated_past_frames(
        cls, value: object
    ) -> list[tuple[dict[str, Any], int]]:
        validated: list[tuple[dict[str, Any], int]] = []
        for raw_frame in json_array(value):
            if not is_json_object(raw_frame):
                continue
            timestamp = cls._frame_timestamp(raw_frame.get("time"))
            path = cls._validated_frame_path(raw_frame.get("path"))
            if timestamp is not None and path is not None:
                validated.append((dict(raw_frame, path=path), timestamp))
        return validated

    # -------------------------------------------------------------------------
    @staticmethod
    def _validated_host(value: object) -> str:
        if not isinstance(value, str) or not value.strip():
            raise RainViewerRequestError("RainViewer metadata host is missing.")
        try:
            parsed = urlsplit(value.strip())
            port = parsed.port
        except ValueError as exc:
            raise RainViewerRequestError("RainViewer metadata host is invalid.") from exc
        hostname = (parsed.hostname or "").lower()
        if (
            parsed.scheme.lower() != "https"
            or parsed.username is not None
            or parsed.password is not None
            or port is not None
            or parsed.path not in {"", "/"}
            or parsed.query
            or parsed.fragment
            or not (
                hostname == "rainviewer.com"
                or hostname.endswith(".rainviewer.com")
            )
        ):
            raise RainViewerRequestError("RainViewer metadata host is not trusted.")
        return f"https://{hostname}"

    # -------------------------------------------------------------------------
    @classmethod
    def _validated_frame_path(cls, value: object) -> str | None:
        if not isinstance(value, str) or not value.strip():
            return None
        raw_path = value.strip()
        try:
            parsed = urlsplit(raw_path)
        except ValueError:
            return None
        path = parsed.path.rstrip("/")
        if (
            parsed.scheme
            or parsed.netloc
            or parsed.query
            or parsed.fragment
            or "\\" in raw_path
            or "//" in path
            or any(part in {"", ".", ".."} for part in path.split("/")[1:])
            or cls._FRAME_PATH.fullmatch(path) is None
        ):
            return None
        return path

    # -------------------------------------------------------------------------
    @staticmethod
    def _frame_timestamp(value: object) -> int | None:
        if isinstance(value, bool):
            return None
        if isinstance(value, int):
            timestamp = value
        elif isinstance(value, float) and math.isfinite(value) and value.is_integer():
            timestamp = int(value)
        elif isinstance(value, str):
            try:
                timestamp = int(value.strip())
            except ValueError:
                return None
        else:
            return None
        return timestamp if timestamp > 0 else None

    # -------------------------------------------------------------------------
    async def _fetch_metadata_payload(self) -> dict[str, Any]:
        cached = self._cache_get()
        if cached is not None:
            return cached
        await self._wait_for_rate_limit_slot()
        try:
            data = await call_json_fetcher(
                self.fetcher,
                self.metadata_url,
                {"User-Agent": self.user_agent},
            )
        except ProviderUnavailableError as exc:
            raise RainViewerRequestError(f"RainViewer request failed: {exc}") from exc
        if not is_json_object(data):
            raise RainViewerRequestError("RainViewer response payload is malformed.")
        self._cache_set(data)
        return data

    # -------------------------------------------------------------------------
    def _cache_get(self) -> dict[str, Any] | None:
        with self._lock:
            if self._cache is None:
                return None
            ts, payload = self._cache
            if time.time() - ts > self.cache_ttl_s:
                self._cache = None
                return None
            return dict(payload)

    # -------------------------------------------------------------------------
    def _cache_set(self, payload: dict[str, Any]) -> None:
        with self._lock:
            self._cache = (time.time(), payload)

    # -------------------------------------------------------------------------
    async def _wait_for_rate_limit_slot(self) -> None:
        with self._lock:
            now = time.time()
            delay = self.min_call_interval_s - (now - self._last_call)
        if delay > 0:
            await asyncio.sleep(delay)
        with self._lock:
            self._last_call = time.time()

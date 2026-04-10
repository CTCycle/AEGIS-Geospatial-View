from __future__ import annotations

import asyncio
import json
import threading
import time
from datetime import UTC, datetime
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from AEGIS.server.configurations import server_settings


class RainViewerServiceError(Exception):
    """Base exception for RainViewer failures."""


class RainViewerRequestError(RainViewerServiceError):
    """Raised when RainViewer metadata cannot be fetched."""


class RainViewerService:
    def __init__(
        self,
        *,
        metadata_url: str | None = None,
        user_agent: str | None = None,
        timeout_s: float | None = None,
        cache_ttl_s: float | None = None,
        min_call_interval_s: float | None = None,
        tile_color_scheme: int | None = None,
        tile_smooth: int | None = None,
        tile_snow: int | None = None,
    ) -> None:
        settings = server_settings.rainviewer
        self.metadata_url = metadata_url or settings.metadata_url
        self.user_agent = user_agent or settings.user_agent
        self.timeout_s = timeout_s if timeout_s is not None else settings.timeout
        self.cache_ttl_s = max(cache_ttl_s if cache_ttl_s is not None else settings.cache_ttl_s, 30.0)
        self.min_call_interval_s = max(
            min_call_interval_s if min_call_interval_s is not None else settings.min_call_interval_s,
            0.05,
        )
        self.tile_color_scheme = tile_color_scheme if tile_color_scheme is not None else settings.tile_color_scheme
        self.tile_smooth = tile_smooth if tile_smooth is not None else settings.tile_smooth
        self.tile_snow = tile_snow if tile_snow is not None else settings.tile_snow
        self._lock = threading.Lock()
        self._last_call = 0.0
        self._cache: tuple[float, dict[str, Any]] | None = None

    async def get_latest_radar_metadata(self) -> dict[str, Any]:
        payload = await asyncio.to_thread(self._fetch_metadata_payload)
        radar = payload.get("radar") if isinstance(payload.get("radar"), dict) else {}
        past = radar.get("past") if isinstance(radar.get("past"), list) else []
        nowcast = radar.get("nowcast") if isinstance(radar.get("nowcast"), list) else []
        frames = [frame for frame in [*past, *nowcast] if isinstance(frame, dict)]
        if not frames:
            raise RainViewerRequestError("RainViewer did not return radar frames.")
        latest = max(frames, key=lambda frame: int(frame.get("time") or 0))
        latest_time = int(latest.get("time") or 0)
        latest_path = str(latest.get("path") or "").strip()
        if not latest_path:
            raise RainViewerRequestError("RainViewer radar frame path is missing.")
        tile_url_template = (
            f"https://tilecache.rainviewer.com{latest_path}/256/{{z}}/{{x}}/{{y}}/"
            f"{self.tile_color_scheme}/{self.tile_smooth}_{self.tile_snow}.png"
        )
        return {
            "provider": "rainviewer",
            "kind": "precipitation_radar",
            "latest_time": latest_time,
            "tile_url_template": tile_url_template,
            "frame_count": len(frames),
            "host": payload.get("host"),
            "resolved_at": datetime.now(UTC).isoformat(),
            "attribution": "© RainViewer",
        }

    def _fetch_metadata_payload(self) -> dict[str, Any]:
        cached = self._cache_get()
        if cached is not None:
            return cached
        self._wait_for_rate_limit_slot()
        request = Request(self.metadata_url, headers={"User-Agent": self.user_agent})
        try:
            with urlopen(request, timeout=self.timeout_s) as response:
                payload = response.read().decode("utf-8")
        except (HTTPError, URLError, TimeoutError) as exc:
            raise RainViewerRequestError(f"RainViewer request failed: {exc}") from exc
        try:
            data = json.loads(payload)
        except json.JSONDecodeError as exc:
            raise RainViewerRequestError("RainViewer response was not valid JSON.") from exc
        if not isinstance(data, dict):
            raise RainViewerRequestError("RainViewer response payload is malformed.")
        self._cache_set(data)
        return data

    def _cache_get(self) -> dict[str, Any] | None:
        with self._lock:
            if self._cache is None:
                return None
            ts, payload = self._cache
            if time.time() - ts > self.cache_ttl_s:
                self._cache = None
                return None
            return dict(payload)

    def _cache_set(self, payload: dict[str, Any]) -> None:
        with self._lock:
            self._cache = (time.time(), payload)

    def _wait_for_rate_limit_slot(self) -> None:
        with self._lock:
            now = time.time()
            delay = self.min_call_interval_s - (now - self._last_call)
        if delay > 0:
            time.sleep(delay)
        with self._lock:
            self._last_call = time.time()

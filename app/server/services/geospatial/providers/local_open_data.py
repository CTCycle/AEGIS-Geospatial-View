from __future__ import annotations

from server.common.typing import is_json_array, is_json_object, json_array

import json
import os
import ipaddress
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from server.services.geospatial.providers.base import (
    ProviderMalformedPayloadError,
    ProviderInvalidQueryError,
    ProviderRequest,
    ProviderResponse,
    ProviderUnavailableError,
)
from server.services.geospatial.providers.http import (
    JsonFetcher,
    call_json_fetcher,
    fetch_json_url,
)

###############################################################################
class LocalOpenDataProvider:
    provider_id = "local_open_data"

    # -------------------------------------------------------------------------
    def __init__(
        self,
        *,
        source_map: dict[str, str] | None = None,
        fetcher: JsonFetcher | None = None,
        allowed_hosts: set[str] | None = None,
    ) -> None:
        self.source_map = (
            dict(source_map)
            if source_map is not None
            else self._source_map_from_env()
        )
        self.fetcher = fetcher or fetch_json_url
        self.allowed_hosts = self._allowed_hosts(allowed_hosts)

    # -------------------------------------------------------------------------
    async def fetch(self, request: ProviderRequest) -> ProviderResponse:
        source_id = self._requested_source_id(request)
        source = self.source_map.get(source_id, "").strip()
        if source:
            payload = await self._load_source(source, source_id=source_id)
        else:
            payload = {
                "renderingMode": "metadata-only",
                "status": "configuration-needed",
                "message": (
                    "Configure a trusted local open-data source for this "
                    "capability before rendering live agency data."
                ),
            }
        return ProviderResponse(
            capability_id=request.capability_id,
            provider_id=self.provider_id,
            payload=payload,
            attribution=["Local open data provider"],
            result_type="features" if payload.get("features") else "metadata",
            result_status="valid_empty"
            if payload.get("features") == []
            else "ok",
        )

    # -------------------------------------------------------------------------
    async def fetch_features(self, request: ProviderRequest) -> ProviderResponse:
        return await self.fetch(request)

    # -------------------------------------------------------------------------
    async def _load_source(self, source: str, *, source_id: str) -> dict[str, Any]:
        parsed = urlsplit(source)
        if parsed.scheme in {"http", "https"} or parsed.netloc:
            self._validate_remote_source(parsed, source_id=source_id)
            payload = await call_json_fetcher(self.fetcher, source, None)
        else:
            try:
                path = Path(source).expanduser()
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, UnicodeError, json.JSONDecodeError) as exc:
                raise ProviderUnavailableError(
                    "Configured local open-data source is unavailable or malformed."
                ) from exc
        return self._normalize_payload(payload, source_id=source_id)

    # -------------------------------------------------------------------------
    def _normalize_payload(self, payload: object, *, source_id: str) -> dict[str, Any]:
        if not is_json_object(payload):
            raise ProviderMalformedPayloadError("Local open-data source must be a JSON object.")
        if payload.get("type") == "FeatureCollection":
            features = payload.get("features")
            if not is_json_array(features):
                raise ProviderMalformedPayloadError(
                    "Local open-data FeatureCollection is missing features."
                )
            return {
                "renderingMode": (
                    "camera-points" if self._is_camera_source(source_id) else "geojson"
                ),
                "type": "FeatureCollection",
                "features": json_array(features),
                "sourceId": source_id,
            }
        cameras = payload.get("cameras")
        if is_json_array(cameras):
            return {
                "renderingMode": "camera-points",
                "type": "FeatureCollection",
                "features": [self._camera_feature(item) for item in cameras if is_json_object(item)],
                "sourceId": source_id,
            }
        return payload | {"sourceId": source_id}

    # -------------------------------------------------------------------------
    def _camera_feature(self, item: dict[str, Any]) -> dict[str, Any]:
        longitude = item.get("longitude") or item.get("lon")
        latitude = item.get("latitude") or item.get("lat")
        return {
            "type": "Feature",
            "id": item.get("id") or item.get("camera_id") or item.get("name"),
            "geometry": {"type": "Point", "coordinates": [longitude, latitude]},
            "properties": item,
        }

    # -------------------------------------------------------------------------
    def _source_map_from_env(self) -> dict[str, str]:
        raw = os.getenv("LOCAL_OPEN_DATA_SOURCES", "").strip()
        if not raw:
            return {}
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            return {}
        if not is_json_object(payload):
            return {}
        return {str(key): str(value) for key, value in payload.items() if value}

    # -------------------------------------------------------------------------
    def _requested_source_id(self, request: ProviderRequest) -> str:
        requested = request.params.get("source_id")
        if requested is None:
            for field in ("source", "source_url"):
                if field in request.params:
                    requested = request.params[field]
                    break
        source_id = str(requested or request.capability_id).strip()
        if not source_id:
            raise ProviderInvalidQueryError("A configured local open-data source id is required.")
        if source_id not in self.source_map:
            raise ProviderInvalidQueryError(
                "Local open-data sources must be selected by a configured source id."
            )
        return source_id

    # -------------------------------------------------------------------------
    def _allowed_hosts(self, allowed_hosts: set[str] | None) -> set[str]:
        if allowed_hosts is not None:
            return {str(host).strip().lower().rstrip(".") for host in allowed_hosts if host.strip()}
        configured = os.getenv("LOCAL_OPEN_DATA_ALLOWED_HOSTS", "")
        explicit = {item.strip().lower().rstrip(".") for item in configured.split(",") if item.strip()}
        if explicit:
            return explicit
        hosts: set[str] = set()
        for source in self.source_map.values():
            parsed = urlsplit(source)
            if parsed.scheme == "https" and parsed.hostname:
                hosts.add(parsed.hostname.lower().rstrip("."))
        return hosts

    # -------------------------------------------------------------------------
    def _validate_remote_source(self, parsed: Any, *, source_id: str) -> None:
        if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
            raise ProviderInvalidQueryError(
                f"Configured local source '{source_id}' must use an HTTPS URL without embedded credentials."
            )
        host = parsed.hostname.lower().rstrip(".")
        if host not in self.allowed_hosts or _is_private_host(host):
            raise ProviderInvalidQueryError(
                f"Configured local source '{source_id}' is not on the trusted host allowlist."
            )

    # -------------------------------------------------------------------------
    @staticmethod
    def _is_camera_source(source_id: str) -> bool:
        normalized = source_id.casefold()
        return "camera" in normalized or "webcam" in normalized

###############################################################################
def _is_private_host(host: str) -> bool:
    if host in {"localhost", "localhost.localdomain"}:
        return True
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return False
    return bool(
        address.is_private
        or address.is_loopback
        or address.is_link_local
        or address.is_multicast
        or address.is_reserved
    )

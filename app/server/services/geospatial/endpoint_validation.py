from __future__ import annotations

import json
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from server.domain.geospatial.validation import EndpointValidationResult


###############################################################################
class EndpointValidationService:
    """Performs sampled, read-only health checks for manifest endpoints."""

    def __init__(self, *, timeout_seconds: float = 5.0, max_bytes: int = 1_000_000) -> None:
        self.timeout_seconds = timeout_seconds
        self.max_bytes = max_bytes

    def build_validation_url(
        self, manifest: dict[str, Any], *, sample_bbox: str = "12.45,41.88,12.52,41.92"
    ) -> str | None:
        metadata = dict(manifest.get("metadata") or {})
        raw_url = (
            metadata.get("url")
            or metadata.get("url_template")
            or metadata.get("tile_url")
            or metadata.get("tile_url_template")
        )
        if not isinstance(raw_url, str) or not raw_url.strip():
            return None
        url = raw_url.strip().replace("{bbox}", sample_bbox)
        url = url.replace("{lat}", "41.9028").replace("{lon}", "12.4964")
        if "{api_key}" in url:
            return None
        manifest_type = str(manifest.get("type") or "").lower()
        if manifest_type in {"wms", "wmts"} and "request=" not in url.lower():
            query = urlencode(
                {
                    "service": manifest_type.upper(),
                    "request": "GetCapabilities",
                }
            )
            separator = "&" if "?" in url else "?"
            url = f"{url}{separator}{query}"
        return url

    def validate_manifest(
        self, manifest: dict[str, Any], *, sample_bbox: str = "12.45,41.88,12.52,41.92"
    ) -> EndpointValidationResult:
        capability_id = str(manifest.get("id") or "unknown")
        data_format = str(dict(manifest.get("metadata") or {}).get("data_format") or "")
        url = self.build_validation_url(manifest, sample_bbox=sample_bbox)
        if url is None:
            return EndpointValidationResult(
                capability_id=capability_id,
                ok=False,
                status_code=None,
                data_format=data_format,
                message="No public sampled endpoint is available for this manifest.",
            )
        try:
            request = Request(url, headers={"User-Agent": "AEGIS-EndpointValidation/1.0"})
            with urlopen(request, timeout=self.timeout_seconds) as response:  # noqa: S310
                status = getattr(response, "status", None)
                read_limit = self.max_bytes if "json" in data_format.lower() else 2048
                body = response.read(read_limit + 1)
        except Exception as exc:
            return EndpointValidationResult(
                capability_id=capability_id,
                ok=False,
                status_code=None,
                data_format=data_format,
                message=str(exc),
            )
        if not body:
            return EndpointValidationResult(
                capability_id=capability_id,
                ok=False,
                status_code=status,
                data_format=data_format,
                message="Endpoint returned an empty response.",
            )
        if "json" in data_format.lower() and len(body) > self.max_bytes:
            return EndpointValidationResult(
                capability_id=capability_id,
                ok=False,
                status_code=status,
                data_format=data_format,
                message=f"Endpoint response exceeded validation limit of {self.max_bytes} bytes.",
            )
        if "json" in data_format.lower():
            try:
                json.loads(body.decode("utf-8"))
            except Exception as exc:
                return EndpointValidationResult(
                    capability_id=capability_id,
                    ok=False,
                    status_code=status,
                    data_format=data_format,
                    message=f"Endpoint did not return parseable JSON: {exc}",
                )
        return EndpointValidationResult(
            capability_id=capability_id,
            ok=bool(status is None or 200 <= int(status) < 400),
            status_code=status,
            data_format=data_format,
            message="Endpoint returned a sampled response.",
        )

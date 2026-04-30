from __future__ import annotations

import asyncio
import json
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from server.common.logger import logger

PVGIS_BASE_URL = "https://re.jrc.ec.europa.eu/api/v5_3"


class PVGISError(Exception):
    """Exception for PVGIS API failures."""


class PVGISService:
    def __init__(
        self,
        *,
        user_agent: str | None = None,
        timeout_s: float = 20.0,
    ) -> None:
        self.user_agent = user_agent or "AEGIS-PVGIS/1.0"
        self.timeout_s = timeout_s

    # -------------------------------------------------------------------------
    async def get_point_estimate(
        self, latitude: float, longitude: float
    ) -> dict[str, Any]:
        return await asyncio.to_thread(
            self._fetch_point_estimate,
            latitude,
            longitude,
        )

    # -------------------------------------------------------------------------
    def _fetch_point_estimate(
        self, latitude: float, longitude: float
    ) -> dict[str, Any]:
        params = {
            "lat": f"{latitude:.6f}",
            "lon": f"{longitude:.6f}",
            "outputformat": "json",
            "loss": "14",
            "peakpower": "1",
        }
        url = f"{PVGIS_BASE_URL}/PVcalc?{urlencode(params)}"
        request = Request(url, headers={"User-Agent": self.user_agent})
        try:
            with urlopen(request, timeout=self.timeout_s) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as exc:
            logger.warning("PVGIS request failed: %s", exc)
            return {
                "provider": "pvgis",
                "latitude": latitude,
                "longitude": longitude,
                "error": "PVGIS data unavailable",
            }

        outputs = payload.get("outputs", {})
        monthly = outputs.get("monthly", {})
        fixed = monthly.get("fixed", [])
        yearly_kwh = None
        if isinstance(fixed, list) and fixed:
            yearly_kwh = 0.0
            for entry in fixed:
                try:
                    yearly_kwh += float(entry.get("E_m", 0.0) or 0.0)
                except (TypeError, ValueError):
                    continue
        return {
            "provider": "pvgis",
            "latitude": latitude,
            "longitude": longitude,
            "yearly_kwh_per_kwp_estimate": yearly_kwh,
            "raw": outputs,
            "attribution": "PVGIS (European Commission JRC)",
        }


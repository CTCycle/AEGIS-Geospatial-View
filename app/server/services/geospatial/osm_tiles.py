from __future__ import annotations

from urllib.error import HTTPError, URLError
from urllib.request import Request as UrlRequest
from urllib.request import urlopen

###############################################################################
class OsmTileProxyError(RuntimeError):
    """Raised when OSM tile proxy retrieval fails."""

###############################################################################
class OsmTileProxyService:

    # -------------------------------------------------------------------------
    def fetch_tile(self, z: int, x: int, y: int) -> tuple[bytes, str, str]:
        tile_url = f"https://tile.openstreetmap.org/{z}/{x}/{y}.png"
        request = UrlRequest(
            tile_url,
            headers={
                "User-Agent": "AEGIS Geospatial View/2.0 (+https://github.com/CTCycle/AEGIS-geographics)",
                "Accept": "image/avif,image/webp,image/apng,image/*,*/*;q=0.8",
            },
        )
        try:
            with urlopen(request, timeout=10) as upstream:
                media_type = upstream.headers.get_content_type() or "image/png"
                cache_control = upstream.headers.get(
                    "Cache-Control", "public, max-age=3600"
                )
                return upstream.read(), media_type, cache_control
        except HTTPError as exc:
            raise OsmTileProxyError(
                f"OSM basemap tile request failed with status {exc.code}."
            ) from exc
        except URLError as exc:
            raise OsmTileProxyError("OSM basemap tile provider is unavailable.") from exc

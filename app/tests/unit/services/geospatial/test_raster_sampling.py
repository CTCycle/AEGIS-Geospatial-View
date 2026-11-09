from __future__ import annotations

from io import BytesIO
from types import SimpleNamespace
from typing import Any, cast

from fastapi import FastAPI
from fastapi.testclient import TestClient
from PIL import Image
import pytest

from server.api import geospatial
from server.domain.geospatial.registry import GeospatialManifestSnapshot
from server.services.geospatial.api_service import GeospatialApiService
from server.services.geospatial.raster_sampling import (
    TilePixel,
    compile_legend,
    lonlat_to_tile_pixel,
    sample_tile,
    summarize_legend,
)

LEGEND: dict[str, Any] = {
    "kind": "continuous",
    "title": "Precipitation rate",
    "units": "mm/h",
    "entries": [
        {"color": "#0000ff", "value": 1.0, "label": "1"},
        {"color": "#00ff00", "value": 5.0, "label": "5"},
        {"color": "#ff0000", "value": 20.0, "label": "20"},
    ],
    "nodata_colors": ["#808080"],
}
PIXEL = TilePixel(z=1, x=0, y=0, pixel_x=10, pixel_y=10, tile_size=256)

###############################################################################
def _png(color: tuple[int, int, int, int], size: int = 256) -> bytes:
    buffer = BytesIO()
    Image.new("RGBA", (size, size), color).save(buffer, format="PNG")
    return buffer.getvalue()

###############################################################################
def _legend():  # noqa: ANN202
    compiled = compile_legend(LEGEND)
    assert compiled is not None
    return compiled

###############################################################################
def test_lonlat_maps_to_known_tile_and_pixel() -> None:
    assert lonlat_to_tile_pixel(0.0, 0.0, 1) == TilePixel(
        z=1, x=1, y=1, pixel_x=0, pixel_y=0, tile_size=256
    )
    # Rome at z8 lies in the published OSM tile 136/95.
    rome = lonlat_to_tile_pixel(12.4964, 41.9028, 8, tile_size=512)
    assert (rome.x, rome.y) == (136, 95)
    assert 0 <= rome.pixel_x < 512 and 0 <= rome.pixel_y < 512

###############################################################################
def test_sample_tile_reads_nearest_legend_entry_within_tolerance() -> None:
    sample = sample_tile(_png((10, 245, 5, 255)), PIXEL, _legend())

    assert sample == {
        "value": 5.0,
        "label": "5",
        "units": "mm/h",
        "kind": "continuous",
        "matched_color": "#00ff00",
    }

###############################################################################
@pytest.mark.parametrize(
    "color",
    [(255, 0, 0, 0), (128, 128, 128, 255), (255, 255, 0, 255)],
    ids=["transparent", "nodata", "out_of_tolerance"],
)
def test_sample_tile_returns_none_without_a_legend_colour(
    color: tuple[int, int, int, int],
) -> None:
    assert sample_tile(_png(color), PIXEL, _legend()) is None

###############################################################################
def test_legend_summary_is_compact() -> None:
    assert summarize_legend(LEGEND) == {
        "title": "Precipitation rate",
        "units": "mm/h",
        "kind": "continuous",
        "min": 1.0,
        "max": 20.0,
    }
    categorical = {
        "kind": "categorical",
        "title": "Land cover",
        "units": None,
        "entries": [
            {"color": f"#0000{index:02x}", "label": f"class {index}"}
            for index in range(10)
        ],
    }
    summary = summarize_legend(categorical)
    assert summary is not None
    assert summary["labels"] == [f"class {index}" for index in range(8)]
    assert summary["label_count"] == 10

###############################################################################
def _client(overlay: dict[str, Any], tile: bytes) -> tuple[TestClient, list[tuple[int, ...]]]:
    service = GeospatialApiService(
        catalog_service=cast(Any, None),
        catalog_snapshot=GeospatialManifestSnapshot.from_payload({"overlays": [overlay]}),
        runtime_registry=cast(Any, SimpleNamespace(credential_resolver=None)),
        provider_registry=cast(Any, None),
    )
    fetched: list[tuple[int, ...]] = []

    async def fake_fetch(
        capability_id: str, z: int, x: int, y: int, time: str | None = None
    ) -> bytes:
        fetched.append((z, x, y))
        return tile

    service.fetch_capability_tile = fake_fetch  # type: ignore[method-assign]
    app = FastAPI()
    app.include_router(geospatial.router, prefix="/api")
    app.dependency_overrides[geospatial.get_geospatial_api_service] = lambda: service
    return TestClient(app), fetched

###############################################################################
def _overlay(**metadata: Any) -> dict[str, Any]:
    return {
        "id": "fixture_rain",
        "provider": "gibs",
        "renderingMode": "wms",
        "metadata": {"layer_id": "fixture_rain", "max_zoom": 6, **metadata},
    }

###############################################################################
def test_sample_endpoint_returns_legend_value_with_clamped_zoom_and_cached_tile() -> None:
    client, fetched = _client(_overlay(legend=LEGEND), _png((255, 0, 0, 255)))

    url = "/api/geospatial/sample/fixture_rain?lon=12.5&lat=41.9&z=12&time=2026-11-01"
    response = client.get(url)
    assert client.get(url).status_code == 200

    assert response.status_code == 200
    assert response.json() == {
        "capability_id": "fixture_rain",
        "lon": 12.5,
        "lat": 41.9,
        "z": 6,
        "time": "2026-11-01",
        "legend_title": "Precipitation rate",
        "units": "mm/h",
        "kind": "continuous",
        "sample": {
            "value": 20.0,
            "label": "20",
            "units": "mm/h",
            "kind": "continuous",
            "matched_color": "#ff0000",
        },
    }
    assert len(fetched) == 1 and fetched[0][0] == 6

###############################################################################
def test_sample_endpoint_rejects_layer_without_legend() -> None:
    client, fetched = _client(_overlay(), _png((255, 0, 0, 255)))

    response = client.get("/api/geospatial/sample/fixture_rain?lon=12.5&lat=41.9&z=5")

    assert response.status_code == 422
    assert "no colour legend" in response.json()["detail"]
    assert fetched == []

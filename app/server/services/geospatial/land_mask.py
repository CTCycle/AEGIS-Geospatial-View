from __future__ import annotations

import json
from functools import lru_cache
from typing import TypeAlias

from shapely import Geometry
from shapely.geometry import box, shape
from shapely.ops import unary_union
from shapely.prepared import PreparedGeometry, prep

from server.services.catalog.loader import get_catalog_root

MASK_SOURCE = "natural_earth_50m_admin0"
LandMask: TypeAlias = "PreparedGeometry[Geometry]"
COAST_BUFFER_DEG = 0.05

###############################################################################
@lru_cache(maxsize=1)
def country_shapes() -> dict[str, Geometry]:
    """Simplified Natural Earth admin-0 land polygons keyed by ISO alpha-2."""
    path = get_catalog_root() / "reference" / "country_shapes.geojson"
    payload = json.loads(path.read_text(encoding="utf-8"))
    shapes: dict[str, list[Geometry]] = {}
    for feature in payload["features"]:
        shapes.setdefault(feature["properties"]["iso2"], []).append(shape(feature["geometry"]))
    return {code: unary_union(parts) for code, parts in shapes.items()}

###############################################################################
@lru_cache(maxsize=64)
def land_mask(
    bbox: tuple[float, float, float, float],
    countries: tuple[str, ...] = (),
    buffer_deg: float = COAST_BUFFER_DEG,
) -> LandMask:
    """Land inside the bbox, restricted to member countries when given."""
    shapes = country_shapes()
    unknown = [code for code in countries if code not in shapes]
    if unknown:
        raise ValueError(f"Unknown country codes for land mask: {', '.join(unknown)}")
    members = [shapes[code] for code in countries] if countries else list(shapes.values())
    # The default buffer keeps coastal cells the simplified coastline cuts off;
    # callers widen it to keep offshore observations near the region.
    return prep(unary_union(members).intersection(box(*bbox)).buffer(buffer_deg))

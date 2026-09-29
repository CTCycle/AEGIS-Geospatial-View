from __future__ import annotations

from collections.abc import Mapping
import re
from typing import Any
from urllib.parse import quote, urlsplit, urlunsplit


WEB_MERCATOR_HALF_WORLD = 20037508.342789244
MAX_TILE_ZOOM = 30
_UNRESOLVED_PLACEHOLDER = re.compile(r"\{[^{}]+\}")

###############################################################################
class RasterTileTemplateError(ValueError):
    """Raised when a raster tile template cannot be safely materialized."""

###############################################################################
def validate_tile_coordinates(z: int, x: int, y: int) -> None:
    """Validate bounded XYZ coordinates before any provider request."""

    values = (z, x, y)
    if any(type(value) is not int for value in values):
        raise RasterTileTemplateError("Tile coordinates must be integers.")
    if z < 0 or z > MAX_TILE_ZOOM:
        raise RasterTileTemplateError(
            f"Tile zoom must be between 0 and {MAX_TILE_ZOOM}."
        )
    tile_count = 1 << z
    if not 0 <= x < tile_count or not 0 <= y < tile_count:
        raise RasterTileTemplateError("Tile coordinates are outside the zoom range.")

###############################################################################
def web_mercator_tile_bbox(
    z: int, x: int, y: int
) -> tuple[float, float, float, float]:
    """Return the exact EPSG:3857 envelope for one XYZ tile."""

    validate_tile_coordinates(z, x, y)
    tile_span = (WEB_MERCATOR_HALF_WORLD * 2.0) / float(1 << z)
    min_x = -WEB_MERCATOR_HALF_WORLD + (float(x) * tile_span)
    max_x = min_x + tile_span
    max_y = WEB_MERCATOR_HALF_WORLD - (float(y) * tile_span)
    min_y = max_y - tile_span
    return min_x, min_y, max_x, max_y

###############################################################################
def format_web_mercator_bbox(
    z: int, x: int, y: int
) -> str:
    """Format one XYZ tile envelope for a provider query parameter."""

    return ",".join(str(value) for value in web_mercator_tile_bbox(z, x, y))

###############################################################################
def ensure_no_unresolved_placeholders(url: str) -> str:
    """Reject any placeholder that would otherwise reach an upstream URL."""

    unresolved = _UNRESOLVED_PLACEHOLDER.findall(url)
    if unresolved:
        raise RasterTileTemplateError(
            f"Raster tile URL contains unresolved placeholders: {', '.join(unresolved)}."
        )
    return url

###############################################################################
def materialize_tile_template(
    template: str,
    z: int,
    x: int,
    y: int,
    *,
    replacements: Mapping[str, Any] | None = None,
) -> str:
    """Resolve supported tile placeholders and reject anything left over."""

    validate_tile_coordinates(z, x, y)
    if not template.strip():
        raise RasterTileTemplateError("Raster tile URL template is required.")

    values: dict[str, Any] = {
        "z": z,
        "x": x,
        "y": y,
        "bbox-epsg-3857": format_web_mercator_bbox(z, x, y),
    }
    if replacements:
        values.update(replacements)

    resolved = template
    for name, value in values.items():
        placeholder = "{" + str(name) + "}"
        if placeholder not in resolved:
            continue
        if name == "bbox-epsg-3857":
            replacement = str(value)
        elif name in {"z", "x", "y"}:
            replacement = str(value)
        else:
            replacement = quote(str(value), safe="-._~:/")
        resolved = resolved.replace(placeholder, replacement)
    return ensure_no_unresolved_placeholders(resolved)

###############################################################################
def build_wms_tile_template(
    *,
    url: str,
    layer_id: str,
    crs: str,
    image_format: str,
    style: str,
    time: str,
    version: str,
    exceptions: str,
) -> str:
    """Build a browser-facing WMS GetMap template."""

    crs_key = "crs" if version.startswith("1.3") else "srs"
    query = [
        ("service", "WMS"),
        ("request", "GetMap"),
        ("layers", layer_id),
        ("styles", style),
        ("format", image_format),
        ("transparent", "true"),
        ("version", version),
        (crs_key, crs),
        ("exceptions", exceptions),
        ("bbox", "{bbox-epsg-3857}"),
        ("width", "256"),
        ("height", "256"),
    ]
    if time:
        query.append(("time", time))
    return _append_query(url, query)

###############################################################################
def build_wmts_tile_template(
    *,
    url: str,
    layer_id: str,
    style: str,
    image_format: str,
    tile_matrix_set: str,
    time: str,
) -> str:
    """Build a browser-facing WMTS GetTile template."""

    query = [
        ("service", "WMTS"),
        ("request", "GetTile"),
        ("version", "1.0.0"),
        ("layer", layer_id),
        ("style", style),
        ("tilematrixset", tile_matrix_set),
        ("tilematrix", f"{tile_matrix_set}:{{z}}"),
        ("tilerow", "{y}"),
        ("tilecol", "{x}"),
        ("format", image_format),
    ]
    if time:
        query.append(("time", time))
    return _append_query(url, query)

###############################################################################
def build_wms_get_map_url(
    *,
    url: str,
    layer_id: str,
    crs: str,
    image_format: str,
    style: str,
    version: str,
    exceptions: str,
    z: int,
    x: int,
    y: int,
    time: str | None = None,
) -> str:
    """Build one bounded WMS GetMap request for an XYZ tile."""

    return materialize_tile_template(
        build_wms_tile_template(
            url=url,
            layer_id=layer_id,
            crs=crs,
            image_format=image_format,
            style=style,
            time=time or "",
            version=version,
            exceptions=exceptions,
        ),
        z,
        x,
        y,
    )

###############################################################################
def build_wmts_get_tile_url(
    *,
    url: str,
    layer_id: str,
    style: str,
    image_format: str,
    tile_matrix_set: str,
    z: int,
    x: int,
    y: int,
    time: str | None = None,
) -> str:
    """Build one bounded WMTS GetTile request for an XYZ tile."""

    return materialize_tile_template(
        build_wmts_tile_template(
            url=url,
            layer_id=layer_id,
            style=style,
            image_format=image_format,
            tile_matrix_set=tile_matrix_set,
            time=time or "",
        ),
        z,
        x,
        y,
    )

###############################################################################
def _append_query(url: str, query: list[tuple[str, str]]) -> str:
    parts = urlsplit(url)
    existing = parts.query
    rendered = "&".join(
        f"{_query_component(key)}={_query_component(value)}" for key, value in query
    )
    combined = "&".join(item for item in (existing, rendered) if item)
    return urlunsplit((parts.scheme, parts.netloc, parts.path, combined, parts.fragment))

###############################################################################
def _query_component(value: str) -> str:
    return quote(str(value), safe="-._~:/,{}")

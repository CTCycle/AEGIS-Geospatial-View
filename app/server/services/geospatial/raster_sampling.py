"""Read legend values from colour-mapped raster tiles at one coordinate.

Colour-mapped overlays only carry colours. A manifest legend lists the exact
rendered colour of each class or value, so the value at a coordinate is the
legend entry whose colour is nearest to the tile pixel there.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from functools import lru_cache
from io import BytesIO
import json
import math
from typing import Any, Literal

from PIL import Image, UnidentifiedImageError

from server.common.typing import is_json_array, is_json_object

DEFAULT_TILE_SIZE = 256
# Web Mercator is undefined at the poles; tiles stop at this latitude.
MAX_MERCATOR_LATITUDE = 85.05112878
# Largest Euclidean RGB distance still accepted as a legend colour. It absorbs
# PNG quantisation and resampling at class edges without matching unrelated
# colours (adjacent legend colours are usually far further apart).
LEGEND_COLOR_TOLERANCE = 24.0
# Legend labels shown in a compact model-facing legend summary.
MAX_SUMMARY_LABELS = 8

LegendKind = Literal["continuous", "categorical"]
Rgb = tuple[int, int, int]

###############################################################################
class RasterSamplingError(ValueError):
    """Raised when a coordinate, tile or legend cannot be sampled."""

###############################################################################
@dataclass(frozen=True)
class TilePixel:
    z: int
    x: int
    y: int
    pixel_x: int
    pixel_y: int
    tile_size: int

###############################################################################
@dataclass(frozen=True)
class LegendEntry:
    rgb: Rgb
    color: str
    value: float | None
    label: str

###############################################################################
@dataclass(frozen=True)
class CompiledLegend:
    kind: LegendKind
    title: str | None
    units: str | None
    entries: tuple[LegendEntry, ...]
    nodata: tuple[Rgb, ...]

###############################################################################
def lonlat_to_tile_pixel(
    lon: float, lat: float, z: int, *, tile_size: int = DEFAULT_TILE_SIZE
) -> TilePixel:
    """Return the Web Mercator XYZ tile and pixel that contain a coordinate."""

    if not (math.isfinite(lon) and math.isfinite(lat)):
        raise RasterSamplingError("Coordinates must be finite numbers.")
    if abs(lat) > MAX_MERCATOR_LATITUDE:
        raise RasterSamplingError(
            f"Latitude must be within ±{MAX_MERCATOR_LATITUDE:.4f} for map tiles."
        )
    if z < 0 or tile_size <= 0:
        raise RasterSamplingError("Zoom and tile size must be positive.")
    tiles = 1 << z
    wrapped_lon = ((lon + 180.0) % 360.0) - 180.0
    world_x = (wrapped_lon + 180.0) / 360.0 * tiles
    radians = math.radians(lat)
    world_y = (1.0 - math.asinh(math.tan(radians)) / math.pi) / 2.0 * tiles
    x = min(tiles - 1, max(0, int(math.floor(world_x))))
    y = min(tiles - 1, max(0, int(math.floor(world_y))))
    pixel_x = min(tile_size - 1, max(0, int((world_x - x) * tile_size)))
    pixel_y = min(tile_size - 1, max(0, int((world_y - y) * tile_size)))
    return TilePixel(z=z, x=x, y=y, pixel_x=pixel_x, pixel_y=pixel_y, tile_size=tile_size)

###############################################################################
def read_tile_rgba(png: bytes, pixel: TilePixel) -> tuple[int, int, int, int]:
    """Decode a tile image and read the RGBA colour at the pixel.

    Providers may answer with a larger image than the nominal tile size, so
    the pixel is rescaled to the decoded image dimensions.
    """

    try:
        with Image.open(BytesIO(png)) as image:
            rgba = image.convert("RGBA")
    except (UnidentifiedImageError, OSError) as exc:
        raise RasterSamplingError("The tile is not a decodable image.") from exc
    px = min(rgba.width - 1, pixel.pixel_x * rgba.width // pixel.tile_size)
    py = min(rgba.height - 1, pixel.pixel_y * rgba.height // pixel.tile_size)
    red, green, blue, alpha = rgba.getpixel((px, py))  # type: ignore[misc]
    return int(red), int(green), int(blue), int(alpha)  # pyright: ignore[reportUnknownArgumentType]

###############################################################################
def compile_legend(legend: Mapping[str, Any]) -> CompiledLegend | None:
    """Validate a manifest legend once and precompute its RGB tuples."""

    try:
        key = json.dumps(legend, sort_keys=True, default=str)
    except (TypeError, ValueError):
        return None
    return _compile_legend_cached(key)

###############################################################################
@lru_cache(maxsize=128)
def _compile_legend_cached(key: str) -> CompiledLegend | None:
    legend = json.loads(key)
    if not is_json_object(legend):
        return None
    kind = legend.get("kind")
    raw_entries = legend.get("entries")
    if kind not in ("continuous", "categorical") or not is_json_array(raw_entries):
        return None
    entries: list[LegendEntry] = []
    for raw in raw_entries:
        if not is_json_object(raw):
            continue
        rgb = _parse_hex_color(raw.get("color"))
        label = raw.get("label")
        if rgb is None or not isinstance(label, str):
            continue
        value = raw.get("value")
        numeric = (
            float(value)
            if isinstance(value, int | float) and not isinstance(value, bool)
            else None
        )
        entries.append(
            LegendEntry(rgb=rgb, color=_hex(rgb), value=numeric, label=label)
        )
    if not entries:
        return None
    raw_nodata = legend.get("nodata_colors")
    nodata: list[Rgb] = []
    for item in raw_nodata if is_json_array(raw_nodata) else []:
        rgb = _parse_hex_color(item)
        if rgb is not None:
            nodata.append(rgb)
    return CompiledLegend(
        kind=kind,
        title=_optional_text(legend.get("title")),
        units=_optional_text(legend.get("units")),
        entries=tuple(entries),
        nodata=tuple(nodata),
    )

###############################################################################
def match_legend(
    legend: CompiledLegend,
    rgba: tuple[int, int, int, int],
    *,
    tolerance: float = LEGEND_COLOR_TOLERANCE,
) -> dict[str, Any] | None:
    """Return the legend entry rendered at a pixel colour, or None for no data."""

    red, green, blue, alpha = rgba
    if alpha == 0:
        return None
    rgb = (red, green, blue)
    limit = tolerance * tolerance
    if any(_distance_squared(rgb, item) <= limit for item in legend.nodata):
        return None
    best = min(legend.entries, key=lambda entry: _distance_squared(rgb, entry.rgb))
    if _distance_squared(rgb, best.rgb) > limit:
        return None
    return {
        "value": best.value,
        "label": best.label,
        "units": legend.units,
        "kind": legend.kind,
        "matched_color": best.color,
    }

###############################################################################
def sample_tile(
    png: bytes, pixel: TilePixel, legend: CompiledLegend
) -> dict[str, Any] | None:
    """Read the legend value at one pixel of a decoded tile."""

    return match_legend(legend, read_tile_rgba(png, pixel))

###############################################################################
def summarize_legend(legend: object) -> dict[str, Any] | None:
    """Compact a legend for model context: range or a few class labels."""

    if not is_json_object(legend):
        return None
    compiled = compile_legend(legend)
    if compiled is None:
        return None
    summary: dict[str, Any] = {
        "title": (compiled.title or "")[:120] or None,
        "units": compiled.units,
        "kind": compiled.kind,
    }
    values = [entry.value for entry in compiled.entries if entry.value is not None]
    if compiled.kind == "continuous" and values:
        summary["min"] = min(values)
        summary["max"] = max(values)
        return summary
    labels = list(dict.fromkeys(entry.label[:60] for entry in compiled.entries))
    summary["labels"] = labels[:MAX_SUMMARY_LABELS]
    if len(labels) > MAX_SUMMARY_LABELS:
        summary["label_count"] = len(labels)
    return summary

###############################################################################
def _parse_hex_color(value: object) -> Rgb | None:
    if not isinstance(value, str):
        return None
    text = value.strip().removeprefix("#")
    if len(text) != 6:
        return None
    try:
        return int(text[0:2], 16), int(text[2:4], 16), int(text[4:6], 16)
    except ValueError:
        return None

###############################################################################
def _hex(rgb: Rgb) -> str:
    return "#{:02x}{:02x}{:02x}".format(*rgb)

###############################################################################
def _distance_squared(left: Rgb, right: Rgb) -> int:
    return sum((a - b) * (a - b) for a, b in zip(left, right, strict=True))

###############################################################################
def _optional_text(value: object) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None

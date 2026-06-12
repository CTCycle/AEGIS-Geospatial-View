import { LngLatBoundsLike, Map, StyleSpecification } from 'maplibre-gl';

import {
  DEFAULT_BASE_ATTRIBUTION,
  DEFAULT_BASE_TILE_MAX_ZOOM,
  DEFAULT_BASE_TILE_PROXY_URL,
  DEFAULT_BASE_TILE_URL,
  DEFAULT_OVERLAY_OPACITY,
  DEFAULT_WMS_EXCEPTIONS,
  DEFAULT_WMS_LAYER_ID,
  DEFAULT_WMS_VERSION,
  DEFAULT_WMTS_FORMAT,
  DEFAULT_WMTS_MATRIX_SET,
} from '../core/constants';
import { MapOverlayEntry, MapSession, OverlayRenderStatus } from '../core/types';
import { isFiniteNumber } from '../core/type-guards';

export type OverlayEntry = MapOverlayEntry;
type RasterOverlayKind = 'tile' | 'wms' | 'wmts';

const toMessage = (error: unknown): string => {
  if (error instanceof Error && error.message.trim()) {
    return error.message;
  }
  if (typeof error === 'string' && error.trim()) {
    return error;
  }
  return 'Overlay rendering failed.';
};

export const recordBooleanEqual = (a: Record<string, boolean>, b: Record<string, boolean>): boolean => {
  const aKeys = Object.keys(a);
  const bKeys = Object.keys(b);
  if (aKeys.length !== bKeys.length) {
    return false;
  }
  return aKeys.every((key) => a[key] === b[key]);
};

export const recordNumberEqual = (a: Record<string, number>, b: Record<string, number>): boolean => {
  const aKeys = Object.keys(a);
  const bKeys = Object.keys(b);
  if (aKeys.length !== bKeys.length) {
    return false;
  }
  return aKeys.every((key) => a[key] === b[key]);
};

const appendQuery = (baseUrl: string, query: string): string => {
  const separator = baseUrl.includes('?') ? '&' : '?';
  return `${baseUrl}${separator}${query}`;
};

const isFiniteBoundsTuple = (value: unknown): value is [number, number, number, number] => (
  Array.isArray(value)
  && value.length === 4
  && value.every(isFiniteNumber)
);

const normalizeOverlayBounds = (
  bounds?: [number, number, number, number],
): [number, number, number, number] | undefined => {
  if (!isFiniteBoundsTuple(bounds)) {
    return undefined;
  }
  return bounds;
};

const buildWmsTileUrl = (overlay: OverlayEntry): string | null => {
  if (overlay.tile_url_template) {
    return overlay.tile_url_template;
  }
  if (!overlay.url) {
    return null;
  }
  const layers = overlay.layers || DEFAULT_WMS_LAYER_ID;
  const version = overlay.wms_version || DEFAULT_WMS_VERSION;
  const exceptions = overlay.wms_exceptions || DEFAULT_WMS_EXCEPTIONS;
  const query = [
    'service=WMS',
    'request=GetMap',
    `layers=${encodeURIComponent(layers)}`,
    'styles=',
    'format=image/png',
    'transparent=true',
    `version=${encodeURIComponent(version)}`,
    'srs=EPSG:3857',
    `exceptions=${encodeURIComponent(exceptions)}`,
    'bbox={bbox-epsg-3857}',
    'width=256',
    'height=256',
  ].join('&');
  return appendQuery(overlay.url, query);
};

const buildWmtsTileUrl = (overlay: OverlayEntry): string | null => {
  if (overlay.tile_url_template) {
    return overlay.tile_url_template;
  }
  if (!overlay.url) {
    return null;
  }
  const layerId = overlay.layer_id || overlay.layers || DEFAULT_WMS_LAYER_ID;
  const matrixSet = overlay.tile_matrix_set || DEFAULT_WMTS_MATRIX_SET;
  const format = overlay.wmts_format || DEFAULT_WMTS_FORMAT;
  const style = overlay.wmts_style ?? '';
  const query = [
    'service=WMTS',
    'request=GetTile',
    'version=1.0.0',
    `layer=${encodeURIComponent(layerId)}`,
    `style=${encodeURIComponent(style)}`,
    `tilematrixset=${encodeURIComponent(matrixSet)}`,
    `tilematrix=${matrixSet}:{z}`,
    'tilerow={y}',
    'tilecol={x}',
    `format=${encodeURIComponent(format)}`,
  ].join('&');
  return appendQuery(overlay.url, query);
};

const buildBasemapTileUrl = (mapSession?: MapSession): string => {
  const basemap = mapSession?.basemap;
  const tileUrl = basemap?.tile_url || DEFAULT_BASE_TILE_URL;
  if (tileUrl === DEFAULT_BASE_TILE_URL) {
    return DEFAULT_BASE_TILE_PROXY_URL;
  }
  try {
    const parsed = new URL(tileUrl);
    if (parsed.hostname === 'tile.openstreetmap.org') {
      return DEFAULT_BASE_TILE_PROXY_URL;
    }
  } catch {
    return tileUrl;
  }
  return tileUrl;
};

export const buildStyle = (mapSession?: MapSession): StyleSpecification => {
  const basemap = mapSession?.basemap;
  const baseTileUrl = buildBasemapTileUrl(mapSession);
  const basemapPaint = mapSession?.basemap_id === 'osm_dark'
    ? {
      'raster-brightness-max': 0.45,
      'raster-contrast': 0.35,
      'raster-saturation': -0.8,
    }
    : {};
  return {
    version: 8,
    sources: {
      basemap: {
        type: 'raster',
        tiles: [baseTileUrl],
        tileSize: 256,
        maxzoom: DEFAULT_BASE_TILE_MAX_ZOOM,
        attribution: basemap?.attribution || DEFAULT_BASE_ATTRIBUTION,
      },
    },
    layers: [
      {
        id: 'basemap',
        type: 'raster',
        source: 'basemap',
        minzoom: 0,
        maxzoom: DEFAULT_BASE_TILE_MAX_ZOOM,
        paint: basemapPaint,
      },
    ],
  };
};

export const addOverlayLayers = (map: Map, mapSession?: MapSession): OverlayRenderStatus[] => {
  const overlays = mapSession?.overlays || [];
  const statuses: OverlayRenderStatus[] = [];

  overlays.forEach((overlay, index) => {
    const sourceId = `overlay-source-${overlay.id}`;
    const layerId = `overlay-layer-${overlay.id}`;
    const opacity = typeof overlay.default_opacity === 'number' ? overlay.default_opacity : DEFAULT_OVERLAY_OPACITY;
    const sourceBounds = normalizeOverlayBounds(overlay.bounds);
    const renderingMode = String(overlay.rendering_mode || overlay.type || '').toLowerCase();
    try {
      if (renderingMode === 'metadata-only' || overlay.type === 'metadata-only') {
        statuses.push({
          overlayId: overlay.id,
          status: 'metadata-only',
          message: 'This layer is available as metadata or setup context only.',
        });
        return;
      }

      if (
        ['xyz', 'raster-tile', 'wmts', 'wms', 'tile'].includes(renderingMode)
        && addRasterOverlayLayer(map, overlay, sourceId, layerId, opacity, sourceBounds)
      ) {
        statuses.push({ overlayId: overlay.id, status: 'loaded' });
        return;
      }

      if (
        ['geojson', 'arcgis-geojson', 'clustered-points', 'choropleth', 'camera-points'].includes(renderingMode)
        && addGeoJsonOverlayLayer(map, overlay, sourceId, layerId, opacity)
      ) {
        statuses.push({ overlayId: overlay.id, status: 'loaded' });
        return;
      }

      if (renderingMode === 'vector-tile' && addVectorTileOverlayLayer(map, overlay, sourceId, layerId, opacity)) {
        statuses.push({ overlayId: overlay.id, status: 'loaded' });
        return;
      }

      if (overlay.type === 'point-insight') {
        const center = mapSession?.center;
        if (typeof center?.longitude !== 'number' || typeof center?.latitude !== 'number') {
          throw new Error('Map center unavailable for point insight rendering.');
        }
        map.addSource(sourceId, {
          type: 'geojson',
          data: {
            type: 'FeatureCollection',
            features: [
              {
                type: 'Feature',
                properties: { label: overlay.label },
                geometry: {
                  type: 'Point',
                  coordinates: [center.longitude, center.latitude],
                },
              },
            ],
          },
        });
        map.addLayer({
          id: layerId,
          source: sourceId,
          type: 'circle',
          paint: {
            'circle-radius': 8 + index,
            'circle-color': '#ef4444',
            'circle-opacity': opacity,
            'circle-stroke-width': 1,
            'circle-stroke-color': '#111827',
          },
        });
        statuses.push({ overlayId: overlay.id, status: 'loaded' });
        return;
      }

      throw new Error('Unsupported overlay render descriptor.');
    } catch (error) {
      statuses.push({
        overlayId: overlay.id,
        status: 'failed',
        message: toMessage(error),
      });
    }
  });

  return statuses;
};

export const isGeoJsonOverlay = (overlay: OverlayEntry): boolean => {
  const overlayType = overlay.type.toLowerCase();
  const format = overlay.data_format?.toLowerCase() || '';
  const protocol = overlay.source_protocol?.toLowerCase() || '';
  return Boolean(
    overlay.url
    && (overlayType === 'geojson'
      || overlayType === 'arcgis-geojson'
      || format.includes('geojson')
      || protocol.includes('geojson')),
  );
};

const addGeoJsonOverlayLayer = (
  map: Map,
  overlay: OverlayEntry,
  sourceId: string,
  layerId: string,
  opacity: number,
): boolean => {
  if (!isGeoJsonOverlay(overlay) || !overlay.url) {
    return false;
  }
  map.addSource(sourceId, {
    type: 'geojson',
    data: overlay.url,
  });
  const renderingMode = String(overlay.rendering_mode || overlay.type).toLowerCase();
  const geometryType = overlay.geometry_type?.toLowerCase() || '';
  if (renderingMode === 'camera-points') {
    map.addLayer({
      id: layerId,
      source: sourceId,
      type: 'circle',
      paint: {
        'circle-radius': 7,
        'circle-color': '#f97316',
        'circle-opacity': opacity,
        'circle-stroke-width': 2,
        'circle-stroke-color': '#7c2d12',
      },
    });
    return true;
  }
  if (geometryType.includes('point') || renderingMode === 'clustered-points') {
    map.addLayer({
      id: layerId,
      source: sourceId,
      type: 'circle',
      paint: {
        'circle-radius': 5,
        'circle-color': '#0ea5e9',
        'circle-opacity': opacity,
        'circle-stroke-width': 1,
        'circle-stroke-color': '#082f49',
      },
    });
    return true;
  }
  if (renderingMode === 'choropleth' || geometryType.includes('polygon')) {
    map.addLayer({
      id: layerId,
      source: sourceId,
      type: 'fill',
      paint: {
        'fill-color': '#2563eb',
        'fill-opacity': Math.min(opacity, 0.55),
        'fill-outline-color': '#1e3a8a',
      },
    });
    return true;
  }
  map.addLayer({
    id: layerId,
    source: sourceId,
    type: 'line',
    paint: {
      'line-color': '#38bdf8',
      'line-width': 2,
      'line-opacity': opacity,
    },
  });
  return true;
};

const addVectorTileOverlayLayer = (
  map: Map,
  overlay: OverlayEntry,
  sourceId: string,
  layerId: string,
  opacity: number,
): boolean => {
  const tilesUrl = overlay.tile_url_template || overlay.url;
  const sourceLayer = overlay.source_layer || overlay.layer_id;
  if (!tilesUrl) {
    return false;
  }
  if (!sourceLayer) {
    throw new Error('Vector tile overlay is missing source_layer metadata.');
  }
  map.addSource(sourceId, {
    type: 'vector',
    tiles: [tilesUrl],
  });
  map.addLayer({
    id: layerId,
    source: sourceId,
    'source-layer': sourceLayer,
    type: 'fill',
    paint: {
      'fill-color': '#22c55e',
      'fill-opacity': Math.min(opacity, 0.45),
      'fill-outline-color': '#14532d',
    },
  });
  return true;
};

const buildRasterOverlayTiles = (overlay: OverlayEntry): string[] | null => {
  const overlayType = String(overlay.rendering_mode || overlay.type) as RasterOverlayKind | 'raster-tile' | 'xyz';
  if ((overlayType === 'tile' || overlayType === 'raster-tile' || overlayType === 'xyz') && (overlay.tile_url_template || overlay.url)) {
    return [overlay.tile_url_template || overlay.url as string];
  }
  if (overlayType === 'wms' && overlay.url) {
    const wmsTiles = buildWmsTileUrl(overlay);
    return wmsTiles ? [wmsTiles] : null;
  }
  if (overlayType === 'wmts' && overlay.url) {
    const wmtsTiles = buildWmtsTileUrl(overlay);
    return wmtsTiles ? [wmtsTiles] : null;
  }
  return null;
};

const addRasterOverlayLayer = (
  map: Map,
  overlay: OverlayEntry,
  sourceId: string,
  layerId: string,
  opacity: number,
  sourceBounds?: [number, number, number, number],
): boolean => {
  const tiles = buildRasterOverlayTiles(overlay);
  if (!tiles) {
    return false;
  }
  const rasterSource: {
    type: 'raster';
    tiles: string[];
    tileSize: number;
    bounds?: [number, number, number, number];
    maxzoom?: number;
  } = {
    type: 'raster',
    tiles,
    tileSize: overlay.tile_size || 256,
  };
  if (typeof overlay.minzoom === 'number') {
    (rasterSource as { minzoom?: number }).minzoom = overlay.minzoom;
  }
  if (typeof overlay.maxzoom === 'number') {
    rasterSource.maxzoom = overlay.maxzoom;
  }
  if (sourceBounds) {
    rasterSource.bounds = sourceBounds;
  }
  map.addSource(sourceId, rasterSource);
  map.addLayer({
    id: layerId,
    source: sourceId,
    type: 'raster',
    paint: { 'raster-opacity': opacity },
  });
  return true;
};

export const normalizeBounds = (bounds: unknown): LngLatBoundsLike | null => {
  if (!isFiniteBoundsTuple(bounds)) {
    return null;
  }
  const [minx, miny, maxx, maxy] = bounds;
  return [[minx, miny], [maxx, maxy]];
};

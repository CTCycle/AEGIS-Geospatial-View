import type { ExpressionSpecification } from 'maplibre-gl';
import { LngLatBoundsLike, Map, Marker, StyleSpecification } from 'maplibre-gl';
import type { GeoJSON } from 'geojson';

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
import { mapOverlayEntryFromInstance } from '../core/api-parsers';
import { MapOverlayEntry, MapSession, OverlayRenderStatus } from '../core/types';
import { isFiniteNumber } from '../core/type-guards';

export type OverlayEntry = MapOverlayEntry;
type RasterOverlayKind = 'tile' | 'wms' | 'wmts';
type ClusterGeoJsonSource = {
  type: 'geojson';
  getClusterExpansionZoom: (
    clusterId: number,
    callback: (error: Error | null, zoom: number) => void,
  ) => void;
};

export const mapSessionOverlayEntries = (mapSession?: MapSession): OverlayEntry[] => (
  mapSession?.overlay_collection?.instances.flatMap((instance) => {
    const entry = mapOverlayEntryFromInstance(instance);
    return entry ? [entry] : [];
  }) || []
);

export const reconcileOverlayOrder = (
  overlays: readonly OverlayEntry[],
  preferredOrder: readonly string[] = [],
): string[] => {
  const availableIds = new Set(overlays.map((overlay) => overlay.id));
  const seenIds = new Set<string>();
  const order: string[] = [];
  for (const id of preferredOrder) {
    if (availableIds.has(id) && !seenIds.has(id)) {
      seenIds.add(id);
      order.push(id);
    }
  }
  for (const overlay of overlays) {
    if (!seenIds.has(overlay.id)) {
      seenIds.add(overlay.id);
      order.push(overlay.id);
    }
  }
  return order;
};

export const orderOverlayEntries = (
  overlays: readonly OverlayEntry[],
  preferredOrder: readonly string[] = [],
): OverlayEntry[] => {
  const order = reconcileOverlayOrder(overlays, preferredOrder);
  const positionById = new globalThis.Map(order.map((id, index) => [id, index]));
  return [...overlays].sort((left, right) => (
    (positionById.get(left.id) ?? Number.MAX_SAFE_INTEGER)
    - (positionById.get(right.id) ?? Number.MAX_SAFE_INTEGER)
  ));
};

const toMessage = (error: unknown): string => {
  if (error instanceof Error && error.message.trim()) {
    return error.message;
  }
  if (typeof error === 'string' && error.trim()) {
    return error;
  }
  return 'Overlay rendering failed.';
};

const noResultsStatus = (overlay: OverlayEntry): OverlayRenderStatus => (
  String(overlay.result_status || '').toLowerCase() === 'valid_empty'
    ? {
      overlayId: overlay.id,
      status: 'no-results',
      message: 'No results in the requested area or time window.',
    }
    : { overlayId: overlay.id, status: 'loaded' }
);

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

const applyTimeIfNeeded = (
  template: string,
  descriptor: { time?: string | null; default_time?: string | null },
): string => {
  const time = descriptor.time || descriptor.default_time;
  return time ? template.replaceAll('{time}', encodeURIComponent(time)) : template;
};

const isFiniteBoundsTuple = (value: unknown): value is [number, number, number, number] => (
  Array.isArray(value)
  && value.length === 4
  && value.every(isFiniteNumber)
  && value[0] >= -180
  && value[0] <= 180
  && value[1] >= -90
  && value[1] <= 90
  && value[2] >= -180
  && value[2] <= 180
  && value[3] >= -90
  && value[3] <= 90
  && value[1] <= value[3]
  && !(value[0] > value[2] && (value[0] < 150 || value[2] > -150))
);

const normalizeOverlayBounds = (
  bounds?: [number, number, number, number],
): [number, number, number, number] | undefined => {
  if (!isFiniteBoundsTuple(bounds)) {
    return undefined;
  }
  return bounds;
};

const buildWmsTileUrl = (
  descriptor: OverlayEntry | NonNullable<OverlayEntry['render']>,
): string | null => {
  if (descriptor.tile_url_template) {
    return applyTimeIfNeeded(descriptor.tile_url_template, descriptor);
  }
  if (!descriptor.url) {
    return null;
  }
  const layers = 'layers' in descriptor && descriptor.layers ? descriptor.layers : descriptor.layer_id || DEFAULT_WMS_LAYER_ID;
  const version = DEFAULT_WMS_VERSION;
  const exceptions = DEFAULT_WMS_EXCEPTIONS;
  const crs = descriptor.crs || 'EPSG:3857';
  const format = descriptor.format || 'image/png';
  const style = descriptor.style || '';
  const crsKey = version.startsWith('1.3') ? 'crs' : 'srs';
  const query = [
    'service=WMS',
    'request=GetMap',
    `layers=${encodeURIComponent(layers)}`,
    `styles=${encodeURIComponent(style)}`,
    `format=${encodeURIComponent(format)}`,
    'transparent=true',
    `version=${encodeURIComponent(version)}`,
    `${crsKey}=${encodeURIComponent(crs)}`,
    `exceptions=${encodeURIComponent(exceptions)}`,
    'bbox={bbox-epsg-3857}',
    'width=256',
    'height=256',
    ...((descriptor.time || descriptor.default_time) ? [`time=${encodeURIComponent(descriptor.time || descriptor.default_time || '')}`] : []),
  ].join('&');
  return appendQuery(descriptor.url, query);
};

const buildWmtsTileUrl = (
  descriptor: OverlayEntry | NonNullable<OverlayEntry['render']>,
): string | null => {
  if (descriptor.tile_url_template) {
    return applyTimeIfNeeded(descriptor.tile_url_template, descriptor);
  }
  if (!descriptor.url) {
    return null;
  }
  const layerId = descriptor.layer_id || ('layers' in descriptor ? descriptor.layers : undefined) || DEFAULT_WMS_LAYER_ID;
  const matrixSet = descriptor.tile_matrix_set || DEFAULT_WMTS_MATRIX_SET;
  const format = descriptor.format || DEFAULT_WMTS_FORMAT;
  const style = descriptor.style || 'default';
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
    ...((descriptor.time || descriptor.default_time) ? [`time=${encodeURIComponent(descriptor.time || descriptor.default_time || '')}`] : []),
  ].join('&');
  return appendQuery(descriptor.url, query);
};

const buildBasemapTileUrl = (mapSession?: MapSession): string | null => {
  const basemap = mapSession?.basemap;
  if (mapSession && (!basemap || basemap.render_status === 'unavailable')) {
    return null;
  }
  const basemapId = mapSession?.basemap_id || basemap?.id || 'osm_default';
  const tileUrl = basemap?.tile_url || (basemapId === 'osm_default' ? DEFAULT_BASE_TILE_URL : null);
  if (!tileUrl) {
    return null;
  }
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
        tiles: baseTileUrl ? [baseTileUrl] : [],
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
  const overlays = mapSessionOverlayEntries(mapSession);
  const statuses: OverlayRenderStatus[] = [];

  overlays.forEach((overlay, index) => {
    const sourceId = `overlay-source-${overlay.id}`;
    const layerId = `overlay-layer-${overlay.id}`;
    const layerIds = getOverlayLayerIds(overlay);
    const opacity = typeof overlay.default_opacity === 'number' ? overlay.default_opacity : DEFAULT_OVERLAY_OPACITY;
    const sourceBounds = normalizeOverlayBounds(overlay.bounds);
    const renderingMode = String(
      overlay.render?.rendering_mode || overlay.rendering_mode || overlay.type || '',
    ).toLowerCase();
    try {
      if (
        typeof map.getLayer === 'function'
        && typeof map.getSource === 'function'
        && layerIds.some((id) => map.getLayer(id))
      ) {
        statuses.push(noResultsStatus(overlay));
        return;
      }
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
        statuses.push(noResultsStatus(overlay));
        return;
      }

      if (
        ['geojson', 'arcgis-geojson', 'clustered-points', 'choropleth', 'camera-points', 'circles', 'place-markers'].includes(renderingMode)
        && addGeoJsonOverlayLayer(map, overlay, sourceId, layerId, opacity)
      ) {
        statuses.push(noResultsStatus(overlay));
        return;
      }

      if (renderingMode === 'vector-tile' && addVectorTileOverlayLayer(map, overlay, sourceId, layerId, opacity)) {
        statuses.push(noResultsStatus(overlay));
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
        statuses.push(noResultsStatus(overlay));
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

// Place names are HTML markers: raster basemap styles carry no glyphs, so a
// symbol layer could not label them.
const placeLabels = new WeakMap<Map, globalThis.Map<string, Marker[]>>();

const removePlaceLabels = (map: Map, overlayId: string): void => {
  placeLabels.get(map)?.get(overlayId)?.forEach((marker) => marker.remove());
  placeLabels.get(map)?.delete(overlayId);
};

export const setPlaceLabelsVisible = (map: Map, overlayId: string, visible: boolean): void => {
  placeLabels.get(map)?.get(overlayId)?.forEach((marker) => {
    marker.getElement().style.display = visible ? '' : 'none';
  });
};

const addPlaceLabels = (map: Map, overlay: OverlayEntry): void => {
  removePlaceLabels(map, overlay.id);
  if (typeof map.getCanvasContainer !== 'function') {
    return;
  }
  const data = overlay.data as { features?: Array<{ geometry?: { coordinates?: unknown }; properties?: Record<string, unknown> }> } | undefined;
  const markers: Marker[] = [];
  for (const feature of data?.features || []) {
    const coordinates = feature.geometry?.coordinates;
    const name = String(feature.properties?.['name'] || '').trim();
    if (!Array.isArray(coordinates) || !isFiniteNumber(coordinates[0]) || !isFiniteNumber(coordinates[1]) || !name) {
      continue;
    }
    const element = document.createElement('div');
    element.className = 'aegis-place-label';
    element.textContent = name;
    markers.push(
      new Marker({ element, anchor: 'bottom', offset: [0, -10] })
        .setLngLat([coordinates[0], coordinates[1]])
        .addTo(map),
    );
  }
  let byOverlay = placeLabels.get(map);
  if (!byOverlay) {
    byOverlay = new globalThis.Map();
    placeLabels.set(map, byOverlay);
  }
  byOverlay.set(overlay.id, markers);
};

export const removeOverlayLayers = (map: Map, mapSession?: MapSession): void => {
  const entries = mapSessionOverlayEntries(mapSession);
  const keptOverlayIds = new Set(entries.map((overlay) => overlay.id));
  for (const overlayId of [...(placeLabels.get(map)?.keys() || [])]) {
    if (!keptOverlayIds.has(overlayId)) {
      removePlaceLabels(map, overlayId);
    }
  }
  const keep = new Set(entries.flatMap(getOverlayLayerIds));
  const sourcesToRemove = new Set<string>();
  const styleLayers = typeof map.getStyle === 'function' ? map.getStyle()?.layers || [] : [];
  for (const layer of styleLayers) {
    if (!layer.id.startsWith('overlay-layer-') || keep.has(layer.id)) {
      continue;
    }
    if (map.getLayer(layer.id)) {
      map.removeLayer(layer.id);
    }
    const source = (layer as unknown as { source?: unknown }).source;
    sourcesToRemove.add(
      typeof source === 'string'
        ? source
        : `overlay-source-${layer.id.slice('overlay-layer-'.length)}`,
    );
  }
  for (const sourceId of sourcesToRemove) {
    if (map.getSource(sourceId)) {
      map.removeSource(sourceId);
    }
  }
};

export const getOverlayLayerIds = (overlay: OverlayEntry): string[] => {
  const layerId = `overlay-layer-${overlay.id}`;
  const renderingMode = String(
    overlay.render?.rendering_mode || overlay.rendering_mode || overlay.type || '',
  ).toLowerCase();
  if (overlay.value_encoding?.mode === 'heatmap') return [`${layerId}-heatmap`, `${layerId}-centres`];
  if (renderingMode === 'clustered-points' && !overlay.value_encoding) {
    return [
      `${layerId}-clusters`,
      `${layerId}-cluster-count`,
      `${layerId}-points`,
    ];
  }
  return [layerId];
};

export const applyOverlayLayerOrder = (
  map: Map,
  overlays: readonly OverlayEntry[],
  preferredOrder: readonly string[] = [],
): void => {
  const overlaysById = new globalThis.Map(overlays.map((overlay) => [overlay.id, overlay]));
  const order = reconcileOverlayOrder(overlays, preferredOrder);

  // The control list is front-to-back. MapLibre appends moved layers to the
  // top, so apply the order from back to front and keep clustered layers grouped.
  for (const overlayId of [...order].reverse()) {
    const overlay = overlaysById.get(overlayId);
    if (!overlay) {
      continue;
    }
    for (const layerId of getOverlayLayerIds(overlay)) {
      if (map.getLayer(layerId)) {
        map.moveLayer(layerId);
      }
    }
  }
};

export const isGeoJsonOverlay = (overlay: OverlayEntry): boolean => {
  const overlayType = overlay.type.toLowerCase();
  const renderingMode = String(overlay.rendering_mode || '').toLowerCase();
  const format = overlay.data_format?.toLowerCase() || '';
  const protocol = overlay.source_protocol?.toLowerCase() || '';
  const geoJsonRenderingModes = new Set([
    'geojson',
    'arcgis-geojson',
    'clustered-points',
    'circles',
    'choropleth',
    'camera-points',
    'place-markers',
  ]);
  return Boolean(
    (overlay.url || overlay.data)
    && (overlayType === 'geojson'
      || overlayType === 'arcgis-geojson'
      || geoJsonRenderingModes.has(renderingMode)
      || format.includes('geojson')
      || protocol.includes('geojson')),
  );
};

const mapHasGlyphs = (map: Map): boolean => {
  if (typeof map.getStyle !== 'function') {
    // Keep lightweight map doubles useful in unit tests. Real MapLibre maps
    // always expose getStyle(), so an absent glyphs URL is handled below.
    return true;
  }
  try {
    const glyphs = map.getStyle()?.glyphs;
    return typeof glyphs === 'string' && glyphs.trim().length > 0;
  } catch {
    return false;
  }
};

const addGeoJsonOverlayLayer = (
  map: Map,
  overlay: OverlayEntry,
  sourceId: string,
  layerId: string,
  opacity: number,
): boolean => {
  if (!isGeoJsonOverlay(overlay) || (!overlay.url && !overlay.data)) {
    return false;
  }
  const renderingMode = String(overlay.rendering_mode || overlay.type).toLowerCase();
  map.addSource(sourceId, {
    type: 'geojson',
    data: (overlay.data || overlay.url!) as unknown as GeoJSON,
    ...(renderingMode === 'clustered-points' && !overlay.value_encoding
      ? { cluster: true, clusterMaxZoom: 14, clusterRadius: 50 }
      : {}),
  });
  const encoding = overlay.value_encoding;
  if (encoding) {
    const value: ExpressionSpecification = ['to-number', ['get', encoding.field], encoding.min];
    if (encoding.mode === 'heatmap') {
      map.addLayer({id: `${layerId}-heatmap`, source: sourceId, type: 'heatmap', paint: {
        'heatmap-weight': encoding.min === encoding.max ? 1 : ['interpolate', ['linear'], value, encoding.min, 0, encoding.max, 1],
        'heatmap-radius': 30, 'heatmap-opacity': opacity,
      }});
      // Visible bin centres keep sparse heatmaps inspectable and provide
      // queryable rendered geometry (MapLibre heatmaps do not expose hits).
      map.addLayer({id: `${layerId}-centres`, source: sourceId, type: 'circle', paint: {
        'circle-radius': 3, 'circle-color': '#ffffff', 'circle-opacity': opacity,
        'circle-stroke-width': 1, 'circle-stroke-color': '#334155',
      }});
    } else {
      map.addLayer({id: layerId, source: sourceId, type: 'circle', paint: {
        'circle-color': encoding.min === encoding.max ? '#ef4444' : ['interpolate', ['linear'], value, encoding.min, '#38bdf8', encoding.max, '#ef4444'],
        'circle-radius': encoding.min === encoding.max ? 9 : ['interpolate', ['linear'], value, encoding.min, 4, encoding.max, 16],
        'circle-opacity': opacity, 'circle-stroke-width': 1, 'circle-stroke-color': '#ffffff',
      }});
    }
    return true;
  }
  const geometryType = overlay.geometry_type?.toLowerCase() || '';
  if (renderingMode === 'place-markers') {
    map.addLayer({
      id: layerId,
      source: sourceId,
      type: 'circle',
      paint: {
        'circle-radius': 8,
        'circle-color': '#dc2626',
        'circle-opacity': opacity,
        'circle-stroke-width': 2,
        'circle-stroke-color': '#ffffff',
      },
    });
    addPlaceLabels(map, overlay);
    return true;
  }
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
  if (renderingMode === 'clustered-points') {
    const baseLayerId = `overlay-layer-${overlay.id}`;
    map.addLayer({
      id: `${baseLayerId}-clusters`,
      source: sourceId,
      type: 'circle',
      filter: ['has', 'point_count'],
      paint: {
        'circle-color': [
          'step',
          ['get', 'point_count'],
          '#51bbd6',
          100,
          '#f1f075',
          750,
          '#f28cb1',
        ],
        'circle-radius': [
          'step',
          ['get', 'point_count'],
          16,
          100,
          20,
          750,
          24,
        ],
        'circle-opacity': opacity,
        'circle-stroke-width': 1,
        'circle-stroke-color': '#164e63',
      },
    });
    if (mapHasGlyphs(map)) {
      map.addLayer({
        id: `${baseLayerId}-cluster-count`,
        source: sourceId,
        type: 'symbol',
        filter: ['has', 'point_count'],
        layout: {
          'text-field': ['get', 'point_count_abbreviated'],
          'text-size': 12,
        },
        paint: {
          'text-color': '#ffffff',
          'text-halo-color': '#164e63',
          'text-halo-width': 1,
          'text-opacity': opacity,
        },
      });
    }
    map.addLayer({
      id: `${baseLayerId}-points`,
      source: sourceId,
      type: 'circle',
      filter: ['!', ['has', 'point_count']],
      paint: {
        'circle-radius': 5,
        'circle-color': '#0ea5e9',
        'circle-opacity': opacity,
        'circle-stroke-width': 1,
        'circle-stroke-color': '#082f49',
      },
    });
    if (typeof map.on === 'function') {
      map.on('click', `${baseLayerId}-clusters`, (event) => {
        const features = map.queryRenderedFeatures(event.point, {
          layers: [`${baseLayerId}-clusters`],
        });
        const clusterId = features[0]?.properties?.['cluster_id'];
        if (!isFiniteNumber(clusterId)) {
          return;
        }
        const source = map.getSource(sourceId) as unknown as ClusterGeoJsonSource | undefined;
        if (
          !source
          || source.type !== 'geojson'
          || typeof source.getClusterExpansionZoom !== 'function'
        ) {
          return;
        }
        source.getClusterExpansionZoom(clusterId, (error, zoom) => {
          if (error || !isFiniteNumber(zoom)) {
            return;
          }
          map.easeTo({ center: [event.lngLat.lng, event.lngLat.lat], zoom });
        });
      });
    }
    return true;
  }
  if (geometryType.includes('point')) {
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

export const buildRasterOverlayTiles = (overlay: OverlayEntry): string[] | null => {
  const render = overlay.render;
  if (render?.tile_url_template) {
    return [applyTimeIfNeeded(render.tile_url_template, render)];
  }
  if (overlay.tile_url_template) {
    return [applyTimeIfNeeded(overlay.tile_url_template, overlay)];
  }
  if (render?.rendering_mode === 'wms') {
    const wmsTiles = buildWmsTileUrl(render);
    return wmsTiles ? [wmsTiles] : null;
  }
  if (render?.rendering_mode === 'wmts') {
    const wmtsTiles = buildWmtsTileUrl(render);
    return wmtsTiles ? [wmtsTiles] : null;
  }
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
    tileSize: overlay.render?.tile_size || overlay.tile_size || 256,
  };
  const minZoom = overlay.render?.min_zoom ?? overlay.min_zoom;
  const maxZoom = overlay.render?.max_zoom ?? overlay.max_zoom;
  if (typeof minZoom === 'number') {
    (rasterSource as { minzoom?: number }).minzoom = minZoom;
  }
  if (typeof maxZoom === 'number') {
    rasterSource.maxzoom = maxZoom;
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

export interface FrameInsets {
  top: number;
  right: number;
  bottom: number;
  left: number;
}

export interface FrameRect {
  left: number;
  top: number;
  right: number;
  bottom: number;
}

// Half of the largest marker glyph plus a visual margin.
export const MARKER_FIT_PADDING_PX = 30;
const MAX_FRAME_INSET_FRACTION = 0.35;
const MAX_TARGET_ANCHORS = 500;

/**
 * Derives fitBounds padding from the measured UI overlays covering the map.
 * Each obstruction is attributed to the viewport edge it intrudes least from,
 * and the marker radius is added on top so symbols stay clear of the chrome.
 */
export const computeFrameInsets = (
  container: FrameRect,
  obstructions: FrameRect[],
  markerPx: number = MARKER_FIT_PADDING_PX,
): FrameInsets => {
  const insets: FrameInsets = { top: 0, right: 0, bottom: 0, left: 0 };
  for (const rect of obstructions) {
    const left = Math.max(rect.left, container.left);
    const top = Math.max(rect.top, container.top);
    const right = Math.min(rect.right, container.right);
    const bottom = Math.min(rect.bottom, container.bottom);
    if (right <= left || bottom <= top) {
      continue;
    }
    const extents: Array<[keyof FrameInsets, number]> = [
      ['top', bottom - container.top],
      ['bottom', container.bottom - top],
      ['left', right - container.left],
      ['right', container.right - left],
    ];
    const [edge, extent] = extents.reduce((best, item) => (item[1] < best[1] ? item : best));
    insets[edge] = Math.max(insets[edge], extent);
  }
  return insets.top + insets.right + insets.bottom + insets.left === 0
    ? insets
    : capInsets(insets, container);
};

const capInsets = (insets: FrameInsets, container: FrameRect): FrameInsets => {
  const maxX = (container.right - container.left) * MAX_FRAME_INSET_FRACTION;
  const maxY = (container.bottom - container.top) * MAX_FRAME_INSET_FRACTION;
  return {
    top: Math.min(insets.top, maxY),
    bottom: Math.min(insets.bottom, maxY),
    left: Math.min(insets.left, maxX),
    right: Math.min(insets.right, maxX),
  };
};

export const computeFitPadding = (
  container: FrameRect,
  obstructions: FrameRect[],
  markerPx: number = MARKER_FIT_PADDING_PX,
): FrameInsets => {
  const insets = computeFrameInsets(container, obstructions, markerPx);
  return {
    top: insets.top + markerPx,
    right: insets.right + markerPx,
    bottom: insets.bottom + markerPx,
    left: insets.left + markerPx,
  };
};

/** Representative [lon, lat] anchors of a feature collection (one per feature part). */
export const featureAnchors = (data: unknown): Array<[number, number]> => {
  const anchors: Array<[number, number]> = [];
  const features = (data as { features?: unknown } | null | undefined)?.features;
  if (!Array.isArray(features)) {
    return anchors;
  }
  const collect = (value: unknown, out: Array<[number, number]>): void => {
    if (Array.isArray(value) && value.length >= 2 && isFiniteNumber(value[0]) && isFiniteNumber(value[1])) {
      out.push([value[0], value[1]]);
    } else if (Array.isArray(value)) {
      value.forEach((item) => collect(item, out));
    }
  };
  for (const feature of features) {
    if (anchors.length >= MAX_TARGET_ANCHORS) {
      break;
    }
    const geometry = (feature as { geometry?: { type?: string; coordinates?: unknown } } | null)?.geometry;
    const vertices: Array<[number, number]> = [];
    collect(geometry?.coordinates, vertices);
    if (!vertices.length) {
      continue;
    }
    if (geometry?.type === 'MultiPoint') {
      anchors.push(...vertices);
      continue;
    }
    const lons = vertices.map((item) => item[0]);
    const lats = vertices.map((item) => item[1]);
    anchors.push([
      (Math.min(...lons) + Math.max(...lons)) / 2,
      (Math.min(...lats) + Math.max(...lats)) / 2,
    ]);
  }
  return anchors;
};

/** Whether every projected anchor lies in the container minus the overlay insets. */
export const allTargetsInView = (
  pixels: Array<{ x: number; y: number }>,
  container: FrameRect,
  insets: FrameInsets,
  markerPx: number = MARKER_FIT_PADDING_PX,
): boolean => {
  const margin = markerPx / 2;
  const minX = container.left + insets.left + margin;
  const maxX = container.right - insets.right - margin;
  const minY = container.top + insets.top + margin;
  const maxY = container.bottom - insets.bottom - margin;
  return pixels.every((p) => (
    Number.isFinite(p.x) && Number.isFinite(p.y)
    && p.x >= minX && p.x <= maxX && p.y >= minY && p.y <= maxY
  ));
};

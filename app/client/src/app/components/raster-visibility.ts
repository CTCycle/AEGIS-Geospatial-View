import { buildRasterOverlayTiles, OverlayEntry } from './map-preview-rendering';

export type GeographicBounds = [number, number, number, number];

export interface RasterTileProbe {
  url: string | null;
  z: number;
  x: number;
  y: number;
  tileIntersectsViewport: boolean | null;
  zoomSupported: boolean | null;
  failureCode?: string | null;
}

export interface RasterTileContentObservation {
  nonTransparentPixelCount: number | null;
  imageWidth?: number;
  imageHeight?: number;
  failureCode?: string | null;
}

export interface RasterVisibilityObservation {
  resultVisible: boolean | null;
  sourceLoaded: boolean | null;
  tileIntersectsViewport: boolean | null;
  zoomSupported: boolean | null;
  nonTransparentPixelCount: number | null;
  tile?: { z: number; x: number; y: number };
  failureCode?: string | null;
}

export interface RasterVisibilityContext {
  viewportBounds?: GeographicBounds;
  zoom?: number;
  center?: [number, number];
  sourcePresent: boolean;
  layerPresent: boolean;
  sourceLoaded: boolean | null;
  layerVisible: boolean;
  opacity: number | null;
}

export interface RasterImageLike {
  width: number;
  height: number;
  draw: (context: CanvasRenderingContext2D) => void;
  close?: () => void;
}

export interface RasterTileInspectionDependencies {
  fetch?: (input: RequestInfo | URL, init?: RequestInit) => Promise<Response>;
  decodeImage?: (blob: Blob) => Promise<RasterImageLike>;
  createCanvas?: () => HTMLCanvasElement;
  timeoutMs?: number;
}

const WEB_MERCATOR_HALF_WORLD = 20037508.342789244;
const MAX_PROBE_ZOOM = 30;
const MAX_IMAGE_PIXELS = 1024 * 1024;
const RASTER_MODES = new Set(['tile', 'raster-tile', 'xyz', 'wms', 'wmts']);

export const isRasterOverlay = (overlay: OverlayEntry): boolean => RASTER_MODES.has(
  String(overlay.render?.rendering_mode || overlay.rendering_mode || overlay.type || '').toLowerCase(),
);

const isFiniteBounds = (value: unknown): value is GeographicBounds => (
  Array.isArray(value)
  && value.length === 4
  && value.every((item) => typeof item === 'number' && Number.isFinite(item))
  && value[0] >= -180
  && value[0] <= 180
  && value[2] >= -180
  && value[2] <= 180
  && value[1] >= -90
  && value[1] <= 90
  && value[3] >= -90
  && value[3] <= 90
  && value[1] <= value[3]
);

const longitudeRanges = (west: number, east: number): Array<[number, number]> => (
  west <= east ? [[west, east]] : [[west, 180], [-180, east]]
);

const boundsIntersect = (left: GeographicBounds, right: GeographicBounds): boolean => (
  left[1] <= right[3]
  && left[3] >= right[1]
  && longitudeRanges(left[0], left[2]).some(([leftWest, leftEast]) => (
    longitudeRanges(right[0], right[2]).some(([rightWest, rightEast]) => (
      leftWest <= rightEast && leftEast >= rightWest
    ))
  ))
);

const intersectionBounds = (
  left: GeographicBounds,
  right: GeographicBounds,
): GeographicBounds | undefined => {
  if (!boundsIntersect(left, right)) {
    return undefined;
  }
  const leftRange = longitudeRanges(left[0], left[2])[0];
  const rightRange = longitudeRanges(right[0], right[2])[0];
  const west = Math.max(leftRange[0], rightRange[0]);
  const east = Math.min(leftRange[1], rightRange[1]);
  if (west > east) {
    return undefined;
  }
  return [west, Math.max(left[1], right[1]), east, Math.min(left[3], right[3])];
};

const clamp = (value: number, minimum: number, maximum: number): number => (
  Math.min(maximum, Math.max(minimum, value))
);

const longitudeToTileX = (longitude: number, zoom: number): number => (
  clamp(Math.floor(((longitude + 180) / 360) * (1 << zoom)), 0, (1 << zoom) - 1)
);

const latitudeToTileY = (latitude: number, zoom: number): number => {
  const boundedLatitude = clamp(latitude, -85.05112878, 85.05112878);
  const radians = boundedLatitude * Math.PI / 180;
  const normalized = (1 - Math.log(Math.tan(radians) + (1 / Math.cos(radians))) / Math.PI) / 2;
  return clamp(Math.floor(normalized * (1 << zoom)), 0, (1 << zoom) - 1);
};

const tileBounds = (z: number, x: number, y: number): GeographicBounds => {
  const scale = 1 << z;
  const west = (x / scale) * 360 - 180;
  const east = ((x + 1) / scale) * 360 - 180;
  const northRadians = Math.atan(Math.sinh(Math.PI * (1 - (2 * y) / scale)));
  const southRadians = Math.atan(Math.sinh(Math.PI * (1 - (2 * (y + 1)) / scale)));
  return [west, southRadians * 180 / Math.PI, east, northRadians * 180 / Math.PI];
};

const webMercatorTileBbox = (z: number, x: number, y: number): string => {
  const tileSpan = (WEB_MERCATOR_HALF_WORLD * 2) / (1 << z);
  const minX = -WEB_MERCATOR_HALF_WORLD + (x * tileSpan);
  const maxX = minX + tileSpan;
  const maxY = WEB_MERCATOR_HALF_WORLD - (y * tileSpan);
  const minY = maxY - tileSpan;
  return [minX, minY, maxX, maxY].join(',');
};

const materializeTileUrl = (template: string, z: number, x: number, y: number): string | null => {
  const resolved = template
    .replaceAll('{z}', String(z))
    .replaceAll('{x}', String(x))
    .replaceAll('{y}', String(y))
    .replaceAll('{bbox-epsg-3857}', webMercatorTileBbox(z, x, y));
  return /\{[^{}]+\}/.test(resolved) ? null : resolved;
};

export const buildRasterTileProbe = (
  overlay: OverlayEntry,
  viewportBounds: GeographicBounds | undefined,
  zoom: number | undefined,
  center: [number, number] | undefined,
): RasterTileProbe | null => {
  const template = buildRasterOverlayTiles(overlay)?.[0];
  if (!template || !viewportBounds || !isFiniteBounds(viewportBounds) || !Number.isFinite(zoom)) {
    return null;
  }
  const overlayBounds = isFiniteBounds(overlay.bounds) ? overlay.bounds : undefined;
  const requestedBounds = overlayBounds
    ? intersectionBounds(viewportBounds, overlayBounds)
    : viewportBounds;
  const requestedZoom = Math.floor(Number(zoom));
  const render = overlay.render || overlay;
  const minimumZoom = typeof render.min_zoom === 'number' ? Math.ceil(render.min_zoom) : 0;
  const maximumZoom = typeof render.max_zoom === 'number'
    ? Math.floor(render.max_zoom)
    : MAX_PROBE_ZOOM;
  const zoomSupported = requestedZoom >= minimumZoom
    && requestedZoom <= maximumZoom
    && maximumZoom >= minimumZoom;
  const probeZoom = clamp(requestedZoom, minimumZoom, Math.min(MAX_PROBE_ZOOM, maximumZoom));
  const fallbackCenter: [number, number] = requestedBounds
    ? [(requestedBounds[0] + requestedBounds[2]) / 2, (requestedBounds[1] + requestedBounds[3]) / 2]
    : [0, 0];
  const probeCenter = center
    && center[0] >= -180
    && center[0] <= 180
    && center[1] >= -90
    && center[1] <= 90
    && (!requestedBounds || (
      center[0] >= requestedBounds[0]
      && center[0] <= requestedBounds[2]
      && center[1] >= requestedBounds[1]
      && center[1] <= requestedBounds[3]
    ))
    ? center
    : fallbackCenter;
  const x = longitudeToTileX(probeCenter[0], probeZoom);
  const y = latitudeToTileY(probeCenter[1], probeZoom);
  const tileIntersectsViewport = requestedBounds
    ? boundsIntersect(tileBounds(probeZoom, x, y), viewportBounds)
    : false;
  return {
    url: requestedBounds && zoomSupported ? materializeTileUrl(template, probeZoom, x, y) : null,
    z: probeZoom,
    x,
    y,
    tileIntersectsViewport,
    zoomSupported,
    failureCode: !requestedBounds
      ? 'raster_tile_outside_viewport'
      : !zoomSupported
      ? 'raster_zoom_unsupported'
      : null,
  };
};

export const countNonTransparentPixels = (pixels: ArrayLike<number>): number => {
  let count = 0;
  for (let index = 3; index < pixels.length; index += 4) {
    if (Number(pixels[index]) > 0) {
      count += 1;
    }
  }
  return count;
};

const defaultDecodeImage = async (blob: Blob): Promise<RasterImageLike> => {
  if (typeof globalThis.createImageBitmap === 'function') {
    const bitmap = await globalThis.createImageBitmap(blob);
    return {
      width: bitmap.width,
      height: bitmap.height,
      draw: (context) => context.drawImage(bitmap, 0, 0),
      close: () => bitmap.close(),
    };
  }
  if (typeof globalThis.Image === 'undefined' || typeof globalThis.URL?.createObjectURL !== 'function') {
    throw new Error('Raster image decoding is unavailable.');
  }
  const objectUrl = globalThis.URL.createObjectURL(blob);
  try {
    const image = await new Promise<HTMLImageElement>((resolve, reject) => {
      const element = new globalThis.Image();
      element.onload = () => resolve(element);
      element.onerror = () => reject(new Error('Raster image decoding failed.'));
      element.src = objectUrl;
    });
    return {
      width: image.naturalWidth,
      height: image.naturalHeight,
      draw: (context) => context.drawImage(image, 0, 0),
      close: () => globalThis.URL.revokeObjectURL(objectUrl),
    };
  } catch (error) {
    globalThis.URL.revokeObjectURL(objectUrl);
    throw error;
  }
};

export const inspectRasterTileContent = async (
  url: string,
  dependencies: RasterTileInspectionDependencies = {},
): Promise<RasterTileContentObservation> => {
  const fetcher = dependencies.fetch || globalThis.fetch?.bind(globalThis);
  if (!fetcher) {
    return { nonTransparentPixelCount: null, failureCode: 'raster_probe_unavailable' };
  }
  const controller = typeof globalThis.AbortController === 'function'
    ? new globalThis.AbortController()
    : undefined;
  const timeout = globalThis.setTimeout(
    () => controller?.abort(),
    Math.max(250, dependencies.timeoutMs || 2500),
  );
  try {
    const response = await fetcher(url, {
      cache: 'force-cache',
      credentials: 'same-origin',
      signal: controller?.signal,
    });
    const contentType = response.headers.get('content-type')?.split(';', 1)[0].trim().toLowerCase();
    if (!response.ok) {
      return { nonTransparentPixelCount: null, failureCode: `raster_tile_http_${response.status}` };
    }
    if (response.type === 'opaque' || !contentType?.startsWith('image/')) {
      return { nonTransparentPixelCount: null, failureCode: 'raster_tile_not_image' };
    }
    const blob = await response.blob();
    if (!blob.size) {
      return { nonTransparentPixelCount: null, failureCode: 'raster_tile_empty_body' };
    }
    const image = await (dependencies.decodeImage || defaultDecodeImage)(blob);
    if (
      !Number.isInteger(image.width)
      || !Number.isInteger(image.height)
      || image.width <= 0
      || image.height <= 0
      || image.width * image.height > MAX_IMAGE_PIXELS
    ) {
      return { nonTransparentPixelCount: null, failureCode: 'raster_tile_invalid_dimensions' };
    }
    const canvas = (dependencies.createCanvas || (() => document.createElement('canvas')))();
    canvas.width = image.width;
    canvas.height = image.height;
    const context = canvas.getContext('2d', { willReadFrequently: true });
    if (!context) {
      return { nonTransparentPixelCount: null, failureCode: 'raster_canvas_unavailable' };
    }
    image.draw(context);
    const pixels = context.getImageData(0, 0, image.width, image.height).data;
    return {
      nonTransparentPixelCount: countNonTransparentPixels(pixels),
      imageWidth: image.width,
      imageHeight: image.height,
    };
  } catch {
    return { nonTransparentPixelCount: null, failureCode: 'raster_tile_probe_failed' };
  } finally {
    globalThis.clearTimeout(timeout);
    controller?.abort();
  }
};

export const observeRasterOverlay = async (
  overlay: OverlayEntry,
  context: RasterVisibilityContext,
  dependencies: RasterTileInspectionDependencies = {},
): Promise<RasterVisibilityObservation> => {
  const base: RasterVisibilityObservation = {
    resultVisible: null,
    sourceLoaded: context.sourceLoaded,
    tileIntersectsViewport: null,
    zoomSupported: null,
    nonTransparentPixelCount: null,
  };
  if (!context.sourcePresent || !context.layerPresent || context.sourceLoaded !== true) {
    return { ...base, failureCode: 'raster_source_not_loaded' };
  }
  if (!context.layerVisible) {
    return { ...base, resultVisible: false, failureCode: 'raster_layer_hidden' };
  }
  if (context.opacity === null || !Number.isFinite(context.opacity) || context.opacity <= 0) {
    return { ...base, resultVisible: false, failureCode: 'raster_layer_transparent' };
  }
  const probe = buildRasterTileProbe(overlay, context.viewportBounds, context.zoom, context.center);
  if (!probe) {
    return { ...base, failureCode: 'raster_tile_probe_unavailable' };
  }
  const observed: RasterVisibilityObservation = {
    ...base,
    tileIntersectsViewport: probe.tileIntersectsViewport,
    zoomSupported: probe.zoomSupported,
    tile: { z: probe.z, x: probe.x, y: probe.y },
    failureCode: probe.failureCode,
  };
  if (!probe.tileIntersectsViewport || !probe.zoomSupported || !probe.url) {
    return {
      ...observed,
      resultVisible: false,
      failureCode: probe.failureCode || 'raster_tile_outside_viewport',
    };
  }
  const content = await inspectRasterTileContent(probe.url, dependencies);
  return {
    ...observed,
    resultVisible: content.nonTransparentPixelCount === null
      ? null
      : content.nonTransparentPixelCount > 0,
    nonTransparentPixelCount: content.nonTransparentPixelCount,
    failureCode: content.failureCode || null,
  };
};

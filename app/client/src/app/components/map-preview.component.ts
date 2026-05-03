import {
  AfterViewInit,
  ChangeDetectorRef,
  Component,
  ElementRef,
  EventEmitter,
  Input,
  OnChanges,
  OnDestroy,
  Output,
  SimpleChanges,
  ViewChild,
} from '@angular/core';
import { DomSanitizer, SafeHtml } from '@angular/platform-browser';
import maplibregl, { LngLatBoundsLike, Map, StyleSpecification } from 'maplibre-gl';

import { OverlayControlsComponent } from './overlay-controls.component';
import {
  DEFAULT_BASE_ATTRIBUTION,
  DEFAULT_BASE_TILE_MAX_ZOOM,
  DEFAULT_BASE_TILE_PROXY_URL,
  DEFAULT_BASE_TILE_URL,
  DEFAULT_MAP_FIT_MAX_ZOOM,
  DEFAULT_OVERLAY_OPACITY,
  DEFAULT_WMS_EXCEPTIONS,
  DEFAULT_WMS_LAYER_ID,
  DEFAULT_WMS_VERSION,
  DEFAULT_WMTS_FORMAT,
  DEFAULT_WMTS_MATRIX_SET,
} from '../core/constants';
import {
  MapSession,
  OverlayOpacityChange,
  OverlayStateChange,
  OverlayVisibilityChange,
  SearchResponsePayload,
} from '../core/types';

type OverlayEntry = NonNullable<MapSession['overlays']>[number];
type RasterOverlayKind = 'tile' | 'wms' | 'wmts';

const recordBooleanEqual = (a: Record<string, boolean>, b: Record<string, boolean>): boolean => {
  const aKeys = Object.keys(a);
  const bKeys = Object.keys(b);
  if (aKeys.length !== bKeys.length) {
    return false;
  }
  return aKeys.every((key) => a[key] === b[key]);
};

const recordNumberEqual = (a: Record<string, number>, b: Record<string, number>): boolean => {
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

const normalizeOverlayBounds = (
  bounds?: [number, number, number, number],
): [number, number, number, number] | undefined => {
  if (!Array.isArray(bounds) || bounds.length !== 4) {
    return undefined;
  }
  const [minLon, minLat, maxLon, maxLat] = bounds;
  return [minLon, minLat, maxLon, maxLat];
};

const buildWmsTileUrl = (overlay: OverlayEntry): string | null => {
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

const buildStyle = (mapSession?: MapSession): StyleSpecification => {
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

const addOverlayLayers = (map: Map, mapSession?: MapSession) => {
  const overlays = mapSession?.overlays || [];
  overlays.forEach((overlay, index) => {
    const sourceId = `overlay-source-${overlay.id}`;
    const layerId = `overlay-layer-${overlay.id}`;
    const opacity = typeof overlay.default_opacity === 'number' ? overlay.default_opacity : DEFAULT_OVERLAY_OPACITY;
    const sourceBounds = normalizeOverlayBounds(overlay.bounds);
    if (addRasterOverlayLayer(map, overlay, sourceId, layerId, opacity, sourceBounds)) {
      return;
    }

    if (addGeoJsonOverlayLayer(map, overlay, sourceId, layerId, opacity)) {
      return;
    }

    if (overlay.type === 'point-insight') {
      const center = mapSession?.center;
      if (typeof center?.longitude !== 'number' || typeof center?.latitude !== 'number') {
        return;
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
    }
  });
};

const isGeoJsonOverlay = (overlay: OverlayEntry): boolean => {
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
  const geometryType = overlay.geometry_type?.toLowerCase() || '';
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

const buildRasterOverlayTiles = (overlay: OverlayEntry): string[] | null => {
  const overlayType = overlay.type as RasterOverlayKind;
  if (overlayType === 'tile' && overlay.url) {
    return [overlay.url];
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
    tileSize: 256,
  };
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

const normalizeBounds = (bounds: unknown): LngLatBoundsLike | null => {
  if (!Array.isArray(bounds) || bounds.length !== 4) {
    return null;
  }
  const [minx, miny, maxx, maxy] = bounds;
  return [[minx, miny], [maxx, maxy]];
};

@Component({
  selector: 'app-map-preview',
  standalone: true,
  imports: [OverlayControlsComponent],
  templateUrl: './map-preview.component.html',
  styleUrl: './map-preview.component.css',
})
export class MapPreviewComponent implements AfterViewInit, OnChanges, OnDestroy {
  @Input() payload?: SearchResponsePayload;
  @Input() isLoading = false;
  @Input() emptyMessage = 'Run a search to display the map.';
  @Input() initialOverlayVisibility: Record<string, boolean> = {};
  @Input() initialOverlayOpacity: Record<string, number> = {};
  @Output() overlayStateChange = new EventEmitter<OverlayStateChange>();

  @ViewChild('mapContainer', { static: false })
  private set mapContainer(value: ElementRef<HTMLDivElement> | undefined) {
    this.mapContainerRef = value;
    if (value && this.viewInitialized) {
      queueMicrotask(() => this.recreateMapIfPossible());
    }
  }

  mapSession?: MapSession;
  overlayVisibility: Record<string, boolean> = {};
  overlayOpacity: Record<string, number> = {};
  restoreNotice = '';

  private mapRef: Map | null = null;
  private mapContainerRef?: ElementRef<HTMLDivElement>;
  private viewInitialized = false;

  constructor(
    private readonly sanitizer: DomSanitizer,
    private readonly changeDetector: ChangeDetectorRef,
  ) {}

  get hasCenter(): boolean {
    return typeof this.mapSession?.center?.latitude === 'number'
      && typeof this.mapSession?.center?.longitude === 'number';
  }

  get overlays(): OverlayEntry[] {
    return this.mapSession?.overlays || [];
  }

  get complianceWarnings(): string[] {
    return this.mapSession?.compliance_warnings || [];
  }

  get embeddedMapHtml(): SafeHtml | null {
    const mapHtml = this.payload?.satellite_imagery?.map_html;
    return typeof mapHtml === 'string' && mapHtml.trim()
      ? this.sanitizer.bypassSecurityTrustHtml(mapHtml)
      : null;
  }

  ngAfterViewInit(): void {
    this.viewInitialized = true;
    if (!this.mapSession && this.payload) {
      this.syncSessionFromPayload();
      this.rebuildOverlayStateFromSession();
      this.changeDetector.detectChanges();
    }
    this.recreateMapIfPossible();
    this.applyOverlayStateToMap();
  }

  ngOnChanges(changes: SimpleChanges): void {
    if (changes['payload'] || changes['initialOverlayVisibility'] || changes['initialOverlayOpacity']) {
      this.syncSessionFromPayload();
      this.rebuildOverlayStateFromSession();
      this.recreateMapIfPossible();
      this.applyOverlayStateToMap();
    }
  }

  ngOnDestroy(): void {
    this.destroyMap();
  }

  setOverlayVisibility(overlayId: string, checked: boolean): void {
    this.overlayVisibility = { ...this.overlayVisibility, [overlayId]: checked };
    this.emitOverlayState();
    this.applyOverlayStateToMap();
  }

  setOverlayOpacity(overlayId: string, percentValue: string): void {
    const value = Number(percentValue) / 100;
    this.overlayOpacity = { ...this.overlayOpacity, [overlayId]: value };
    this.emitOverlayState();
    this.applyOverlayStateToMap();
  }

  onOverlayVisibilityChange(change: OverlayVisibilityChange): void {
    this.setOverlayVisibility(change.overlayId, change.checked);
  }

  onOverlayOpacityChange(change: OverlayOpacityChange): void {
    this.setOverlayOpacity(change.overlayId, change.percentValue);
  }

  zoomIn(): boolean {
    if (!this.mapRef) {
      return false;
    }
    this.mapRef.zoomIn({ duration: 120 });
    return true;
  }

  zoomOut(): boolean {
    if (!this.mapRef) {
      return false;
    }
    this.mapRef.zoomOut({ duration: 120 });
    return true;
  }

  private syncSessionFromPayload(): void {
    const next = this.payload?.map_session;
    if (!next) {
      this.mapSession = undefined;
      return;
    }
    const overlayIds = next.overlay_ids ?? [];
    const overlays = Array.isArray(next.overlays) && next.overlays.length > 0
      ? next.overlays
      : overlayIds.map((overlayId) => ({
        id: overlayId,
        label: overlayId,
        provider: 'manifest',
        type: 'tile',
      }));
    this.mapSession = {
      ...next,
      center: next.center ?? {
        latitude: next.resolved_location?.latitude ?? null,
        longitude: next.resolved_location?.longitude ?? null,
      },
      basemap: next.basemap ?? {
        id: next.basemap_id,
        label: next.basemap_id,
        provider: 'manifest',
      },
      overlays,
    };
  }

  private rebuildOverlayStateFromSession(): void {
    const overlays = this.mapSession?.overlays || [];
    const overlayIds = new Set(overlays.map((overlay) => overlay.id));
    const staleVisibilityKeys = Object.keys(this.initialOverlayVisibility).filter((key) => !overlayIds.has(key));
    const staleOpacityKeys = Object.keys(this.initialOverlayOpacity).filter((key) => !overlayIds.has(key));
    const staleIds = new Set([...staleVisibilityKeys, ...staleOpacityKeys]);

    this.restoreNotice = staleIds.size > 0
      ? `Some saved overlay preferences could not be restored (${staleIds.size} removed or unknown overlay id${staleIds.size === 1 ? '' : 's'}).`
      : '';

    const nextVisibility: Record<string, boolean> = {};
    overlays.forEach((overlay) => {
      nextVisibility[overlay.id] = this.overlayVisibility[overlay.id] ?? this.initialOverlayVisibility[overlay.id] ?? true;
    });
    this.overlayVisibility = recordBooleanEqual(this.overlayVisibility, nextVisibility) ? this.overlayVisibility : nextVisibility;

    const nextOpacity: Record<string, number> = {};
    overlays.forEach((overlay) => {
      const fallback = typeof overlay.default_opacity === 'number' ? overlay.default_opacity : DEFAULT_OVERLAY_OPACITY;
      nextOpacity[overlay.id] = this.overlayOpacity[overlay.id] ?? this.initialOverlayOpacity[overlay.id] ?? fallback;
    });
    this.overlayOpacity = recordNumberEqual(this.overlayOpacity, nextOpacity) ? this.overlayOpacity : nextOpacity;

    this.emitOverlayState();
  }

  private emitOverlayState(): void {
    this.overlayStateChange.emit({
      overlayVisibility: this.overlayVisibility,
      overlayOpacity: this.overlayOpacity,
    });
  }

  private recreateMapIfPossible(): void {
    if (this.embeddedMapHtml) {
      this.destroyMap();
      return;
    }
    const center = this.mapSession?.center;
    if (!this.viewInitialized) {
      return;
    }
    if (typeof center?.longitude !== 'number' || typeof center.latitude !== 'number') {
      this.destroyMap();
      return;
    }
    if (!this.mapContainerRef?.nativeElement) {
      return;
    }

    this.destroyMap();

    const map = new maplibregl.Map({
      container: this.mapContainerRef.nativeElement,
      style: buildStyle(this.mapSession),
      center: [center.longitude, center.latitude],
      zoom: 12,
    });

    map.on('load', () => {
      map.resize();
      addOverlayLayers(map, this.mapSession);
      const bounds = normalizeBounds(this.mapSession?.bounds);
      if (bounds) {
        map.fitBounds(bounds, { padding: 30, duration: 0, maxZoom: DEFAULT_MAP_FIT_MAX_ZOOM });
      }
      this.applyOverlayStateToMap();
    });

    this.mapRef = map;
  }

  private applyOverlayStateToMap(): void {
    const map = this.mapRef;
    if (!map || !this.mapSession?.overlays?.length) {
      return;
    }

    this.mapSession.overlays.forEach((overlay) => {
      const layerId = `overlay-layer-${overlay.id}`;
      if (!map.getLayer(layerId)) {
        return;
      }
      const visible = this.overlayVisibility[overlay.id] ?? true;
      map.setLayoutProperty(layerId, 'visibility', visible ? 'visible' : 'none');
      const opacityValue = this.overlayOpacity[overlay.id] ?? overlay.default_opacity ?? DEFAULT_OVERLAY_OPACITY;
      if (overlay.type === 'point-insight') {
        map.setPaintProperty(layerId, 'circle-opacity', opacityValue);
      } else if (isGeoJsonOverlay(overlay)) {
        const geometryType = overlay.geometry_type?.toLowerCase() || '';
        map.setPaintProperty(layerId, geometryType.includes('point') ? 'circle-opacity' : 'line-opacity', opacityValue);
      } else {
        map.setPaintProperty(layerId, 'raster-opacity', opacityValue);
      }
    });
  }

  private destroyMap(): void {
    if (this.mapRef) {
      this.mapRef.remove();
      this.mapRef = null;
    }
  }
}

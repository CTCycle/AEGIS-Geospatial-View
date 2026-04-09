import {
  AfterViewInit,
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
import maplibregl, { LngLatBoundsLike, Map, StyleSpecification } from 'maplibre-gl';

import {
  DEFAULT_BASE_ATTRIBUTION,
  DEFAULT_BASE_TILE_URL,
  DEFAULT_OVERLAY_OPACITY,
  DEFAULT_WMS_EXCEPTIONS,
  DEFAULT_WMS_LAYER_ID,
  DEFAULT_WMS_VERSION,
  DEFAULT_WMTS_FORMAT,
  DEFAULT_WMTS_MATRIX_SET,
} from '../core/constants';
import { MapSession, SearchResponsePayload } from '../core/types';

type OverlayEntry = NonNullable<MapSession['overlays']>[number];

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

const buildStyle = (mapSession?: MapSession): StyleSpecification => {
  const basemap = mapSession?.basemap;
  const baseTileUrl = basemap?.tile_url || DEFAULT_BASE_TILE_URL;
  return {
    version: 8,
    sources: {
      basemap: {
        type: 'raster',
        tiles: [baseTileUrl],
        tileSize: 256,
        attribution: basemap?.attribution || DEFAULT_BASE_ATTRIBUTION,
      },
    },
    layers: [
      {
        id: 'basemap',
        type: 'raster',
        source: 'basemap',
        minzoom: 0,
        maxzoom: 22,
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

    if (overlay.type === 'tile' && overlay.url) {
      const rasterSource: {
        type: 'raster';
        tiles: string[];
        tileSize: number;
        bounds?: [number, number, number, number];
      } = {
        type: 'raster',
        tiles: [overlay.url],
        tileSize: 256,
      };
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
      return;
    }

    if (overlay.type === 'wms' && overlay.url) {
      const wmsTiles = buildWmsTileUrl(overlay);
      if (!wmsTiles) {
        return;
      }
      const rasterSource: {
        type: 'raster';
        tiles: string[];
        tileSize: number;
        bounds?: [number, number, number, number];
      } = {
        type: 'raster',
        tiles: [wmsTiles],
        tileSize: 256,
      };
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
      return;
    }

    if (overlay.type === 'wmts' && overlay.url) {
      const wmtsTiles = buildWmtsTileUrl(overlay);
      if (!wmtsTiles) {
        return;
      }
      const rasterSource: {
        type: 'raster';
        tiles: string[];
        tileSize: number;
        bounds?: [number, number, number, number];
      } = {
        type: 'raster',
        tiles: [wmtsTiles],
        tileSize: 256,
      };
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

const normalizeBounds = (bounds?: number[]): LngLatBoundsLike | null => {
  if (!Array.isArray(bounds) || bounds.length !== 4) {
    return null;
  }
  const [minx, miny, maxx, maxy] = bounds;
  return [[minx, miny], [maxx, maxy]];
};

@Component({
  selector: 'app-map-preview',
  templateUrl: './map-preview.component.html',
  styleUrl: './map-preview.component.css',
})
export class MapPreviewComponent implements AfterViewInit, OnChanges, OnDestroy {
  @Input() payload?: SearchResponsePayload;
  @Input() isLoading = false;
  @Input() emptyMessage = 'Run a search to display the map.';
  @Input() initialOverlayVisibility: Record<string, boolean> = {};
  @Input() initialOverlayOpacity: Record<string, number> = {};
  @Output() overlayStateChange = new EventEmitter<{
    overlayVisibility: Record<string, boolean>;
    overlayOpacity: Record<string, number>;
  }>();

  @ViewChild('mapContainer', { static: false })
  private mapContainerRef?: ElementRef<HTMLDivElement>;

  mapSession?: MapSession;
  overlayVisibility: Record<string, boolean> = {};
  overlayOpacity: Record<string, number> = {};
  restoreNotice = '';

  private mapRef: Map | null = null;
  private viewInitialized = false;

  get hasCenter(): boolean {
    return typeof this.mapSession?.center?.latitude === 'number'
      && typeof this.mapSession?.center?.longitude === 'number';
  }

  ngAfterViewInit(): void {
    this.viewInitialized = true;
    this.syncSessionFromPayload();
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

  trackOverlay(_: number, overlay: OverlayEntry): string {
    return overlay.id;
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

  getOpacityPercent(overlay: OverlayEntry): number {
    return Math.round((this.overlayOpacity[overlay.id] ?? overlay.default_opacity ?? DEFAULT_OVERLAY_OPACITY) * 100);
  }

  private syncSessionFromPayload(): void {
    this.mapSession = this.payload?.map_session;
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
    if (!this.viewInitialized || !this.mapContainerRef?.nativeElement || !this.hasCenter || !this.mapSession?.center) {
      return;
    }

    this.destroyMap();

    const map = new maplibregl.Map({
      container: this.mapContainerRef.nativeElement,
      style: buildStyle(this.mapSession),
      center: [this.mapSession.center.longitude!, this.mapSession.center.latitude!],
      zoom: 12,
    });

    map.addControl(new maplibregl.NavigationControl({ showCompass: true }), 'top-right');
    map.on('load', () => {
      addOverlayLayers(map, this.mapSession);
      const bounds = normalizeBounds(this.mapSession?.bounds as number[] | undefined);
      if (bounds) {
        map.fitBounds(bounds, { padding: 30, duration: 0 });
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

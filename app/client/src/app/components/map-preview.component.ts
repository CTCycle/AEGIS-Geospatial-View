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
  SecurityContext,
  SimpleChanges,
  ViewChild,
} from '@angular/core';
import { DomSanitizer } from '@angular/platform-browser';
import maplibregl, { Map } from 'maplibre-gl';

import { DEFAULT_MAP_FIT_MAX_ZOOM, DEFAULT_OVERLAY_OPACITY } from '../core/constants';
import {
  MapSession,
  OverlayOpacityChange,
  OverlayStateChange,
  OverlayVisibilityChange,
  SearchResponsePayload,
} from '../core/types';
import { OverlayControlsComponent } from './overlay-controls.component';
import {
  OverlayEntry,
  addOverlayLayers,
  buildStyle,
  isGeoJsonOverlay,
  normalizeBounds,
  recordBooleanEqual,
  recordNumberEqual,
} from './map-preview-rendering';

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
    return Number.isFinite(this.mapSession?.center?.latitude)
      && Number.isFinite(this.mapSession?.center?.longitude);
  }

  get overlays(): OverlayEntry[] {
    return this.mapSession?.overlays || [];
  }

  get complianceWarnings(): string[] {
    return this.mapSession?.compliance_warnings || [];
  }

  get metadataOnlyOverlays(): OverlayEntry[] {
    return this.overlays.filter((overlay) => {
      const renderingMode = String(overlay.rendering_mode || overlay.type || '').toLowerCase();
      return renderingMode === 'metadata-only' || !overlay.url;
    });
  }

  get attributionEntries(): string[] {
    const entries = this.overlays
      .map((overlay) => overlay.attribution || overlay.provider)
      .filter((value): value is string => typeof value === 'string' && value.trim().length > 0);
    return Array.from(new Set(entries));
  }

  get legendEntries(): Array<{ id: string; label: string; mode: string }> {
    return this.overlays.map((overlay) => ({
      id: overlay.id,
      label: overlay.label,
      mode: String(overlay.rendering_mode || overlay.type || 'overlay'),
    }));
  }

  get embeddedMapHtml(): string | null {
    const mapHtml = this.mapSession?.payload?.embedded_map_html ?? this.payload?.satellite_imagery?.map_html;
    if (typeof mapHtml !== 'string' || mapHtml.trim().length === 0) {
      return null;
    }
    return this.sanitizer.sanitize(SecurityContext.HTML, mapHtml);
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
    const parsed = Number(percentValue);
    if (!Number.isFinite(parsed)) {
      return;
    }
    const value = Math.min(1, Math.max(0, parsed / 100));
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
    if (!Number.isFinite(center?.longitude) || !Number.isFinite(center?.latitude)) {
      this.destroyMap();
      return;
    }
    const longitude = Number(center?.longitude);
    const latitude = Number(center?.latitude);
    if (!this.mapContainerRef?.nativeElement) {
      return;
    }

    this.destroyMap();

    const map = new maplibregl.Map({
      container: this.mapContainerRef.nativeElement,
      style: buildStyle(this.mapSession),
      center: [longitude, latitude],
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
        const renderingMode = String(overlay.rendering_mode || overlay.type).toLowerCase();
        if (geometryType.includes('point') || renderingMode === 'camera-points' || renderingMode === 'clustered-points') {
          map.setPaintProperty(layerId, 'circle-opacity', opacityValue);
        } else if (geometryType.includes('polygon') || renderingMode === 'choropleth') {
          map.setPaintProperty(layerId, 'fill-opacity', Math.min(opacityValue, 0.55));
        } else {
          map.setPaintProperty(layerId, 'line-opacity', opacityValue);
        }
      } else if (String(overlay.rendering_mode || overlay.type).toLowerCase() === 'vector-tile') {
        map.setPaintProperty(layerId, 'fill-opacity', Math.min(opacityValue, 0.45));
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

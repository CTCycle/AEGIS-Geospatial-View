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
  ChangeDetectionStrategy
} from '@angular/core';
import maplibregl, { Map } from 'maplibre-gl';

import { DEFAULT_MAP_FIT_MAX_ZOOM, DEFAULT_OVERLAY_OPACITY } from '../core/constants';
import {
  MapSession,
  OverlayRenderStatus,
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
  removeOverlayLayers,
} from './map-preview-rendering';

export type MapRenderState = 'preparing' | 'ready' | 'failed';

export interface MapRenderStateChange {
  sessionId: string;
  state: MapRenderState;
  message?: string;
}

@Component({
  selector: 'app-map-preview',
  standalone: true,
  imports: [OverlayControlsComponent],
  templateUrl: './map-preview.component.html',
  changeDetection: ChangeDetectionStrategy.Eager,
  styleUrl: './map-preview.component.css',
})
export class MapPreviewComponent implements AfterViewInit, OnChanges, OnDestroy {
  @Input() payload?: SearchResponsePayload;
  @Input() isLoading = false;
  @Input() emptyMessage = 'Run a search to display the map.';
  @Input() initialOverlayVisibility: Record<string, boolean> = {};
  @Input() initialOverlayOpacity: Record<string, number> = {};
  @Output() overlayStateChange = new EventEmitter<OverlayStateChange>();
  @Output() renderStateChange = new EventEmitter<MapRenderStateChange>();

  @ViewChild('mapContainer', { static: false })
  private set mapContainer(value: ElementRef<HTMLDivElement> | undefined) {
    this.mapContainerRef = value;
    if (value && this.viewInitialized && !this.destroyed) {
      queueMicrotask(() => {
        if (!this.destroyed) {
          this.recreateMapIfPossible();
        }
      });
    }
  }

  mapSession?: MapSession;
  overlayVisibility: Record<string, boolean> = {};
  overlayOpacity: Record<string, number> = {};
  overlayRenderStatuses: OverlayRenderStatus[] = [];
  restoreNotice = '';

  private mapRef: Map | null = null;
  private activeMapContainer: HTMLDivElement | null = null;
  private activeBasemapId: string | null = null;
  private activeCenterKey: string | null = null;
  private mapContainerRef?: ElementRef<HTMLDivElement>;
  private viewInitialized = false;
  private mapPreparing = false;
  private destroyed = false;
  private candidateGeneration = 0;
  private pendingCandidate?: {
    map: Map;
    container: HTMLDivElement;
    originalContainer: HTMLDivElement;
    generation: number;
  };

  constructor(private readonly changeDetector: ChangeDetectorRef) {}

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
    const metadataOnlyIds = new Set(
      this.overlayRenderStatuses
        .filter((status) => status.status === 'metadata-only')
        .map((status) => status.overlayId),
    );
    return this.overlays.filter((overlay) => metadataOnlyIds.has(overlay.id));
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

  get failedOverlayStatuses(): OverlayRenderStatus[] {
    return this.overlayRenderStatuses.filter((status) => status.status === 'failed');
  }

  ngAfterViewInit(): void {
    if (this.destroyed) {
      return;
    }
    this.viewInitialized = true;
    if (!this.mapSession && this.payload) {
      this.syncSessionFromPayload();
      this.rebuildOverlayStateFromSession();
      // The session-derived loading state changes during view initialization;
      // publish it before MapLibre starts its external render lifecycle.
      this.changeDetector.detectChanges();
    }
    this.recreateMapIfPossible();
    this.applyOverlayStateToMap();
  }

  ngOnChanges(changes: SimpleChanges): void {
    if (this.destroyed) {
      return;
    }
    if (changes['payload'] || changes['initialOverlayVisibility'] || changes['initialOverlayOpacity']) {
      this.syncSessionFromPayload();
      this.rebuildOverlayStateFromSession();
      this.recreateMapIfPossible();
      this.applyOverlayStateToMap();
    }
  }

  ngOnDestroy(): void {
    this.destroyed = true;
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
      this.overlayRenderStatuses = [];
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
    this.overlayRenderStatuses = overlays.map((overlay) => ({
      overlayId: overlay.id,
      status: 'pending',
    }));
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
    const center = this.mapSession?.center;
    if (this.destroyed || !this.viewInitialized) {
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
    if (this.mapPreparing) {
      return;
    }

    const nextBasemapId = this.mapSession?.basemap_id || this.mapSession?.basemap?.id || null;
    const nextCenterKey = `${latitude.toFixed(5)}:${longitude.toFixed(5)}`;
    if (this.mapRef && this.activeBasemapId === nextBasemapId && this.activeCenterKey === nextCenterKey) {
      // Overlay and metadata updates are applied to the known-good map in place.
      removeOverlayLayers(this.mapRef, this.mapSession);
      this.overlayRenderStatuses = addOverlayLayers(this.mapRef, this.mapSession);
      this.applyOverlayStateToMap();
      this.emitRenderState('ready');
      this.changeDetector.detectChanges();
      return;
    }

    const originalContainer = this.mapContainerRef.nativeElement;
    const candidateContainer = this.mapRef
      ? this.createCandidateContainer(originalContainer)
      : originalContainer;
    const previousMap = this.mapRef;
    const previousContainer = this.activeMapContainer;
    this.emitRenderState('preparing');
    this.mapPreparing = true;
    let candidate: Map;
    try {
      candidate = new maplibregl.Map({
      container: candidateContainer,
      style: this.mapSession?.basemap?.style_url || buildStyle(this.mapSession),
      center: [longitude, latitude],
      zoom: 12,
      });
    } catch (error) {
      this.mapPreparing = false;
      this.removeCandidateContainer(candidateContainer, originalContainer);
      if (!this.destroyed) {
        this.emitRenderState('failed', this.safeRenderError(error));
      }
      return;
    }

    const generation = ++this.candidateGeneration;
    this.pendingCandidate = {
      map: candidate,
      container: candidateContainer,
      originalContainer,
      generation,
    };
    let candidateSettled = false;
    const isCurrentCandidate = (): boolean => !this.destroyed
      && !candidateSettled
      && this.pendingCandidate?.map === candidate
      && this.pendingCandidate.generation === generation;
    const clearCandidate = (): void => {
      if (this.pendingCandidate?.map === candidate) {
        this.pendingCandidate = undefined;
      }
    };

    candidate.on('error', (event: unknown) => {
      if (!isCurrentCandidate()) {
        return;
      }
      const error = (event as { error?: unknown } | null)?.error;
      if (error) {
        candidateSettled = true;
        this.mapPreparing = false;
        clearCandidate();
        candidate.remove();
        this.removeCandidateContainer(candidateContainer, originalContainer);
        if (!this.destroyed) {
          this.emitRenderState('failed', this.safeRenderError(error));
        }
      }
    });

    candidate.on('load', () => {
      if (!isCurrentCandidate()) {
        return;
      }
      candidate.resize();
      this.overlayRenderStatuses = addOverlayLayers(candidate, this.mapSession);
      const bounds = normalizeBounds(this.mapSession?.bounds);
      if (bounds) {
        candidate.fitBounds(bounds, { padding: 30, duration: 0, maxZoom: DEFAULT_MAP_FIT_MAX_ZOOM });
      }
      if (!this.hasRenderableCanvas(candidate, candidateContainer)) {
        candidateSettled = true;
        this.mapPreparing = false;
        clearCandidate();
        candidate.remove();
        this.removeCandidateContainer(candidateContainer, originalContainer);
        if (!this.destroyed) {
          this.emitRenderState('failed', 'The map source loaded but produced no renderable canvas.');
        }
        return;
      }
      candidateSettled = true;
      clearCandidate();
      this.mapPreparing = false;
      this.mapRef = candidate;
      this.activeMapContainer = candidateContainer;
      this.activeBasemapId = nextBasemapId;
      this.activeCenterKey = nextCenterKey;
      this.applyOverlayStateToMap();
      if (previousMap && previousMap !== candidate) {
        previousMap.remove();
        if (previousContainer && previousContainer !== originalContainer) {
          previousContainer.remove();
        }
      }
      this.emitRenderState('ready');
      this.changeDetector.detectChanges();
    });
  }

  private createCandidateContainer(original: HTMLDivElement): HTMLDivElement {
    const candidate = document.createElement('div');
    candidate.className = 'maplibre-container maplibre-container--candidate';
    // MapLibre adds its own `.maplibregl-map` class, which changes the
    // container from absolute positioning to a flow element. Keep the
    // candidate stacked over the known-good map with explicit inline sizing
    // until promotion (and after MapLibre initializes it).
    candidate.style.setProperty('position', 'absolute', 'important');
    candidate.style.setProperty('inset', '0', 'important');
    candidate.style.setProperty('width', '100%', 'important');
    candidate.style.setProperty('height', '100%', 'important');
    original.parentElement?.appendChild(candidate);
    return candidate;
  }

  private removeCandidateContainer(candidate: HTMLDivElement, original: HTMLDivElement): void {
    if (candidate !== original) {
      candidate.remove();
    }
  }

  private hasRenderableCanvas(map: Map, container: HTMLDivElement): boolean {
    const canvas = container.querySelector('canvas') as HTMLCanvasElement | null;
    if (!canvas) {
      // Unit-test doubles and non-DOM renderers do not expose a canvas.
      return typeof (map as unknown as { getCanvas?: () => unknown }).getCanvas !== 'function';
    }
    return canvas.width > 0 && canvas.height > 0;
  }

  private emitRenderState(state: MapRenderState, message?: string): void {
    const sessionId = this.mapSession?.session_id;
    if (sessionId) {
      this.renderStateChange.emit({ sessionId, state, message });
    }
  }

  private safeRenderError(error: unknown): string {
    if (error instanceof Error && error.message.trim()) {
      return `Map rendering failed: ${error.message}`;
    }
    return 'Map rendering failed. The previous map remains available.';
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
    this.mapPreparing = false;
    this.candidateGeneration += 1;
    const pendingCandidate = this.pendingCandidate;
    this.pendingCandidate = undefined;
    if (pendingCandidate) {
      pendingCandidate.map.remove();
      this.removeCandidateContainer(pendingCandidate.container, pendingCandidate.originalContainer);
    }
    if (this.mapRef) {
      this.mapRef.remove();
      this.mapRef = null;
    }
    if (this.activeMapContainer && this.activeMapContainer !== this.mapContainerRef?.nativeElement) {
      this.activeMapContainer.remove();
    }
    this.activeMapContainer = null;
    this.activeBasemapId = null;
    this.activeCenterKey = null;
  }
}

import {
  AfterViewInit,
  ChangeDetectorRef,
  Component,
  ElementRef,
  HostListener,
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
  CapabilityDescriptor,
  MapInspection,
  MapOverlayEntry,
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
  getOverlayLayerIds,
  isGeoJsonOverlay,
  mapSessionOverlayEntries,
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
  @Input() availableBasemaps: CapabilityDescriptor[] = [];
  @Output() overlayStateChange = new EventEmitter<OverlayStateChange>();
  @Output() renderStateChange = new EventEmitter<MapRenderStateChange>();
  @Output() basemapChange = new EventEmitter<string>();

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

  @ViewChild('inspectionPanel', { static: false })
  private inspectionPanelRef?: ElementRef<HTMLElement>;

  mapSession?: MapSession;
  overlayVisibility: Record<string, boolean> = {};
  overlayOpacity: Record<string, number> = {};
  overlayRenderStatuses: OverlayRenderStatus[] = [];
  restoreNotice = '';
  selectedInspection?: MapInspection;

  private inspectionTrigger: HTMLElement | null = null;
  private mapRef: Map | null = null;
  private activeMapContainer: HTMLDivElement | null = null;
  private activeBasemapId: string | null = null;
  private activeCenterKey: string | null = null;
  private mapContainerRef?: ElementRef<HTMLDivElement>;
  private resizeObserver?: ResizeObserver;
  private resizeFrame: number | null = null;
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
  private inspectionListeners: Array<{
    map: Map;
    layerId: string;
    handler: (event: unknown) => void;
  }> = [];

  constructor(
    private readonly changeDetector: ChangeDetectorRef,
    private readonly hostElement: ElementRef<HTMLElement>,
  ) {}

  get hasCenter(): boolean {
    return Number.isFinite(this.mapSession?.center?.latitude)
      && Number.isFinite(this.mapSession?.center?.longitude);
  }

  get overlays(): OverlayEntry[] {
    return mapSessionOverlayEntries(this.mapSession);
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

  get attributionEntries(): Array<{ label: string; url?: string }> {
    const entries = this.overlays
      .map((overlay) => ({
        label: overlay.attribution || overlay.provider,
        url: overlay.attribution_url || undefined,
      }))
      .filter((entry) => entry.label.trim().length > 0);
    const seen = new Set<string>();
    return entries.filter((entry) => {
      const key = `${entry.label}\u0000${entry.url || ''}`;
      if (seen.has(key)) {
        return false;
      }
      seen.add(key);
      return true;
    });
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
    this.observeHostSize();
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
    this.stopObservingHostSize();
    this.destroyMap();
  }

  get inspectionEntries(): MapInspection[] {
    const entries = this.overlays.flatMap((overlay) => overlay.inspections || []);
    return entries.filter((entry, index, all) => (
      all.findIndex((candidate) => candidate.inspection_id === entry.inspection_id) === index
    ));
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

  openInspection(inspection: MapInspection): void {
    this.inspectionTrigger = document.activeElement instanceof HTMLElement && document.activeElement !== document.body
      ? document.activeElement
      : null;
    this.selectedInspection = inspection;
    this.changeDetector.detectChanges();
    queueMicrotask(() => this.inspectionPanelRef?.nativeElement.focus());
  }

  inspectionForOverlayId(overlayId: string): MapInspection | undefined {
    return this.overlays.find((overlay) => overlay.id === overlayId)?.inspections?.[0];
  }

  closeInspection(): void {
    this.selectedInspection = undefined;
    const restoreTarget = this.inspectionTrigger;
    this.inspectionTrigger = null;
    queueMicrotask(() => {
      if (restoreTarget?.isConnected) {
        restoreTarget.focus();
      } else {
        this.mapContainerRef?.nativeElement.focus();
      }
    });
  }

  @HostListener('document:keydown', ['$event'])
  onDocumentKeydown(event: KeyboardEvent): void {
    if (event.key === 'Escape' && this.selectedInspection) {
      event.preventDefault();
      this.closeInspection();
    }
  }

  isSafeInspectionUrl(value: string | null | undefined): boolean {
    if (!value) {
      return false;
    }
    try {
      const parsed = new URL(value);
      return parsed.protocol === 'http:' || parsed.protocol === 'https:';
    } catch {
      return false;
    }
  }

  onBasemapSelection(value: string): void {
    const basemapId = String(value || '').trim();
    if (basemapId && basemapId !== this.mapSession?.basemap_id) {
      this.basemapChange.emit(basemapId);
    }
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
      this.selectedInspection = undefined;
      return;
    }
    this.mapSession = {
      ...next,
      center: next.center ?? {
        latitude: next.resolved_location?.latitude ?? null,
        longitude: next.resolved_location?.longitude ?? null,
      },
      basemap: next.basemap,
    };
    this.overlayRenderStatuses = this.overlays.map((overlay) => ({
      overlayId: overlay.id,
      status: 'pending',
    }));
    this.reconcileSelectedInspection();
  }

  private reconcileSelectedInspection(): void {
    if (!this.selectedInspection) {
      return;
    }
    this.selectedInspection = this.inspectionEntries.find((inspection) => (
      inspection.inspection_id === this.selectedInspection?.inspection_id
    ));
  }

  private rebuildOverlayStateFromSession(): void {
    const overlays = this.overlays;
    const overlayIds = new Set(overlays.map((overlay) => overlay.id));
    const staleVisibilityKeys = Object.keys(this.initialOverlayVisibility).filter((key) => !overlayIds.has(key));
    const staleOpacityKeys = Object.keys(this.initialOverlayOpacity).filter((key) => !overlayIds.has(key));
    const staleIds = new Set([...staleVisibilityKeys, ...staleOpacityKeys]);

    this.restoreNotice = staleIds.size > 0
      ? `Some saved overlay preferences could not be restored (${staleIds.size} removed or unknown overlay id${staleIds.size === 1 ? '' : 's'}).`
      : '';

    const nextVisibility: Record<string, boolean> = {};
    overlays.forEach((overlay) => {
      // The backend collection is authoritative. Local/session storage
      // preferences are only fallbacks for payloads without an explicit
      // visibility value.
      nextVisibility[overlay.id] =
        typeof overlay.visible === 'boolean'
          ? overlay.visible
          : this.overlayVisibility[overlay.id] ?? this.initialOverlayVisibility[overlay.id] ?? true;
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
      this.unbindInspectionListeners();
      removeOverlayLayers(this.mapRef, this.mapSession);
      this.overlayRenderStatuses = addOverlayLayers(this.mapRef, this.mapSession);
      this.bindInspectionListeners(this.mapRef);
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
        this.unbindInspectionListenersForMap(candidate);
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
      this.bindInspectionListeners(candidate);
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
      // `load` precedes the requests initiated by addOverlayLayers. Keep the
      // candidate and its error handler alive until those sources settle.
      candidate.on('idle', () => {
        if (!isCurrentCandidate()) {
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
        this.scheduleMapResize();
      });
    });
  }

  private observeHostSize(): void {
    if (typeof ResizeObserver === 'undefined') {
      return;
    }
    this.resizeObserver?.disconnect();
    this.resizeObserver = new ResizeObserver(() => this.scheduleMapResize());
    this.resizeObserver.observe(this.hostElement.nativeElement);
  }

  private stopObservingHostSize(): void {
    this.resizeObserver?.disconnect();
    this.resizeObserver = undefined;
    if (this.resizeFrame !== null) {
      cancelAnimationFrame(this.resizeFrame);
      this.resizeFrame = null;
    }
  }

  private scheduleMapResize(): void {
    if (this.destroyed || this.resizeFrame !== null) {
      return;
    }
    this.resizeFrame = requestAnimationFrame(() => {
      this.resizeFrame = null;
      if (this.destroyed) {
        return;
      }
      const maps = new Set<Map>();
      if (this.mapRef) {
        maps.add(this.mapRef);
      }
      if (this.pendingCandidate?.map) {
        maps.add(this.pendingCandidate.map);
      }
      maps.forEach((map) => map.resize());
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
    const message = error instanceof Error ? error.message : '';
    if (/\b(401|403)\b/.test(message)) {
      return 'Map layer access was denied. Check the provider credentials in Access.';
    }
    return 'A map data source could not be loaded. Check provider availability and try again.';
  }

  private applyOverlayStateToMap(): void {
    const map = this.mapRef;
    const overlays = this.overlays;
    if (!map || !overlays.length) {
      return;
    }

    overlays.forEach((overlay) => {
      const layerIds = getOverlayLayerIds(overlay);
      if (!layerIds.some((layerId) => map.getLayer(layerId))) {
        return;
      }
      const visible = this.overlayVisibility[overlay.id] ?? overlay.visible ?? true;
      const opacityValue = this.overlayOpacity[overlay.id] ?? overlay.default_opacity ?? DEFAULT_OVERLAY_OPACITY;
      layerIds.forEach((layerId) => {
        if (map.getLayer(layerId)) {
          map.setLayoutProperty(layerId, 'visibility', visible ? 'visible' : 'none');
        }
      });
      if (overlay.type === 'point-insight') {
        map.setPaintProperty(layerIds[0], 'circle-opacity', opacityValue);
      } else if (isGeoJsonOverlay(overlay)) {
        const geometryType = overlay.geometry_type?.toLowerCase() || '';
        const renderingMode = String(overlay.rendering_mode || overlay.type).toLowerCase();
        if (renderingMode === 'clustered-points') {
          const [clusterLayerId, countLayerId, pointLayerId] = layerIds;
          if (map.getLayer(clusterLayerId)) {
            map.setPaintProperty(clusterLayerId, 'circle-opacity', opacityValue);
          }
          if (map.getLayer(countLayerId)) {
            map.setPaintProperty(countLayerId, 'text-opacity', opacityValue);
          }
          if (map.getLayer(pointLayerId)) {
            map.setPaintProperty(pointLayerId, 'circle-opacity', opacityValue);
          }
        } else if (geometryType.includes('point') || renderingMode === 'camera-points') {
          map.setPaintProperty(layerIds[0], 'circle-opacity', opacityValue);
        } else if (geometryType.includes('polygon') || renderingMode === 'choropleth') {
          map.setPaintProperty(layerIds[0], 'fill-opacity', Math.min(opacityValue, 0.55));
        } else {
          map.setPaintProperty(layerIds[0], 'line-opacity', opacityValue);
        }
      } else if (String(overlay.rendering_mode || overlay.type).toLowerCase() === 'vector-tile') {
        map.setPaintProperty(layerIds[0], 'fill-opacity', Math.min(opacityValue, 0.45));
      } else {
        map.setPaintProperty(layerIds[0], 'raster-opacity', opacityValue);
      }
    });
  }

  private destroyMap(): void {
    this.mapPreparing = false;
    this.candidateGeneration += 1;
    const pendingCandidate = this.pendingCandidate;
    this.pendingCandidate = undefined;
    if (pendingCandidate) {
      this.unbindInspectionListenersForMap(pendingCandidate.map);
      pendingCandidate.map.remove();
      this.removeCandidateContainer(pendingCandidate.container, pendingCandidate.originalContainer);
    }
    if (this.mapRef) {
      this.unbindInspectionListeners();
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

  private bindInspectionListeners(map: Map): void {
    this.unbindInspectionListeners();
    this.overlays.forEach((overlay) => {
      const renderingMode = String(overlay.rendering_mode || overlay.type || '').toLowerCase();
      if (!['geojson', 'arcgis-geojson', 'clustered-points', 'choropleth', 'camera-points'].includes(renderingMode)) {
        return;
      }
      const layerIds = getOverlayLayerIds(overlay).filter((layerId) => !layerId.endsWith('-clusters') && !layerId.endsWith('-cluster-count'));
      layerIds.forEach((layerId) => {
        if (!map.getLayer(layerId) || typeof map.on !== 'function') {
          return;
        }
        const handler = (event: unknown): void => {
          const point = (event as { point?: unknown } | null)?.point;
          if (!point || typeof map.queryRenderedFeatures !== 'function') {
            return;
          }
          const features = map.queryRenderedFeatures(point as Parameters<Map['queryRenderedFeatures']>[0], { layers: [layerId] });
          const feature = features[0] as { id?: string | number; properties?: Record<string, unknown> } | undefined;
          if (!feature) {
            return;
          }
          const inspection = this.inspectionForFeature(overlay, feature);
          if (!inspection) {
            return;
          }
          this.openInspection(inspection);
        };
        this.registerLayerClickListener(map, layerId, handler);
        this.inspectionListeners.push({ map, layerId, handler });
      });
    });
  }

  private unbindInspectionListeners(): void {
    this.inspectionListeners.forEach(({ map, layerId, handler }) => {
      this.unregisterLayerClickListener(map, layerId, handler);
    });
    this.inspectionListeners = [];
  }

  private unbindInspectionListenersForMap(target: Map): void {
    const remaining: typeof this.inspectionListeners = [];
    this.inspectionListeners.forEach((entry) => {
      if (entry.map === target) {
        this.unregisterLayerClickListener(entry.map, entry.layerId, entry.handler);
      } else {
        remaining.push(entry);
      }
    });
    this.inspectionListeners = remaining;
  }

  private registerLayerClickListener(map: Map, layerId: string, handler: (event: unknown) => void): void {
    if (typeof map.on !== 'function') {
      return;
    }
    // MapLibre exposes a three-argument layer overload. Keep a small fallback
    // for lightweight map doubles used by the component tests and integrations.
    if (map.on.length >= 3) {
      map.on('click', layerId, handler as never);
    } else {
      map.on('click', handler as never);
    }
  }

  private unregisterLayerClickListener(map: Map, layerId: string, handler: (event: unknown) => void): void {
    if (typeof map.off !== 'function') {
      return;
    }
    if (map.off.length >= 3) {
      map.off('click', layerId, handler as never);
    } else {
      map.off('click', handler as never);
    }
  }

  private inspectionForFeature(
    overlay: MapOverlayEntry,
    feature: { id?: string | number; properties?: Record<string, unknown> },
  ): MapInspection | undefined {
    const featureId = String(feature.id ?? feature.properties?.['id'] ?? '');
    const existing = (overlay.inspections || []).find((entry) => (
      !featureId || entry.feature_id === featureId
    ));
    if (existing) {
      return existing;
    }
    const properties = feature.properties || {};
    const allowedKeys = new Set([
      'metric', 'value', 'unit', 'units', 'observation_time', 'observationTime',
      'forecast_time', 'forecastTime', 'time', 'freshness', 'name', 'label',
      'category', 'address', 'status', 'provider', 'event', 'severity',
      'effective', 'effective_time', 'expiry', 'expiry_time', 'feed', 'feed_id',
      'station', 'station_id', 'camera', 'camera_id', 'period', 'geography',
      'source', 'license', 'update_time', 'updated_at', 'updatedAt',
    ]);
    const fields = Object.entries(properties)
      .filter(([key]) => allowedKeys.has(key))
      .flatMap(([key, value], order) => {
        if (value !== null && typeof value !== 'string' && typeof value !== 'number' && typeof value !== 'boolean') {
          return [];
        }
        return [{
          key,
          label: key.replace(/([A-Z])/g, ' $1').replaceAll('_', ' ').replace(/^./, (value) => value.toUpperCase()),
          value: typeof value === 'string' ? value.slice(0, 240) : value,
          order,
        }];
      })
      .slice(0, 14);
    if (!fields.length) {
      return undefined;
    }
    return {
      inspection_id: `${overlay.id}:feature:${featureId || 'selected'}`,
      title: String(properties['name'] || properties['label'] || overlay.label).slice(0, 240),
      association: 'feature',
      provider: overlay.provider,
      feature_id: featureId || null,
      fields,
      warnings: [],
    };
  }

}

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
import { isFiniteNumber } from '../core/type-guards';

export type MapRenderState = 'preparing' | 'ready' | 'failed';

export interface MapRenderIdentity {
  runId: string;
  runVersion: number;
  mapSessionId: string;
  collectionRevision: number;
}

export interface MapRenderStateChange {
  sessionId: string;
  state: MapRenderState;
  runId?: string;
  runVersion?: number;
  message?: string;
  collectionRevision?: number;
  viewportBounds?: [number, number, number, number];
  checks?: Record<string, boolean>;
  overlayResults?: Array<Record<string, string | number | boolean | null>>;
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
  @Input() renderIdentity?: MapRenderIdentity;
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
  private activeSessionKey: string | null = null;
  private mapContainerRef?: ElementRef<HTMLDivElement>;
  private resizeObserver?: ResizeObserver;
  private resizeFrame: number | null = null;
  private viewInitialized = false;
  private mapPreparing = false;
  private awaitingBackendAcknowledgment = false;
  private awaitingCandidateMap: Map | null = null;
  private destroyed = false;
  private candidateGeneration = 0;
  private renderWatchdog?: number;
  private pendingCandidate?: {
    map: Map;
    container: HTMLDivElement;
    originalContainer: HTMLDivElement;
    generation: number;
  };
  private retainedPrevious?: {
    map: Map;
    container: HTMLDivElement | null;
    basemapId: string | null;
    centerKey: string | null;
    sessionKey: string | null;
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

  acceptRenderedCandidate(): void {
    const retained = this.retainedPrevious;
    this.retainedPrevious = undefined;
    this.awaitingBackendAcknowledgment = false;
    this.awaitingCandidateMap = null;
    if (!retained) {
      // An identical-session update may reuse the already committed map. Keep
      // it available when the backend rejects a no-op acknowledgment.
      if (this.mapRef) {
        this.mapPreparing = false;
        return;
      }
      return;
    }
    this.unbindInspectionListenersForMap(retained.map);
    retained.map.remove();
    if (retained.container && retained.container !== this.mapContainerRef?.nativeElement) {
      retained.container.remove();
    }
  }

  rejectRenderedCandidate(): void {
    this.clearRenderWatchdog();
    const pending = this.pendingCandidate;
    if (pending) {
      this.pendingCandidate = undefined;
      this.candidateGeneration += 1;
      this.unbindInspectionListenersForMap(pending.map);
      pending.map.remove();
      this.removeCandidateContainer(pending.container, pending.originalContainer);
    }
    const retained = this.retainedPrevious;
    this.retainedPrevious = undefined;
    if (retained) {
      if (this.mapRef && this.mapRef !== retained.map) {
        this.unbindInspectionListenersForMap(this.mapRef);
        this.mapRef.remove();
      }
      if (this.activeMapContainer && this.activeMapContainer !== retained.container) {
        this.activeMapContainer.remove();
      }
      this.mapRef = retained.map;
      this.activeMapContainer = retained.container;
      this.activeBasemapId = retained.basemapId;
      this.activeCenterKey = retained.centerKey;
      this.activeSessionKey = retained.sessionKey;
      this.mapPreparing = false;
      this.awaitingBackendAcknowledgment = false;
      this.awaitingCandidateMap = null;
      this.bindInspectionListeners(retained.map);
      this.applyOverlayStateToMap();
      return;
    }
    // An acknowledgment can be rejected for an unchanged session or before a
    // candidate map was allocated. Keep the already committed map in the
    // former case; only tear the map down when there is no committed instance.
    if (this.mapRef) {
      if (this.awaitingBackendAcknowledgment && this.mapRef === this.awaitingCandidateMap) {
        this.destroyMap();
        return;
      }
      this.mapPreparing = false;
      return;
    }
    this.destroyMap();
  }

  get metadataOnlyOverlays(): OverlayEntry[] {
    const metadataOnlyIds = new Set(
      this.overlayRenderStatuses
        .filter((status) => status.status === 'metadata-only')
        .map((status) => status.overlayId),
    );
    return this.overlays.filter((overlay) => metadataOnlyIds.has(overlay.id));
  }

  get noResultsOverlays(): OverlayEntry[] {
    const noResultsIds = new Set(
      this.overlayRenderStatuses
        .filter((status) => status.status === 'no-results')
        .map((status) => status.overlayId),
    );
    return this.overlays.filter((overlay) => noResultsIds.has(overlay.id));
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
    if (changes['payload'] || changes['renderIdentity'] || changes['initialOverlayVisibility'] || changes['initialOverlayOpacity']) {
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
      this.mapPreparing = false;
      this.awaitingBackendAcknowledgment = false;
      this.awaitingCandidateMap = null;
      if (this.renderIdentity) {
        this.emitRenderState(
          'failed',
          'The prepared map has no valid center coordinates.',
          { ...this.renderIdentity },
        );
      } else {
        this.destroyMap();
      }
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
    const nextSessionKey = this.mapSessionIdentityKey(this.mapSession);
    if (this.mapRef && this.activeSessionKey === nextSessionKey) {
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
    const previousBasemapId = this.activeBasemapId;
    const previousCenterKey = this.activeCenterKey;
    const previousSessionKey = this.activeSessionKey;
    if (this.retainedPrevious && previousMap && this.retainedPrevious.map !== previousMap) {
      this.acceptRenderedCandidate();
    }
    const candidateIdentity = this.renderIdentity
      ? { ...this.renderIdentity }
      : undefined;
    this.emitRenderState('preparing', undefined, candidateIdentity);
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
      this.awaitingBackendAcknowledgment = false;
      this.awaitingCandidateMap = null;
      this.removeCandidateContainer(candidateContainer, originalContainer);
      if (!this.destroyed) {
        this.emitRenderState('failed', this.safeRenderError(error), candidateIdentity);
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
    this.awaitingBackendAcknowledgment = Boolean(candidateIdentity);
    this.awaitingCandidateMap = candidateIdentity ? candidate : null;
    let candidateSettled = false;
    const isCurrentCandidate = (): boolean => !this.destroyed
      && !candidateSettled
      && this.pendingCandidate?.map === candidate
      && this.pendingCandidate.generation === generation;
    const clearCandidate = (): void => {
      if (this.pendingCandidate?.map === candidate) {
        this.pendingCandidate = undefined;
      }
      this.clearRenderWatchdog();
    };

    this.clearRenderWatchdog();
    this.renderWatchdog = window.setTimeout(() => {
      if (!isCurrentCandidate()) {
        return;
      }
      candidateSettled = true;
      this.mapPreparing = false;
      clearCandidate();
      this.unbindInspectionListenersForMap(candidate);
      candidate.remove();
      this.removeCandidateContainer(candidateContainer, originalContainer);
      if (!this.destroyed) {
        this.emitRenderState('failed', 'render_timeout', candidateIdentity);
        this.changeDetector.detectChanges();
      }
    }, 30_000);

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
          this.emitRenderState('failed', this.safeRenderError(error), candidateIdentity);
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
        this.emitRenderState(
          'failed',
          'The map source loaded but produced no renderable canvas.',
          candidateIdentity,
        );
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
        this.activeSessionKey = nextSessionKey;
        this.awaitingBackendAcknowledgment = Boolean(candidateIdentity);
        this.awaitingCandidateMap = candidateIdentity ? candidate : null;
        this.applyOverlayStateToMap();
        if (previousMap && previousMap !== candidate) {
          this.retainedPrevious = {
            map: previousMap,
            container: previousContainer,
            basemapId: previousBasemapId,
            centerKey: previousCenterKey,
            sessionKey: previousSessionKey,
          };
        }
        this.emitRenderState('ready', undefined, candidateIdentity);
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

  private emitRenderState(
    state: MapRenderState,
    message?: string,
    identity: MapRenderIdentity | undefined = this.renderIdentity,
  ): void {
    const sessionId = this.mapSession?.session_id;
    if (sessionId) {
      const evidence = this.renderEvidence(state);
      this.renderStateChange.emit({
        sessionId,
        state,
        runId: identity?.runId,
        runVersion: identity?.runVersion,
        message,
        collectionRevision: this.mapSession?.overlay_collection?.revision,
        viewportBounds: evidence.viewportBounds,
        checks: evidence.checks,
        overlayResults: evidence.overlayResults,
      });
    }
  }

  private renderEvidence(state: MapRenderState): {
    viewportBounds?: [number, number, number, number];
    checks: Record<string, boolean>;
    overlayResults: Array<Record<string, string | number | boolean | null>>;
  } {
    const session = this.mapSession;
    const map = this.mapRef;
    const rawBounds = this.readMapBounds(map) ?? session?.bounds ?? session?.viewport?.bbox;
    const viewportBounds: [number, number, number, number] | undefined = Array.isArray(rawBounds)
      && rawBounds.length === 4
      && rawBounds.every(isFiniteNumber)
      && rawBounds[0] >= -180 && rawBounds[0] <= 180
      && rawBounds[1] >= -90 && rawBounds[1] <= 90
      && rawBounds[2] >= -180 && rawBounds[2] <= 180
      && rawBounds[3] >= -90 && rawBounds[3] <= 90
      && rawBounds[1] <= rawBounds[3]
      ? [rawBounds[0], rawBounds[1], rawBounds[2], rawBounds[3]]
      : undefined;
    const overlayResults = this.overlays.map((overlay) => {
      const layerIds = getOverlayLayerIds(overlay);
      const metadataOnly = String(overlay.render?.rendering_mode || overlay.rendering_mode || overlay.type || '')
        .toLowerCase() === 'metadata-only' || overlay.type === 'metadata-only';
      const mapApi = map as unknown as {
        getLayer?: (id: string) => unknown;
        getSource?: (id: string) => unknown;
        getLayoutProperty?: (id: string, property: string) => unknown;
      } | null;
      const layerRecords = metadataOnly
        ? []
        : layerIds
          .map((id) => (mapApi?.getLayer ? mapApi.getLayer.call(map, id) : undefined))
          .filter((layer): layer is Record<string, unknown> => (
            Boolean(layer) && typeof layer === 'object'
          ));
      const present = metadataOnly || layerRecords.length > 0;
      const styleValid = metadataOnly || layerRecords.length > 0 && layerRecords.every((layer) => {
        const type = layer['type'];
        return typeof type === 'string' && type.trim().length > 0;
      });
      const zoomRangeValid = metadataOnly || layerRecords.length > 0 && layerRecords.every((layer) => {
        const minZoom = layer['minzoom'];
        const maxZoom = layer['maxzoom'];
        return (minZoom === undefined || isFiniteNumber(minZoom))
          && (maxZoom === undefined || isFiniteNumber(maxZoom))
          && (minZoom === undefined || maxZoom === undefined || Number(minZoom) <= Number(maxZoom));
      });
      const visible = metadataOnly || layerIds.some((id) => {
        if (!mapApi?.getLayer) {
          return false;
        }
        const layer = mapApi.getLayer.call(map, id) as Record<string, unknown> | undefined;
        if (!layer) {
          return false;
        }
        let visibility: unknown;
        try {
          visibility = mapApi.getLayoutProperty?.call(map, id, 'visibility');
        } catch {
          visibility = undefined;
        }
        if (visibility === undefined) {
          const layout = layer['layout'];
          visibility = layout && typeof layout === 'object'
            ? (layout as Record<string, unknown>)['visibility']
            : undefined;
        }
        return visibility !== 'none';
      });
      const desiredVisible = metadataOnly || (this.overlayVisibility[overlay.id] ?? overlay.visible ?? true);
      const status = this.overlayRenderStatuses.find((item) => item.overlayId === overlay.id)?.status;
      let renderedFeatureCount: number | null = null;
      if (!metadataOnly && map && present && typeof (map as unknown as {
        queryRenderedFeatures?: (geometry?: unknown, options?: unknown) => unknown;
      }).queryRenderedFeatures === 'function' && isGeoJsonOverlay(overlay)) {
        try {
          // A clustered overlay may omit its optional label layer when the
          // active style has no glyphs.  Passing that absent layer id to
          // MapLibre makes queryRenderedFeatures throw and incorrectly turns
          // a visibly rendered cluster/point layer into a render-ack failure.
          const queryLayerIds = layerIds.filter((id) => (
            Boolean(mapApi?.getLayer?.call(map, id))
          ));
          if (!queryLayerIds.length) {
            renderedFeatureCount = 0;
          } else {
          const features = (map as unknown as {
            queryRenderedFeatures: (geometry?: unknown, options?: unknown) => unknown;
          }).queryRenderedFeatures(undefined, { layers: queryLayerIds });
          renderedFeatureCount = Array.isArray(features) ? features.length : null;
          }
        } catch {
          renderedFeatureCount = null;
        }
      }
      return {
        overlay_id: overlay.id,
        capability_id: overlay.capability_id || overlay.id,
        source_present: metadataOnly || Boolean(
          mapApi?.getSource?.call(map, `overlay-source-${overlay.id}`),
        ),
        layer_present: present && styleValid && zoomRangeValid,
        loaded: status === 'loaded' || status === 'no-results' || metadataOnly,
        metadata_only: metadataOnly,
        visibility_matches: metadataOnly || visible === desiredVisible,
        style_valid: styleValid,
        zoom_range_valid: zoomRangeValid,
        rendered_feature_count: renderedFeatureCount,
        failure_code: status === 'failed' ? 'overlay_render_failed' : null,
      };
    });
    const required = overlayResults.filter((item) => item.metadata_only !== true);
    const checks = {
      required_sources_loaded: state === 'ready' && required.every((item) => item.loaded === true),
      required_layers_present: state === 'ready' && required.every((item) => item.layer_present === true),
      viewport_valid: state === 'ready' && Boolean(viewportBounds),
    };
    return { viewportBounds, checks, overlayResults };
  }

  private readMapBounds(map: Map | null): [number, number, number, number] | undefined {
    const getBounds = (map as unknown as {
      getBounds?: () => unknown;
    } | null)?.getBounds;
    if (typeof getBounds !== 'function' || !map) {
      return undefined;
    }
    try {
      const bounds = getBounds.call(map) as {
        getWest?: () => unknown;
        getSouth?: () => unknown;
        getEast?: () => unknown;
        getNorth?: () => unknown;
      } | undefined;
      const values = [
        bounds?.getWest?.(),
        bounds?.getSouth?.(),
        bounds?.getEast?.(),
        bounds?.getNorth?.(),
      ];
      if (values.every(isFiniteNumber)) {
        return values as [number, number, number, number];
      }
    } catch {
      // Fall back to the prepared session bounds when a test double or an
      // older MapLibre adapter does not expose camera bounds.
    }
    return undefined;
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
    this.clearRenderWatchdog();
    this.candidateGeneration += 1;
    const pendingCandidate = this.pendingCandidate;
    this.pendingCandidate = undefined;
    if (pendingCandidate) {
      this.unbindInspectionListenersForMap(pendingCandidate.map);
      pendingCandidate.map.remove();
      this.removeCandidateContainer(pendingCandidate.container, pendingCandidate.originalContainer);
    }
    if (this.retainedPrevious) {
      this.unbindInspectionListenersForMap(this.retainedPrevious.map);
      this.retainedPrevious.map.remove();
      if (this.retainedPrevious.container && this.retainedPrevious.container !== this.mapContainerRef?.nativeElement) {
        this.retainedPrevious.container.remove();
      }
      this.retainedPrevious = undefined;
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
    this.activeSessionKey = null;
    this.awaitingBackendAcknowledgment = false;
    this.awaitingCandidateMap = null;
  }

  private mapSessionIdentityKey(session?: MapSession): string | null {
    if (!session) {
      return null;
    }
    return JSON.stringify({
      sessionId: session.session_id,
      collectionRevision: session.overlay_collection?.revision ?? null,
      basemapId: session.basemap_id,
      center: session.center,
      bounds: session.bounds,
      viewport: session.viewport,
    });
  }

  private clearRenderWatchdog(): void {
    if (this.renderWatchdog !== undefined) {
      window.clearTimeout(this.renderWatchdog);
      this.renderWatchdog = undefined;
    }
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

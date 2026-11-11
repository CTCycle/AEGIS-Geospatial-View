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
  ChangeDetectionStrategy,
  signal,
} from '@angular/core';
import maplibregl, { Map, MapMouseEvent } from 'maplibre-gl';

import { fetchOverlaySample } from '../core/api';
import { ApiRequestError } from '../core/api-errors';

import {
  DEFAULT_MAP_FIT_MAX_ZOOM,
  DEFAULT_OVERLAY_OPACITY,
  DEFAULT_SATELLITE_MAP_FIT_MAX_ZOOM,
} from '../core/constants';
import {
  MapSession,
  CapabilityDescriptor,
  ClientMapView,
  MapInspection,
  MapOverlayEntry,
  OverlayRenderStatus,
  OverlayOpacityChange,
  OverlayStateChange,
  OverlayLegend,
  OverlaySampleResponse,
  OverlayVisibilityChange,
  SearchResponsePayload,
} from '../core/types';
import { OverlayControlsComponent } from './overlay-controls.component';
import { OverlayLegendComponent } from './overlay-legend.component';
import {
  HOVER_READOUT_DELAY_MS,
  HoverReadoutScheduler,
  formatHoverReadout,
  sampleCacheKey,
} from './overlay-legend';
import {
  FrameInsets,
  FrameRect,
  MARKER_FIT_PADDING_PX,
  OverlayEntry,
  allTargetsInView,
  applyOverlayLayerOrder,
  addOverlayLayers,
  computeFitPadding,
  computeFrameInsets,
  featureAnchors,
  buildRasterOverlayTiles,
  buildStyle,
  getOverlayLayerIds,
  isGeoJsonOverlay,
  mapSessionOverlayEntries,
  orderOverlayEntries,
  reconcileOverlayOrder,
  normalizeBounds,
  recordBooleanEqual,
  recordNumberEqual,
  removeOverlayLayers,
  setPlaceLabelsVisible,
} from './map-preview-rendering';
import {
  GeographicBounds,
  isRasterOverlay,
  observeRasterOverlay,
  RasterVisibilityObservation,
} from './raster-visibility';
import { isFiniteNumber } from '../core/type-guards';

export type MapRenderState = 'preparing' | 'ready' | 'failed';

export interface MapRenderIdentity {
  runId: string;
  runVersion: number;
  mapSessionId: string;
  collectionRevision: number;
}

const OVERLAY_SOURCE_PREFIX = 'overlay-source-';

// `idle` needs every tile settled and can stay silent on slow tiles, so a
// candidate that is applied and verifiable is acknowledged after this grace.
const RENDER_WATCHDOG_MS = 30_000;
const SAMPLE_CACHE_LIMIT = 256;

interface HoverTarget {
  point: MapMouseEvent['point'];
  lng: number;
  lat: number;
}
const IDLE_FALLBACK_GRACE_MS = 3_000;
const IDLE_FALLBACK_POLL_MS = 1_000;

const isMetadataOnlyOverlay = (overlay: OverlayEntry): boolean => (
  String(overlay.render?.rendering_mode || overlay.rendering_mode || overlay.type || '')
    .toLowerCase() === 'metadata-only' || overlay.type === 'metadata-only'
);

const stringArrayEqual = (left: readonly string[], right: readonly string[]): boolean => (
  left.length === right.length && left.every((value, index) => value === right[index])
);

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
  failureCode?: string;
  failureStage?: string;
  failureSummary?: string;
}

export interface MapCapturePayload {
  dataUrl: string;
  mimeType: string;
  width: number;
  height: number;
  viewportBounds?: [number, number, number, number];
}

@Component({
  selector: 'app-map-preview',
  standalone: true,
  imports: [OverlayControlsComponent, OverlayLegendComponent],
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
  @Input() initialOverlayOrder: string[] = [];
  @Input() availableBasemaps: CapabilityDescriptor[] = [];
  @Input() renderIdentity?: MapRenderIdentity;
  @Input() toolsOpen = false;
  @Input() layersOpen = false;
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
  overlayOrder: string[] = [];
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

  /**
   * A basemap switch rebuilds the map, which would orphan a candidate the
   * agent is waiting on; lock the selector until that render settles.
   */
  get basemapLocked(): boolean {
    return this.mapPreparing || this.awaitingBackendAcknowledgment;
  }
  private awaitingCandidateMap: Map | null = null;
  private destroyed = false;
  private candidateGeneration = 0;
  private renderWatchdog?: number;
  private rasterEvidenceMap: Map | null = null;
  private loadedSourceIds = new Set<string>();
  private rasterVisibilityEvidence: Record<string, RasterVisibilityObservation> = {};
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
  /** One-line value readout for the legend card of the overlay under the resting pointer. */
  readonly hoverReadout = signal<{ overlayId: string; text: string } | null>(null);
  private hoverMap: Map | null = null;
  private hoverAbort?: AbortController;
  private readonly sampleCache = new globalThis.Map<string, OverlaySampleResponse['sample']>();
  private readonly unsampleableCapabilities = new Set<string>();
  private readonly hoverScheduler = new HoverReadoutScheduler<HoverTarget>(
    HOVER_READOUT_DELAY_MS,
    () => this.hoverMap?.isMoving() ?? true,
    (target) => this.readHoverValue(target),
    () => this.abortHoverSample(),
  );
  private readonly onHoverMove = (event: MapMouseEvent): void => {
    const original = event.originalEvent as (MouseEvent & { sourceCapabilities?: { firesTouchEvents?: boolean } }) | undefined;
    if (!this.toolsOpen || original?.sourceCapabilities?.firesTouchEvents) {
      this.hoverScheduler.stop();
      return;
    }
    const lngLat = event.lngLat.wrap();
    const buttons = original?.buttons ?? 0;
    this.hoverScheduler.move({ point: event.point, lng: lngLat.lng, lat: lngLat.lat }, buttons);
    if (buttons !== 0) {
      // A drag moves the map under the pointer; the last reading no longer applies.
      this.hoverReadout.set(null);
    }
  };
  private readonly onHoverOut = (): void => {
    this.hoverScheduler.stop();
    this.hoverReadout.set(null);
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
    return orderOverlayEntries(mapSessionOverlayEntries(this.mapSession), this.overlayOrder);
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
      this.removeCandidateMap(pending.map);
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

  get legendEntries(): Array<{ id: string; label: string; mode: string; legend?: OverlayLegend }> {
    return this.overlays.map((overlay) => ({
      id: overlay.id,
      label: overlay.label,
      mode: String(overlay.rendering_mode || overlay.type || 'overlay'),
      legend: overlay.legend,
    }));
  }

  hoverReadoutFor(overlayId: string): string | null {
    const readout = this.hoverReadout();
    return readout?.overlayId === overlayId ? readout.text : null;
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
      this.rebuildOverlayStateFromSession(true);
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
    const payloadChanged = Boolean(changes['payload']);
    const sessionChanged = Boolean(payloadChanged || changes['renderIdentity']);
    const overlayStateChanged = Boolean(
      changes['initialOverlayVisibility']
      || changes['initialOverlayOpacity']
      || changes['initialOverlayOrder']
    );
    if (sessionChanged || overlayStateChanged) {
      const hadMapSession = Boolean(this.mapSession);
      if (payloadChanged) {
        this.syncSessionFromPayload();
      }
      const previousSession = (changes['payload']?.previousValue as SearchResponsePayload | undefined)?.map_session;
      const currentSession = this.payload?.map_session;
      const sameSessionRevision = Boolean(previousSession && currentSession
        && previousSession.session_id === currentSession.session_id
        && previousSession.overlay_collection?.revision === currentSession.overlay_collection?.revision);
      const restoringInitialSession = payloadChanged && !hadMapSession && Boolean(this.mapSession);
      this.rebuildOverlayStateFromSession(!payloadChanged || restoringInitialSession || sameSessionRevision);
      if (sessionChanged) {
        this.recreateMapIfPossible();
      }
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

  setOverlayOrder(order: string[]): void {
    const nextOrder = reconcileOverlayOrder(mapSessionOverlayEntries(this.mapSession), order);
    if (stringArrayEqual(this.overlayOrder, nextOrder)) {
      return;
    }
    this.overlayOrder = nextOrder;
    this.emitOverlayState();
    if (this.mapRef) {
      applyOverlayLayerOrder(this.mapRef, this.overlays, this.overlayOrder);
    }
  }

  onOverlayOrderChange(order: string[]): void {
    this.setOverlayOrder(order);
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

  private rebuildOverlayStateFromSession(preferInitialState = false): void {
    const sourceOverlays = mapSessionOverlayEntries(this.mapSession);
    const overlays = orderOverlayEntries(sourceOverlays, this.overlayOrder);
    const overlayIds = new Set(overlays.map((overlay) => overlay.id));
    const staleVisibilityKeys = Object.keys(this.initialOverlayVisibility).filter((key) => !overlayIds.has(key));
    const staleOpacityKeys = Object.keys(this.initialOverlayOpacity).filter((key) => !overlayIds.has(key));
    const staleOrderKeys = this.initialOverlayOrder.filter((key) => !overlayIds.has(key));
    const staleIds = new Set([...staleVisibilityKeys, ...staleOpacityKeys, ...staleOrderKeys]);

    this.restoreNotice = staleIds.size > 0
      ? `Some saved overlay preferences could not be restored (${staleIds.size} removed or unknown overlay id${staleIds.size === 1 ? '' : 's'}).`
      : '';

    const nextVisibility: Record<string, boolean> = {};
    overlays.forEach((overlay) => {
      // Canonical overlay instances always include visibility. Persisted
      // preferences override the backend value only when restoring the page.
      nextVisibility[overlay.id] =
        preferInitialState && typeof this.initialOverlayVisibility[overlay.id] === 'boolean'
          ? this.initialOverlayVisibility[overlay.id]
          : overlay.visible ?? true;
    });
    this.overlayVisibility = recordBooleanEqual(this.overlayVisibility, nextVisibility) ? this.overlayVisibility : nextVisibility;

    const nextOpacity: Record<string, number> = {};
    overlays.forEach((overlay) => {
      const fallback = typeof overlay.default_opacity === 'number' ? overlay.default_opacity : DEFAULT_OVERLAY_OPACITY;
      const initialOpacity = this.initialOverlayOpacity[overlay.id];
      nextOpacity[overlay.id] = preferInitialState && typeof initialOpacity === 'number'
        ? initialOpacity
        : fallback;
    });
    this.overlayOpacity = recordNumberEqual(this.overlayOpacity, nextOpacity) ? this.overlayOpacity : nextOpacity;

    const nextOrder = reconcileOverlayOrder(
      sourceOverlays,
      preferInitialState ? this.initialOverlayOrder : this.overlayOrder,
    );
    this.overlayOrder = stringArrayEqual(this.overlayOrder, nextOrder) ? this.overlayOrder : nextOrder;

    if (this.mapSession) {
      this.emitOverlayState();
    }
  }

  private emitOverlayState(): void {
    this.overlayStateChange.emit({
      overlayVisibility: this.overlayVisibility,
      overlayOpacity: this.overlayOpacity,
      overlayOrder: this.overlayOrder,
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
      this.loadedSourceIds.clear();
      this.overlayRenderStatuses = addOverlayLayers(this.mapRef, this.mapSession);
      this.bindInspectionListeners(this.mapRef);
      this.applyOverlayStateToMap();
      const currentMap = this.mapRef;
      const finishInPlaceUpdate = (): void => {
        if (this.destroyed || this.mapRef !== currentMap) {
          return;
        }
        this.emitRenderState('ready');
        this.changeDetector.detectChanges();
      };
      if (this.hasRasterVisibilityProbe()) {
        void this.collectRasterVisibilityEvidence(currentMap).finally(finishInPlaceUpdate);
      } else {
        finishInPlaceUpdate();
      }
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
      // Preserve the drawing buffer so ``toDataURL``/``toBlob`` reliably
      // captures the rendered canvas for vision inspection.
      preserveDrawingBuffer: true,
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

    const loadedSources = new Set<string>();
    this.loadedSourceIds = loadedSources;
    let styleLoaded = false;
    let committing = false;
    let watchdogExtended = false;
    let fallbackTimer: number | undefined;
    const stopFallback = (): void => {
      if (fallbackTimer !== undefined) {
        window.clearInterval(fallbackTimer);
        fallbackTimer = undefined;
      }
    };
    const armWatchdog = (): void => {
      this.clearRenderWatchdog();
      this.renderWatchdog = window.setTimeout(() => {
        if (!isCurrentCandidate()) {
          return;
        }
        const checks = this.candidateChecks(candidate, styleLoaded);
        const onlyTilesPending = checks['style_loaded'] && checks['sources_present']
          && checks['layers_present'] && checks['viewport_valid'] && !checks['tiles_settled'];
        if (onlyTilesPending && !watchdogExtended) {
          // Tiles are still in flight but the candidate is otherwise intact:
          // extend once, within the backend render-ack budget.
          watchdogExtended = true;
          armWatchdog();
          return;
        }
        candidateSettled = true;
        this.mapPreparing = false;
        stopFallback();
        clearCandidate();
        if (!this.destroyed) {
          // Report the candidate's real per-check state before tearing it down.
          this.emitRenderState('failed', 'render_timeout', candidateIdentity, { map: candidate, checks });
        }
        this.abandonCandidate(candidate);
        this.removeCandidateContainer(candidateContainer, originalContainer);
        if (!this.destroyed) {
          this.changeDetector.detectChanges();
        }
      }, RENDER_WATCHDOG_MS);
    };
    armWatchdog();

    candidate.on('sourcedata', (event: unknown) => {
      const { sourceId, isSourceLoaded, tile } = (event ?? {}) as {
        sourceId?: string;
        isSourceLoaded?: boolean;
        tile?: unknown;
      };
      // Delivery evidence only; readiness comes from `map.isSourceLoaded`.
      if (sourceId?.startsWith(OVERLAY_SOURCE_PREFIX) && (isSourceLoaded || tile)) {
        loadedSources.add(sourceId);
      }
    });

    candidate.on('error', (event: unknown) => {
      if (!isCurrentCandidate()) {
        return;
      }
      const { error, sourceId } = (event ?? {}) as { error?: unknown; sourceId?: string };
      // A failed basemap tile leaves the rest of the map usable; only an
      // overlay source or a style-level failure invalidates the candidate.
      if (error && (!sourceId || sourceId.startsWith(OVERLAY_SOURCE_PREFIX))) {
        candidateSettled = true;
        this.mapPreparing = false;
        stopFallback();
        clearCandidate();
        this.abandonCandidate(candidate);
        this.removeCandidateContainer(candidateContainer, originalContainer);
        if (!this.destroyed) {
          this.emitRenderState('failed', this.safeRenderError(error, sourceId), candidateIdentity);
        }
      }
    });

candidate.on('load', () => {
      if (!isCurrentCandidate()) {
        return;
      }
      this.resizeMapToContainer(candidate);
      this.overlayRenderStatuses = addOverlayLayers(candidate, this.mapSession);
      this.bindInspectionListeners(candidate);
      const bounds = normalizeBounds(this.mapSession?.bounds);
      if (bounds) {
        const defaultMaxZoom = nextBasemapId === 'esri_world_imagery'
          ? DEFAULT_SATELLITE_MAP_FIT_MAX_ZOOM
          : DEFAULT_MAP_FIT_MAX_ZOOM;
        const maxZoom = this.fitMaxZoom(defaultMaxZoom);
        candidate.fitBounds(bounds, { padding: this.fitPadding(candidate), duration: 0, maxZoom });
        const rasterMinZoom = this.requiredRasterMinZoom();
        if (
          rasterMinZoom !== null
          && typeof candidate.getZoom === 'function'
          && typeof candidate.setZoom === 'function'
          && candidate.getZoom() < rasterMinZoom
        ) {
          // Scale-dependent raster overlays (for example FEMA NFHL layer 28)
          // only draw above their declared minimum zoom. Present them at a
          // visible zoom so the acknowledged map contains real pixels.
          candidate.setZoom(rasterMinZoom, { duration: 0 });
        }
      }
      if (!this.hasRenderableCanvas(candidate, candidateContainer)) {
        candidateSettled = true;
        this.mapPreparing = false;
        stopFallback();
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
      styleLoaded = true;
      // `load` precedes the requests initiated by addOverlayLayers. Keep the
      // candidate and its error handler alive until those sources settle.
      const commitCandidate = (): void => {
        if (!isCurrentCandidate() || committing) {
          return;
        }
        committing = true;
        stopFallback();
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
        const finishCandidate = (): void => {
          if (!isCurrentCandidate()) {
            return;
          }
          candidateSettled = true;
          clearCandidate();
          this.emitRenderState('ready', undefined, candidateIdentity);
          this.changeDetector.detectChanges();
          this.scheduleMapResize();
        };
        if (this.hasRasterVisibilityProbe()) {
          void this.collectRasterVisibilityEvidence(candidate).finally(finishCandidate);
        } else {
          finishCandidate();
        }
      };
      candidate.on('idle', commitCandidate);
      // Fallback when `idle` never fires: acknowledge once the applied
      // candidate verifies; a missing source or layer never qualifies.
      let fallbackTicks = 0;
      fallbackTimer = window.setInterval(() => {
        if (!isCurrentCandidate() || committing) {
          stopFallback();
          return;
        }
        fallbackTicks += 1;
        if (fallbackTicks * IDLE_FALLBACK_POLL_MS < IDLE_FALLBACK_GRACE_MS) {
          return;
        }
        if (Object.values(this.candidateChecks(candidate, styleLoaded)).every(Boolean)) {
          commitCandidate();
        }
      }, IDLE_FALLBACK_POLL_MS);
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
      maps.forEach((map) => this.resizeMapToContainer(map));
    });
  }

  // MapLibre can permanently clamp its canvas to 0x0 when resize() runs before
  // the WebGL drawing buffer has caught up, so only resize when the size changed.
  private resizeMapToContainer(map: Map): void {
    const container = map.getContainer?.();
    const canvas = map.getCanvas?.();
    if (
      container
      && canvas
      && canvas.width > 0
      && canvas.clientWidth === container.clientWidth
      && canvas.clientHeight === container.clientHeight
    ) {
      return;
    }
    map.resize();
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

  /** Remove a candidate exactly once; it may already be the committed `mapRef`. */
  private removeCandidateMap(map: Map): void {
    this.unbindInspectionListenersForMap(map);
    map.remove();
    if (this.mapRef === map) {
      this.mapRef = null;
    }
  }

  /** Drop a failed candidate and, if it was committed, restore the previous map. */
  private abandonCandidate(candidate: Map): void {
    const committed = this.mapRef === candidate;
    this.removeCandidateMap(candidate);
    if (committed && !this.destroyed) {
      this.rejectRenderedCandidate();
    }
  }

  private removeCandidateContainer(candidate: HTMLDivElement, original: HTMLDivElement): void {
    if (candidate !== original) {
      candidate.remove();
    }
  }

  /**
   * Capture the currently rendered map canvas as a JPEG data URL.
   *
   * Returns null when no map is available or the canvas cannot be serialized.
   * The capture is synchronous (preserveDrawingBuffer keeps the WebGL buffer
   * readable) so it can be posted before the render acknowledgment.
   */
  captureCurrentMap(maxDimension = 1024): MapCapturePayload | null {
    const map = this.mapRef;
    if (!map) {
      return null;
    }
    const canvas = (map as unknown as { getCanvas?: () => HTMLCanvasElement }).getCanvas?.();
    if (!canvas || canvas.width <= 0 || canvas.height <= 0) {
      return null;
    }
    try {
      const scale = Math.min(1, maxDimension / Math.max(canvas.width, canvas.height));
      let source: HTMLCanvasElement = canvas;
      if (scale < 1) {
        const scaled = document.createElement('canvas');
        scaled.width = Math.max(1, Math.round(canvas.width * scale));
        scaled.height = Math.max(1, Math.round(canvas.height * scale));
        const context = scaled.getContext('2d');
        if (context) {
          context.drawImage(canvas, 0, 0, scaled.width, scaled.height);
          source = scaled;
        }
      }
      const mimeType = 'image/jpeg';
      const dataUrl = source.toDataURL(mimeType, 0.7);
      const evidence = this.renderEvidence('ready');
      return {
        dataUrl,
        mimeType,
        width: source.width,
        height: source.height,
        viewportBounds: evidence.viewportBounds,
      };
    } catch {
      return null;
    }
  }

  /**
   * The view the user currently sees, sent with each request so the agent
   * can answer about "this area" and describe the map as it is displayed.
   */
  currentView(): ClientMapView | null {
    const map = this.mapRef;
    // Unit-test doubles may not implement the camera API.
    if (!map || typeof map.getBounds !== 'function' || typeof map.getCenter !== 'function') {
      return null;
    }
    const bounds = map.getBounds();
    const center = map.getCenter();
    const clampLongitude = (value: number): number => Math.max(-180, Math.min(180, value));
    const clampLatitude = (value: number): number => Math.max(-90, Math.min(90, value));
    const view: [number, number, number, number] = [
      clampLongitude(bounds.getWest()),
      clampLatitude(bounds.getSouth()),
      clampLongitude(bounds.getEast()),
      clampLatitude(bounds.getNorth()),
    ];
    if (!view.every(Number.isFinite) || view[0] >= view[2] || view[1] >= view[3]) {
      return null;
    }
    return {
      bounds: view,
      center: [clampLongitude(center.lng), clampLatitude(center.lat)],
      zoom: Math.max(0, Math.min(24, typeof map.getZoom === 'function' ? map.getZoom() : 0)),
      basemap_id: this.activeBasemapId,
      overlays: this.overlays.slice(0, 32).map((overlay) => ({
        instance_id: overlay.id,
        visible: this.overlayVisibility[overlay.id] ?? overlay.visible ?? true,
        opacity: this.overlayOpacity[overlay.id] ?? overlay.default_opacity ?? DEFAULT_OVERLAY_OPACITY,
      })),
    };
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
    candidateEvidence?: { map: Map; checks: Record<string, boolean> },
  ): void {
    const sessionId = this.mapSession?.session_id;
    if (sessionId) {
      const evidence = candidateEvidence
        ? this.renderEvidence(state, candidateEvidence.map, candidateEvidence.checks)
        : this.renderEvidence(state);
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
        failureCode: state === 'failed'
          ? (message === 'render_timeout' ? 'render_timeout' : 'render_failed')
          : undefined,
        failureStage: state === 'failed'
          ? (message === 'render_timeout' ? 'watchdog' : 'maplibre')
          : undefined,
        failureSummary: state === 'failed' ? message : undefined,
      });
    }
  }

  private renderEvidence(
    state: MapRenderState,
    evidenceMap: Map | null = this.mapRef,
    checkOverrides: Record<string, boolean> = {},
  ): {
    viewportBounds?: [number, number, number, number];
    checks: Record<string, boolean>;
    overlayResults: Array<Record<string, string | number | boolean | null>>;
  } {
    const map = evidenceMap;
    const viewportBounds = this.validViewportBounds(map);
    const overlayResults = this.overlays.map((overlay) => {
      const layerIds = getOverlayLayerIds(overlay);
      const metadataOnly = isMetadataOnlyOverlay(overlay);
      const mapApi = map as unknown as {
        getLayer?: (id: string) => unknown;
        getSource?: (id: string) => unknown;
        getLayoutProperty?: (id: string, property: string) => unknown;
      } | null;
      // A map being replaced has no style; MapLibre throws instead of answering.
      const layerOf = (id: string): unknown => {
        try {
          return mapApi?.getLayer?.call(map, id);
        } catch {
          return undefined;
        }
      };
      const sourcePresent = (id: string): boolean => {
        try {
          return Boolean(mapApi?.getSource?.call(map, id));
        } catch {
          return false;
        }
      };
      const layerRecords = metadataOnly
        ? []
        : layerIds
          .map(layerOf)
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
        const layer = layerOf(id) as Record<string, unknown> | undefined;
        if (!layer) {
          return false;
        }
        let visibility: unknown;
        try {
          visibility = mapApi?.getLayoutProperty?.call(map, id, 'visibility');
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
      const isRaster = isRasterOverlay(overlay);
      const rasterEvidence = isRaster && this.rasterEvidenceMap === map
        ? this.rasterVisibilityEvidence[overlay.id]
        : undefined;
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
            Boolean(layerOf(id))
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
      const loaded = (status === 'loaded' || status === 'no-results' || metadataOnly)
        && (!isRaster || rasterEvidence?.sourceLoaded !== false);
      return {
        overlay_id: overlay.id,
        capability_id: overlay.capability_id || overlay.id,
        source_present: metadataOnly || sourcePresent(`overlay-source-${overlay.id}`),
        layer_present: present && styleValid && zoomRangeValid,
        loaded,
        metadata_only: metadataOnly,
        visibility_matches: metadataOnly || visible === desiredVisible,
        style_valid: styleValid,
        zoom_range_valid: zoomRangeValid,
        rendered_feature_count: renderedFeatureCount,
        result_visible: isRaster
          ? rasterEvidence?.resultVisible ?? null
          : renderedFeatureCount === null ? null : renderedFeatureCount > 0,
        ...(isRaster
          ? {
            raster_source_loaded: rasterEvidence?.sourceLoaded ?? null,
            raster_tile_intersects_viewport: rasterEvidence?.tileIntersectsViewport ?? null,
            raster_zoom_supported: rasterEvidence?.zoomSupported ?? null,
            raster_nontransparent_pixel_count: rasterEvidence?.nonTransparentPixelCount ?? null,
            raster_tile_z: rasterEvidence?.tile?.z ?? null,
            raster_tile_x: rasterEvidence?.tile?.x ?? null,
            raster_tile_y: rasterEvidence?.tile?.y ?? null,
          }
          : {}),
        failure_code: status === 'failed'
          ? 'overlay_render_failed'
          : rasterEvidence?.failureCode || null,
      };
    });
    const required = overlayResults.filter((item) => item.metadata_only !== true);
    const checks = {
      required_sources_loaded: state === 'ready' && required.every((item) => item.loaded === true),
      required_layers_present: state === 'ready' && required.every((item) => item.layer_present === true),
      viewport_valid: state === 'ready' && Boolean(viewportBounds),
      ...this.targetsInViewCheck(map),
      ...checkOverrides,
    };
    return { viewportBounds, checks, overlayResults };
  }

  /** Pixel rect of the map and the overlay insets, in container-local coordinates. */
  private measureFrame(map: Map | null): { container: FrameRect; insets: FrameInsets; padding: FrameInsets } | null {
    const element = (map as unknown as { getContainer?: () => HTMLElement } | null)?.getContainer?.();
    if (!element || typeof element.getBoundingClientRect !== 'function') {
      return null;
    }
    const box = element.getBoundingClientRect();
    if (box.width <= 0 || box.height <= 0) {
      return null;
    }
    const scope = this.hostElement.nativeElement.closest('[data-map-frame]') ?? this.hostElement.nativeElement;
    const obstructions = Array.from(scope.querySelectorAll('[data-map-obstruction]'))
      .map((node) => node.getBoundingClientRect())
      .map((rect): FrameRect => ({
        left: rect.left - box.left,
        top: rect.top - box.top,
        right: rect.right - box.left,
        bottom: rect.bottom - box.top,
      }));
    const container: FrameRect = { left: 0, top: 0, right: box.width, bottom: box.height };
    return {
      container,
      insets: computeFrameInsets(container, obstructions),
      padding: computeFitPadding(container, obstructions),
    };
  }

  private fitPadding(map: Map): FrameInsets | number {
    return this.measureFrame(map)?.padding ?? MARKER_FIT_PADDING_PX;
  }

  /** Whether every rendered target feature lies in the unobstructed viewport. */
  private targetsInViewCheck(map: Map | null): Record<string, boolean> {
    const frame = this.measureFrame(map);
    const project = (map as unknown as {
      project?: (lngLat: [number, number]) => { x: number; y: number };
    } | null)?.project;
    if (!frame || !map || typeof project !== 'function') {
      return {};
    }
    const anchors = this.overlays
      .filter((overlay) => !isMetadataOnlyOverlay(overlay) && isGeoJsonOverlay(overlay))
      .flatMap((overlay) => featureAnchors(overlay.data));
    if (!anchors.length) {
      return {};
    }
    return {
      targets_in_view: allTargetsInView(
        anchors.map((anchor) => project.call(map, anchor)),
        frame.container,
        frame.insets,
      ),
    };
  }

  private validViewportBounds(map: Map | null): [number, number, number, number] | undefined {
    const session = this.mapSession;
    const rawBounds = this.readMapBounds(map) ?? session?.bounds ?? session?.viewport?.bbox;
    if (!Array.isArray(rawBounds)
      || rawBounds.length !== 4
      || !rawBounds.every(isFiniteNumber)) {
      return undefined;
    }
    const [west, rawSouth, east, rawNorth] = rawBounds;
    const south = Math.max(-90, rawSouth);
    const north = Math.min(90, rawNorth);
    if (south > north) {
      return undefined;
    }
    // MapLibre reports unwrapped longitudes for world-sized or panned views:
    // a full-turn span is the whole world, otherwise wrap into [-180, 180]
    // where west > east denotes an antimeridian crossing.
    if (west <= east && east - west >= 360) {
      return [-180, south, 180, north];
    }
    const wrap = (longitude: number): number => (
      longitude >= -180 && longitude <= 180 ? longitude : ((longitude + 180) % 360 + 360) % 360 - 180
    );
    return [wrap(west), south, wrap(east), north];
  }

  /**
   * Verifies an applied candidate without relying on MapLibre's `idle`, which
   * never fires while a tile stays in flight. `tiles_settled` is true (not
   * "pending") so that a false value reads as a failed check in the backend.
   */
  private candidateChecks(map: Map, styleLoaded: boolean): Record<string, boolean> {
    const mapApi = map as unknown as {
      getLayer?: (id: string) => unknown;
      getSource?: (id: string) => unknown;
      isSourceLoaded?: (id: string) => boolean;
    };
    const required = this.overlays.filter((overlay) => !isMetadataOnlyOverlay(overlay));
    const sourceIdOf = (overlay: OverlayEntry): string => `${OVERLAY_SOURCE_PREFIX}${overlay.id}`;
    // A delivered first tile (`loadedSourceIds`) is not enough: every tile the
    // source requires must have loaded.
    const sourceDelivered = (sourceId: string): boolean => {
      try {
        return Boolean(mapApi.isSourceLoaded?.call(map, sourceId));
      } catch {
        return false;
      }
    };
    return {
      style_loaded: styleLoaded,
      sources_present: required.every((overlay) => Boolean(mapApi.getSource?.call(map, sourceIdOf(overlay)))),
      layers_present: required.every((overlay) => (
        getOverlayLayerIds(overlay).some((id) => Boolean(mapApi.getLayer?.call(map, id)))
      )),
      viewport_valid: Boolean(this.validViewportBounds(map)),
      tiles_settled: required.filter(isRasterOverlay).every((overlay) => sourceDelivered(sourceIdOf(overlay))),
    };
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

  private async collectRasterVisibilityEvidence(map: Map): Promise<void> {
    const mapApi = map as unknown as {
      getCenter?: () => { lng?: unknown; lat?: unknown };
      getLayer?: (id: string) => unknown;
      getLayoutProperty?: (id: string, property: string) => unknown;
      getPaintProperty?: (id: string, property: string) => unknown;
      getSource?: (id: string) => unknown;
      getZoom?: () => unknown;
      isSourceLoaded?: (id: string) => boolean;
    };
    const rawBounds = this.readMapBounds(map) ?? this.mapSession?.bounds ?? this.mapSession?.viewport?.bbox;
    const viewportBounds: GeographicBounds | undefined = Array.isArray(rawBounds)
      && rawBounds.length === 4
      && rawBounds.every(isFiniteNumber)
      ? rawBounds as GeographicBounds
      : undefined;
    const rawCenter = typeof mapApi.getCenter === 'function' ? mapApi.getCenter.call(map) : undefined;
    const center: [number, number] | undefined = isFiniteNumber(rawCenter?.lng)
      && isFiniteNumber(rawCenter?.lat)
      ? [Number(rawCenter?.lng), Number(rawCenter?.lat)]
      : undefined;
    const rawZoom = typeof mapApi.getZoom === 'function' ? mapApi.getZoom.call(map) : undefined;
    const zoom = isFiniteNumber(rawZoom) ? Number(rawZoom) : undefined;
    const rasterOverlays = this.overlays.filter(isRasterOverlay);
    const observations = await Promise.all(rasterOverlays.map(async (overlay) => {
      const layerId = getOverlayLayerIds(overlay)[0];
      const sourceId = `overlay-source-${overlay.id}`;
      const layer = typeof mapApi.getLayer === 'function'
        ? mapApi.getLayer.call(map, layerId)
        : undefined;
      const sourcePresent = typeof mapApi.getSource === 'function'
        && Boolean(mapApi.getSource.call(map, sourceId));
      const layerPresent = Boolean(layer);
      let sourceLoaded: boolean | null = null;
      if (sourcePresent && typeof mapApi.isSourceLoaded === 'function') {
        try {
          sourceLoaded = Boolean(mapApi.isSourceLoaded.call(map, sourceId));
        } catch {
          sourceLoaded = null;
        }
      }
      let visibility: unknown;
      try {
        visibility = mapApi.getLayoutProperty?.call(map, layerId, 'visibility');
      } catch {
        visibility = undefined;
      }
      if (visibility === undefined && layer && typeof layer === 'object') {
        const layout = (layer as Record<string, unknown>)['layout'];
        visibility = layout && typeof layout === 'object'
          ? (layout as Record<string, unknown>)['visibility']
          : undefined;
      }
      let opacity = this.overlayOpacity[overlay.id]
        ?? overlay.default_opacity
        ?? DEFAULT_OVERLAY_OPACITY;
      try {
        const paintOpacity = mapApi.getPaintProperty?.call(map, layerId, 'raster-opacity');
        if (isFiniteNumber(paintOpacity)) {
          opacity = Number(paintOpacity);
        }
      } catch {
        // Keep the persisted/default opacity when MapLibre cannot expose it.
      }
      const observation = await observeRasterOverlay(overlay, {
        viewportBounds,
        zoom,
        center,
        sourcePresent,
        layerPresent,
        sourceLoaded,
        layerVisible: visibility !== 'none',
        opacity,
      });
      return [overlay.id, observation] as const;
    }));
    if (this.mapRef !== map && this.pendingCandidate?.map !== map) {
      return;
    }
    this.rasterEvidenceMap = map;
    this.rasterVisibilityEvidence = Object.fromEntries(observations);
  }

  private hasRasterVisibilityProbe(): boolean {
    return this.overlays.some((overlay) => (
      isRasterOverlay(overlay) && Boolean(buildRasterOverlayTiles(overlay)?.[0])
    ));
  }

private fitMaxZoom(defaultMaxZoom: number): number {
    return this.overlays.reduce((maxZoom, overlay) => (
      isFiniteNumber(overlay.fit_max_zoom)
        ? Math.min(maxZoom, overlay.fit_max_zoom)
        : maxZoom
    ), defaultMaxZoom);
  }

  private requiredRasterMinZoom(): number | null {
    return this.overlays.reduce<number | null>((minZoom, overlay) => {
      if (!isRasterOverlay(overlay) || !this.isRequiredOverlay(overlay)) {
        return minZoom;
      }
      const overlayMinZoom = (
        overlay.render?.min_zoom
        ?? overlay.min_zoom
      );
      if (!isFiniteNumber(overlayMinZoom)) {
        return minZoom;
      }
      return minZoom === null ? Math.ceil(overlayMinZoom) : Math.max(minZoom, Math.ceil(overlayMinZoom));
    }, null);
  }

  private isRequiredOverlay(overlay: OverlayEntry): boolean {
    if (overlay.visible === false) {
      return false;
    }
    if (this.mapSession?.overlay_collection) {
      const instance = this.mapSession.overlay_collection.instances.find(
        (candidate) => (
          candidate.instance_id === overlay.id
          || candidate.capability_id === overlay.capability_id
        ),
      );
      if (instance && instance.visible === false) {
        return false;
      }
    }
    return true;
  }

  private safeRenderError(error: unknown, sourceId?: string): string {
    const message = error instanceof Error ? error.message : '';
    if (/\b(401|403)\b/.test(message)) {
      return 'Map layer access was denied. Check the provider credentials in Settings under Geospatial Access.';
    }
    // Name the failing layer and status so the agent can revise that layer
    // instead of guessing which part of the map failed.
    const overlayId = sourceId?.startsWith(OVERLAY_SOURCE_PREFIX)
      ? sourceId.slice(OVERLAY_SOURCE_PREFIX.length)
      : undefined;
    if (overlayId) {
      const label = this.overlays.find((overlay) => overlay.id === overlayId)?.label || overlayId;
      const status = /\b([45]\d{2})\b/.exec(message)?.[1];
      return `The map layer "${label}" could not be loaded${status ? ` (HTTP ${status})` : ''}. Check provider availability or choose another source.`;
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
      setPlaceLabelsVisible(map, overlay.id, visible);
      if (overlay.value_encoding) {
        // Encoded layers are heatmaps, circles or (for areas) fills.
        const encodedType = map.getLayer(layerIds[0])?.type;
        if (encodedType === 'fill') {
          map.setPaintProperty(layerIds[0], 'fill-opacity', Math.min(opacityValue, 0.7));
        } else if (encodedType === 'heatmap' || encodedType === 'circle') {
          map.setPaintProperty(layerIds[0], `${encodedType}-opacity`, opacityValue);
        }
        if (overlay.value_encoding.mode === 'heatmap' && map.getLayer(layerIds[1])) {
          map.setPaintProperty(layerIds[1], 'circle-opacity', opacityValue);
        }
      } else if (overlay.type === 'point-insight') {
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
    applyOverlayLayerOrder(map, overlays, this.overlayOrder);
  }

  private destroyMap(): void {
    this.unbindHoverListeners();
    this.mapPreparing = false;
    this.clearRenderWatchdog();
    this.candidateGeneration += 1;
    const pendingCandidate = this.pendingCandidate;
    this.pendingCandidate = undefined;
    if (pendingCandidate) {
      this.removeCandidateMap(pendingCandidate.map);
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
    this.rasterEvidenceMap = null;
    this.rasterVisibilityEvidence = {};
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
      if (!['geojson', 'arcgis-geojson', 'clustered-points', 'choropleth', 'camera-points', 'place-markers'].includes(renderingMode)) {
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
    this.bindHoverListeners(map);
  }

  private unbindInspectionListeners(): void {
    this.inspectionListeners.forEach(({ map, layerId, handler }) => {
      this.unregisterLayerClickListener(map, layerId, handler);
    });
    this.inspectionListeners = [];
  }

  private unbindInspectionListenersForMap(target: Map): void {
    if (this.hoverMap === target) {
      this.unbindHoverListeners();
    }
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

  /** A single map-level hover listener pair follows the map that owns the inspection listeners. */
  private bindHoverListeners(map: Map): void {
    if (this.hoverMap === map) {
      return;
    }
    this.unbindHoverListeners();
    if (typeof map.on !== 'function') {
      return;
    }
    map.on('mousemove', this.onHoverMove);
    map.on('mouseout', this.onHoverOut);
    this.hoverMap = map;
  }

  private unbindHoverListeners(): void {
    this.hoverScheduler.stop();
    this.hoverReadout.set(null);
    if (!this.hoverMap) {
      return;
    }
    if (typeof this.hoverMap.off === 'function') {
      this.hoverMap.off('mousemove', this.onHoverMove);
      this.hoverMap.off('mouseout', this.onHoverOut);
    }
    this.hoverMap = null;
  }

  private abortHoverSample(): void {
    this.hoverAbort?.abort();
    this.hoverAbort = undefined;
  }

  /** Read the value of the topmost visible overlay with a legend under the resting pointer. */
  private readHoverValue(target: HoverTarget): void {
    const map = this.hoverMap;
    if (!map || this.destroyed) {
      return;
    }
    for (const overlay of this.overlays) {
      const legend = overlay.legend;
      if (!legend || !(this.overlayVisibility[overlay.id] ?? overlay.visible ?? true)) {
        continue;
      }
      const layerIds = getOverlayLayerIds(overlay).filter((layerId) => map.getLayer(layerId));
      if (!layerIds.length) {
        continue;
      }
      const encoding = overlay.value_encoding;
      if (encoding) {
        const queryLayers = layerIds.filter((layerId) => !layerId.endsWith('-heatmap'));
        const feature = queryLayers.length
          ? map.queryRenderedFeatures(target.point, { layers: queryLayers })[0]
          : undefined;
        const raw: unknown = feature?.properties?.[encoding.field];
        const value = typeof raw === 'number' ? raw : typeof raw === 'string' && raw.trim() ? Number(raw) : Number.NaN;
        if (!Number.isFinite(value)) {
          continue;
        }
        this.hoverReadout.set({
          overlayId: overlay.id,
          text: formatHoverReadout({ kind: 'continuous', value, label: '', units: legend.units }, target.lng, target.lat),
        });
        return;
      }
      const capabilityId = overlay.capability_id;
      const proxied = buildRasterOverlayTiles(overlay)?.some((url) => url.includes('/geospatial/tiles/'));
      if (!capabilityId || !proxied || this.unsampleableCapabilities.has(capabilityId)) {
        continue;
      }
      this.sampleRasterOverlay(map, overlay, capabilityId, legend, target);
      return;
    }
    this.hoverReadout.set(null);
  }

  private sampleRasterOverlay(
    map: Map,
    overlay: OverlayEntry,
    capabilityId: string,
    legend: OverlayLegend,
    target: HoverTarget,
  ): void {
    const z = Math.max(0, Math.min(30, Math.round(map.getZoom())));
    const time = overlay.render?.time || overlay.render?.default_time || overlay.time || overlay.default_time || undefined;
    const key = sampleCacheKey(capabilityId, z, target.lng, target.lat, time);
    const show = (sample: OverlaySampleResponse['sample']): void => {
      this.hoverReadout.set({
        overlayId: overlay.id,
        text: formatHoverReadout(sample && { ...sample, units: sample.units ?? legend.units }, target.lng, target.lat),
      });
    };
    if (this.sampleCache.has(key)) {
      show(this.sampleCache.get(key) ?? null);
      return;
    }
    const controller = new AbortController();
    this.hoverAbort = controller;
    const round = (value: number): number => Math.round(value * 1e5) / 1e5;
    fetchOverlaySample(capabilityId, { lon: round(target.lng), lat: round(target.lat), z, time }, controller.signal)
      .then((response) => {
        if (controller.signal.aborted || this.destroyed) {
          return;
        }
        if (this.sampleCache.size >= SAMPLE_CACHE_LIMIT) {
          const oldest = this.sampleCache.keys().next().value;
          if (oldest !== undefined) {
            this.sampleCache.delete(oldest);
          }
        }
        this.sampleCache.set(key, response.sample);
        show(response.sample);
      })
      .catch((error: unknown) => {
        if (controller.signal.aborted || this.destroyed) {
          return;
        }
        // 404/422 mean this layer cannot be sampled at all; stop asking.
        if (error instanceof ApiRequestError && (error.status === 404 || error.status === 422)) {
          this.unsampleableCapabilities.add(capabilityId);
        }
        this.hoverReadout.set(null);
      })
      .finally(() => {
        if (this.hoverAbort === controller) {
          this.hoverAbort = undefined;
        }
      });
  }

  private registerLayerClickListener(map: Map, layerId: string, handler: (event: unknown) => void): void {
    map.on('click', layerId, handler as never);
  }

  private unregisterLayerClickListener(map: Map, layerId: string, handler: (event: unknown) => void): void {
    map.off('click', layerId, handler as never);
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

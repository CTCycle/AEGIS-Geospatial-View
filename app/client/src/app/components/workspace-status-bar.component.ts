import { ChangeDetectionStrategy, ChangeDetectorRef, Component, OnDestroy, OnInit } from '@angular/core';

import { AgentReadinessService, AgentReadinessState, INITIAL_AGENT_READINESS_STATE } from '../core/agent-readiness.service';
import { ApiClientService } from '../core/api-client.service';
import { CapabilityStatusInteraction, CapabilityStatusItem, CapabilityStatusListComponent } from './capability-status-list.component';

type SatelliteState = 'checking' | 'available' | 'unavailable';

/** Shell-level status bar shown on pages that do not render the search workspace's own bar. */
@Component({
  selector: 'app-workspace-status-bar',
  standalone: true,
  imports: [CapabilityStatusListComponent],
  template: `
    <app-capability-status-list [items]="items" [nowrap]="true" [interactions]="interactions"></app-capability-status-list>
  `,
  styleUrl: './workspace-status-bar.component.css',
  changeDetection: ChangeDetectionStrategy.Eager,
})
export class WorkspaceStatusBarComponent implements OnInit, OnDestroy {
  readonly interactions: Record<string, CapabilityStatusInteraction> = {
    'Agent model': {
      route: '/settings',
      actionLabel: 'Open agent settings',
      description: 'Review the configured agent model and provider.',
    },
    'Optional Keys': {
      route: '/settings',
      queryParams: { tab: 'geospatial-access' },
      actionLabel: 'Open geospatial access settings',
      description: 'Optional provider credentials are managed in Settings under Geospatial Access.',
    },
  };

  private agentReadiness: AgentReadinessState = INITIAL_AGENT_READINESS_STATE;
  private satellite: SatelliteState = 'checking';
  private isDestroyed = false;

  constructor(
    private readonly agentReadinessService: AgentReadinessService,
    private readonly apiClient: ApiClientService,
    private readonly changeDetectorRef: ChangeDetectorRef,
  ) {}

  get items(): CapabilityStatusItem[] {
    return [
      {
        label: 'Agent model',
        statusLabel: this.agentReadiness.label,
        tone: this.agentReadiness.status === 'active' ? 'ok' : 'warn',
        detail: this.agentReadiness.message,
      },
      this.satelliteItem(),
      { label: 'Optional Keys', statusLabel: 'Optional', tone: 'warn', detail: 'Optional provider credentials are configured in Settings under Geospatial Access.' },
    ];
  }

  ngOnInit(): void {
    void this.load();
  }

  ngOnDestroy(): void {
    this.isDestroyed = true;
  }

  private satelliteItem(): CapabilityStatusItem {
    switch (this.satellite) {
      case 'available':
        return { label: 'Satellite', statusLabel: 'Available', tone: 'ok', detail: 'Select Satellite from the map basemap control.' };
      case 'unavailable':
        return { label: 'Satellite', statusLabel: 'Unavailable', tone: 'error', detail: 'No usable public satellite render descriptor is available.' };
      default:
        return { label: 'Satellite', statusLabel: 'Checking', tone: 'none', detail: 'Loading the live basemap catalog.' };
    }
  }

  private async load(): Promise<void> {
    const [readiness, catalog] = await Promise.allSettled([
      this.agentReadinessService.loadReadiness(),
      this.apiClient.fetchCatalog(),
    ]);
    if (this.isDestroyed) {
      return;
    }
    if (readiness.status === 'fulfilled') {
      this.agentReadiness = readiness.value;
    }
    const imagery = catalog.status === 'fulfilled'
      ? catalog.value.basemaps?.find((item) => item.id === 'esri_world_imagery')
      : undefined;
    this.satellite = imagery?.is_available && imagery.render?.status === 'available' ? 'available' : 'unavailable';
    this.changeDetectorRef.markForCheck();
  }
}

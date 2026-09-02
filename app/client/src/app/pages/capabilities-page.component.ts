import { CommonModule } from '@angular/common';
import { ChangeDetectionStrategy, ChangeDetectorRef, Component, OnInit } from '@angular/core';

import { ApiClientService } from '../core/api-client.service';
import { CapabilityDescriptor, CatalogResponse } from '../core/types';

type CapabilityGroup = 'providers' | 'basemaps' | 'overlays' | 'cameras' | 'transit' | 'tools';

const EMPTY_CATALOG: CatalogResponse = {
  capabilities: [],
  providers: [],
  basemaps: [],
  overlays: [],
  cameras: [],
  transit: [],
  tools: [],
};

@Component({
  selector: 'app-capabilities-page',
  standalone: true,
  imports: [CommonModule],
  templateUrl: './capabilities-page.component.html',
  changeDetection: ChangeDetectionStrategy.Eager,
  styleUrl: './capabilities-page.component.css',
})
export class CapabilitiesPageComponent implements OnInit {
  catalog: CatalogResponse = { ...EMPTY_CATALOG };
  statusText = 'Loading capabilities';
  isLoading = true;
  catalogLoadFailed = false;

  readonly groups: Array<{ id: CapabilityGroup; label: string; description: string }> = [
    { id: 'providers', label: 'Data Providers', description: 'Source systems and access constraints.' },
    { id: 'basemaps', label: 'Map Types', description: 'Base map render styles available to map sessions.' },
    { id: 'overlays', label: 'Layers', description: 'Analytical and contextual map layers.' },
    { id: 'cameras', label: 'Cameras', description: 'Camera networks with preview and official-link policies.' },
    { id: 'transit', label: 'Transit', description: 'GTFS static and realtime mobility feeds.' },
    { id: 'tools', label: 'Direct Tools', description: 'Fast non-map actions the assistant can execute.' },
  ];

  constructor(
    private readonly apiClient: ApiClientService,
    private readonly changeDetector: ChangeDetectorRef,
  ) {}

  async ngOnInit(): Promise<void> {
    try {
      this.catalog = await this.apiClient.fetchCatalog();
      this.statusText = 'Capability catalog loaded';
      this.catalogLoadFailed = false;
    } catch {
      this.catalog = { ...EMPTY_CATALOG };
      this.statusText = 'Capability catalog unavailable.';
      this.catalogLoadFailed = true;
    } finally {
      this.isLoading = false;
      // Eager change detection does not automatically publish the async catalog result.
      this.changeDetector.detectChanges();
    }
  }

  itemsFor(group: CapabilityGroup): CapabilityDescriptor[] {
    return this.catalog[group] ?? [];
  }

  get catalogEntryCount(): number {
    return this.groups.reduce((count, group) => count + this.itemsFor(group.id).length, 0);
  }

  get emptyGroups(): string[] {
    return this.groups
      .filter((group) => this.itemsFor(group.id).length === 0)
      .map((group) => group.label);
  }

  capabilityPurpose(item: CapabilityDescriptor): string {
    return item.description || String(item.metadata?.['human_summary'] ?? 'Manifest-backed geospatial capability.');
  }

  dataSource(item: CapabilityDescriptor): string {
    const source = this.dataSourceUrl(item);
    if (!source) {
      return item.provider;
    }
    try {
      return new URL(source).hostname || 'Official source';
    } catch {
      return 'Official source';
    }
  }

  dataSourceUrl(item: CapabilityDescriptor): string | undefined {
    const candidates = [
      item.metadata?.['docs_url'],
      item.metadata?.['url'],
      item.metadata?.['tile_url'],
      item.metadata?.['url_template'],
      item.metadata?.['tile_url_template'],
    ];
    return candidates.find((candidate): candidate is string => (
      typeof candidate === 'string' && this.isSafeUrl(candidate)
    ));
  }

  private isSafeUrl(value: string): boolean {
    try {
      const protocol = new URL(value).protocol;
      return protocol === 'http:' || protocol === 'https:';
    } catch {
      return false;
    }
  }

  updateFrequency(item: CapabilityDescriptor): string {
    const temporal = String(item.metadata?.['temporal_behavior'] ?? '').trim();
    if (temporal) {
      return temporal;
    }
    if (item.kind === 'provider') {
      return 'Provider-defined';
    }
    return 'Static or request-driven';
  }

  accessConstraints(item: CapabilityDescriptor): string {
    if (item.requires_credentials) {
      return item.is_available ? 'Optional provider key configured.' : 'Optional provider key required before use.';
    }
    return String(item.metadata?.['constraints'] ?? 'Open access with attribution and provider usage limits.');
  }

  dependencies(item: CapabilityDescriptor): string {
    const requirements = item.metadata?.['integration_requirements'];
    if (Array.isArray(requirements) && requirements.length > 0) {
      return requirements.map(String).join('; ');
    }
    if (item.kind === 'tool') {
      return 'Assistant policy engine, runtime profile, and registered direct-tool handler.';
    }
    if (item.kind === 'overlay') {
      return 'MapLibre raster/insight renderer and manifest runtime profile.';
    }
    if (item.kind === 'basemap') {
      return 'MapLibre raster source and manifest runtime profile.';
    }
    return 'Manifest registry and runtime availability checks.';
  }

  trackCapability(_: number, item: CapabilityDescriptor): string {
    return `${item.kind}:${item.id}`;
  }
}

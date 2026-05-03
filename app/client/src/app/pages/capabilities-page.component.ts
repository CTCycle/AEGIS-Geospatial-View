import { CommonModule } from '@angular/common';
import { ChangeDetectorRef, Component, OnInit } from '@angular/core';

import { ApiClientService } from '../core/api-client.service';
import { CapabilityDescriptor, CatalogResponse } from '../core/types';

type CapabilityGroup = 'providers' | 'basemaps' | 'overlays' | 'tools';

@Component({
  selector: 'app-capabilities-page',
  standalone: true,
  imports: [CommonModule],
  templateUrl: './capabilities-page.component.html',
  styleUrl: './capabilities-page.component.css',
})
export class CapabilitiesPageComponent implements OnInit {
  catalog: CatalogResponse = { capabilities: [], providers: [], basemaps: [], overlays: [], tools: [] };
  statusText = 'Loading capabilities';
  isLoading = true;

  readonly groups: Array<{ id: CapabilityGroup; label: string; description: string }> = [
    { id: 'providers', label: 'Data Providers', description: 'Source systems and access constraints.' },
    { id: 'basemaps', label: 'Map Types', description: 'Base map render styles available to map sessions.' },
    { id: 'overlays', label: 'Layers', description: 'Analytical and contextual map layers.' },
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
    } catch {
      this.catalog = { capabilities: [], providers: [], basemaps: [], overlays: [], tools: [] };
      this.statusText = 'Capability catalog unavailable.';
    } finally {
      this.isLoading = false;
      this.changeDetector.detectChanges();
    }
  }

  itemsFor(group: CapabilityGroup): CapabilityDescriptor[] {
    return this.catalog[group] ?? [];
  }

  capabilityPurpose(item: CapabilityDescriptor): string {
    return item.description || String(item.metadata?.['human_summary'] ?? 'Manifest-backed geospatial capability.');
  }

  dataSource(item: CapabilityDescriptor): string {
    const source = item.metadata?.['docs_url'];
    if (typeof source === 'string' && source.trim()) {
      return source;
    }
    const url = item.metadata?.['url'] ?? item.metadata?.['tile_url'] ?? item.metadata?.['url_template'] ?? item.metadata?.['tile_url_template'];
    return typeof url === 'string' && url.trim() ? url : item.provider;
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

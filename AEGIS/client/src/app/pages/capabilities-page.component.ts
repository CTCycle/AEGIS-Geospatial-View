import { CommonModule } from '@angular/common';
import { ChangeDetectorRef, Component, OnInit } from '@angular/core';

import { fetchCatalog } from '../core/api';
import { CapabilityDescriptor, CatalogResponse } from '../core/types';

type CapabilityGroup = 'providers' | 'basemaps' | 'overlays' | 'tools';

const fallbackCapability = (
  id: string,
  name: string,
  kind: CapabilityDescriptor['kind'],
  provider: string,
  description: string,
  metadata: Record<string, string | string[] | boolean> = {},
): CapabilityDescriptor => ({
  id,
  name,
  kind,
  type: kind,
  description,
  provider,
  requires_credentials: Boolean(metadata['requires_key']),
  is_available: !metadata['requires_key'],
  supports_map: kind !== 'tool',
  supports_direct_text: kind === 'tool',
  coverage: String(metadata['coverage'] ?? 'global'),
  intent_tags: Array.isArray(metadata['intent_tags']) ? metadata['intent_tags'] as string[] : [],
  task_tags: Array.isArray(metadata['task_tags']) ? metadata['task_tags'] as string[] : [],
  metadata,
});

const FALLBACK_CATALOG: CatalogResponse = {
  capabilities: [],
  providers: [
    fallbackCapability('gibs', 'NASA GIBS', 'provider', 'gibs', 'NASA raster imagery and environmental map layers.', { coverage: 'global', source_freshness: 'Provider-managed', dataset_time_reference: 'Layer-specific' }),
    fallbackCapability('openaq', 'OpenAQ', 'provider', 'openaq', 'Measured air-quality observations and station context.', { coverage: 'global-partial', source_freshness: 'Provider-managed', dataset_time_reference: 'Measurement timestamps' }),
    fallbackCapability('openmeteo', 'Open-Meteo', 'provider', 'openmeteo', 'Weather and air-quality forecast APIs.', { coverage: 'global', source_freshness: 'Forecast refresh cycle', dataset_time_reference: 'Forecast valid time' }),
    fallbackCapability('overpass', 'Overpass', 'provider', 'overpass', 'OpenStreetMap POI and amenity query service.', { coverage: 'global', source_freshness: 'OSM extract state', dataset_time_reference: 'Current OSM data' }),
    fallbackCapability('inspire', 'INSPIRE Geoportal', 'provider', 'inspire', 'European institutional geospatial data discovery.', { coverage: 'eu-eea', source_freshness: 'Record modified time', dataset_time_reference: 'Dataset-specific' }),
    fallbackCapability('data_europa', 'data.europa.eu', 'provider', 'data_europa', 'European open-data catalog discovery.', { coverage: 'eu-eea', source_freshness: 'Record modified time', dataset_time_reference: 'Dataset-specific' }),
    fallbackCapability('arcgis', 'ArcGIS REST Services', 'provider', 'arcgis', 'Public and credentialed ArcGIS service discovery.', { coverage: 'global', source_freshness: 'Service metadata', dataset_time_reference: 'Service timeInfo where available' }),
    fallbackCapability('geoss', 'GEOSS Platform', 'provider', 'geoss', 'Earth-observation and institutional dataset discovery.', { coverage: 'global', source_freshness: 'Record modified time', dataset_time_reference: 'Dataset-specific' }),
  ],
  basemaps: [
    fallbackCapability('osm_default', 'OpenStreetMap', 'basemap', 'fallback', 'Default open street-map base layer.'),
    fallbackCapability('osm_terrain', 'Terrain Context', 'basemap', 'fallback', 'Terrain-focused basemap for relief and landform context.'),
    fallbackCapability('gibs_satellite', 'NASA GIBS Satellite', 'basemap', 'gibs', 'Satellite imagery basemap.'),
  ],
  overlays: [
    fallbackCapability('openaq_air_quality', 'OpenAQ Air Quality', 'overlay', 'openaq', 'Measured air-quality point insight layer.'),
    fallbackCapability('rainviewer_precipitation_radar', 'RainViewer Precipitation Radar', 'overlay', 'rainviewer', 'Current precipitation radar overlay.'),
    fallbackCapability('SRTM_Color_Index', 'Elevation DEM (SRTM)', 'overlay', 'gibs', 'Terrain elevation color relief overlay.'),
    fallbackCapability('esa_worldcover', 'ESA WorldCover', 'overlay', 'esa', 'Land-cover classification overlay.'),
    fallbackCapability('MODIS_Combined_Thermal_Anomalies_Fire', 'Thermal Anomalies and Fire', 'overlay', 'gibs', 'Active fire and thermal anomaly layer.'),
  ],
  tools: [
    fallbackCapability('location_to_coordinates', 'Location To Coordinates', 'tool', 'nominatim', 'Resolve place names to coordinates.'),
    fallbackCapability('get_weather_forecast', 'Weather Forecast', 'tool', 'openmeteo', 'Fetch local weather forecast data.'),
    fallbackCapability('get_nearby_poi', 'Nearby Points Of Interest', 'tool', 'overpass', 'Fetch nearby amenities around a resolved location.'),
  ],
};
FALLBACK_CATALOG.capabilities = [
  ...(FALLBACK_CATALOG.basemaps ?? []),
  ...(FALLBACK_CATALOG.overlays ?? []),
  ...(FALLBACK_CATALOG.tools ?? []),
];

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

  constructor(private readonly changeDetector: ChangeDetectorRef) {}

  async ngOnInit(): Promise<void> {
    try {
      this.catalog = await fetchCatalog();
      this.statusText = 'Capability catalog loaded';
    } catch {
      this.catalog = FALLBACK_CATALOG;
      this.statusText = 'Showing bundled catalog fallback.';
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

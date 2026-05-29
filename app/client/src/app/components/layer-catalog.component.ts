import { Component, EventEmitter, Input, Output } from '@angular/core';

import { CapabilityDescriptor } from '../core/types';
import { SourceHealthBadgeComponent } from './source-health-badge.component';

@Component({
  selector: 'app-layer-catalog',
  standalone: true,
  imports: [SourceHealthBadgeComponent],
  templateUrl: './layer-catalog.component.html',
  styleUrl: './layer-catalog.component.scss',
})
export class LayerCatalogComponent {
  @Input() layers: CapabilityDescriptor[] = [];
  @Output() askAgent = new EventEmitter<CapabilityDescriptor>();
  @Output() manualToggle = new EventEmitter<CapabilityDescriptor>();

  searchText = '';
  selectedCategory = 'all';

  readonly categories = [
    'all',
    'Base maps',
    'Weather',
    'Hazards',
    'Cameras',
    'Transit',
    'Traffic',
    'Amenities',
    'Environment',
    'Terrain',
    'Demographics',
    'Infrastructure',
    'Tourism',
    'Safety',
  ];

  get filteredLayers(): CapabilityDescriptor[] {
    const query = this.searchText.trim().toLowerCase();
    return this.layers.filter((layer) => {
      const categoryMatch = this.selectedCategory === 'all'
        || this.matchesCategory(layer, this.selectedCategory.toLowerCase());
      const queryMatch = !query
        || layer.name.toLowerCase().includes(query)
        || layer.description?.toLowerCase().includes(query)
        || layer.action_tags.some((tag) => tag.toLowerCase().includes(query))
        || layer.task_tags.some((tag) => tag.toLowerCase().includes(query));
      return categoryMatch && queryMatch;
    });
  }

  setSearchText(value: string): void {
    this.searchText = value;
  }

  setCategory(value: string): void {
    this.selectedCategory = value;
  }

  onCategoryChange(value: string): void {
    this.selectedCategory = this.categories.includes(value) ? value : 'all';
  }

  onSearchInput(value: string): void {
    this.searchText = value;
  }

  canToggle(layer: CapabilityDescriptor): boolean {
    const status = String(layer.reliability?.status || layer.endpoint_health || '').toLowerCase();
    return layer.supports_map
      && layer.is_available
      && layer.rendering_mode !== 'metadata-only'
      && !this.hasCredentialGap(layer)
      && !['broken', 'disabled'].includes(status);
  }

  hasCredentialGap(layer: CapabilityDescriptor): boolean {
    return Boolean(layer.requires_credentials && !layer.is_available);
  }

  stateLabel(layer: CapabilityDescriptor): string | null {
    if (this.hasCredentialGap(layer)) {
      return 'Missing key';
    }
    if (!layer.is_available) {
      return 'Unavailable';
    }
    if (layer.rendering_mode === 'metadata-only' || layer.capability_kind === 'metadata-only') {
      return 'Metadata only';
    }
    return null;
  }

  private matchesCategory(layer: CapabilityDescriptor, category: string): boolean {
    const haystack = [
      layer.kind,
      layer.capability_kind,
      layer.rendering_mode,
      layer.provider,
      ...layer.action_tags,
      ...layer.task_tags,
    ].join(' ').toLowerCase();
    if (category === 'base maps') {
      return haystack.includes('basemap');
    }
    if (category === 'cameras') {
      return haystack.includes('camera') || haystack.includes('webcam');
    }
    if (category === 'hazards') {
      return haystack.includes('hazard') || haystack.includes('risk');
    }
    if (category === 'amenities') {
      return haystack.includes('amenity') || haystack.includes('poi') || haystack.includes('places');
    }
    return haystack.includes(category);
  }
}

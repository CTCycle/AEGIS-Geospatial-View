import { ComponentFixture, TestBed } from '@angular/core/testing';

import { CapabilityDescriptor } from '../core/types';
import { LayerCatalogComponent } from './layer-catalog.component';

describe('components/layer-catalog.component', () => {
  let fixture: ComponentFixture<LayerCatalogComponent>;
  let component: LayerCatalogComponent;

  const layer = (overrides: Partial<CapabilityDescriptor>): CapabilityDescriptor => ({
    id: 'layer',
    name: 'Layer',
    kind: 'vector-overlay',
    provider: 'provider',
    requires_credentials: false,
    is_available: true,
    supports_map: true,
    supports_direct_text: false,
    coverage: 'global',
    intent_tags: [],
    task_tags: [],
    rendering_mode: 'clustered-points',
    reliability: { status: 'functional' },
    ...overrides,
  });

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [LayerCatalogComponent],
    }).compileComponents();

    fixture = TestBed.createComponent(LayerCatalogComponent);
    component = fixture.componentInstance;
    component.layers = [
      layer({
        id: 'windy_webcams',
        name: 'Windy Webcams',
        kind: 'camera-network',
        capability_kind: 'camera-network',
        provider: 'windy_webcams',
        intent_tags: ['webcam', 'camera'],
        rendering_mode: 'camera-points',
      }),
      layer({
        id: 'fema_nfhl_flood_zones',
        name: 'FEMA Flood Zones',
        kind: 'raster-overlay',
        capability_kind: 'raster-overlay',
        provider: 'fema',
        intent_tags: ['flood', 'hazard'],
        rendering_mode: 'wms',
      }),
      layer({
        id: 'fred_regional_market_indicators',
        name: 'FRED Regional Market Indicators',
        kind: 'metadata-only',
        capability_kind: 'metadata-only',
        provider: 'fred',
        supports_map: false,
        supports_direct_text: true,
        rendering_mode: 'metadata-only',
      }),
      layer({
        id: 'broken_layer',
        name: 'Broken Layer',
        kind: 'vector-overlay',
        provider: 'test',
        reliability: { status: 'broken' },
      }),
    ];
  });

  it('filters layers by natural language search text', () => {
    component.setSearchText('webcam');

    expect(component.filteredLayers.map((item) => item.id)).toEqual(['windy_webcams']);
  });

  it('filters layers by catalog category', () => {
    component.setCategory('Hazards');

    expect(component.filteredLayers.map((item) => item.id)).toEqual([
      'fema_nfhl_flood_zones',
    ]);
  });

  it('allows manual toggles only for healthy renderable map layers', () => {
    const byId = Object.fromEntries(component.layers.map((item) => [item.id, item]));

    expect(component.canToggle(byId['windy_webcams'])).toBeTrue();
    expect(component.canToggle(byId['fema_nfhl_flood_zones'])).toBeTrue();
    expect(component.canToggle(byId['fred_regional_market_indicators'])).toBeFalse();
    expect(component.canToggle(byId['broken_layer'])).toBeFalse();
  });

  it('emits ask-agent and manual-toggle actions from the rendered catalog', () => {
    const asked: string[] = [];
    const toggled: string[] = [];
    component.askAgent.subscribe((item) => asked.push(item.id));
    component.manualToggle.subscribe((item) => toggled.push(item.id));

    fixture.detectChanges();
    const buttons = Array.from(
      fixture.nativeElement.querySelectorAll('button'),
    ) as HTMLButtonElement[];
    buttons.find((button) => button.textContent?.includes('Ask agent'))?.click();
    buttons.find((button) => button.textContent?.includes('Toggle'))?.click();

    expect(asked).toEqual(['windy_webcams']);
    expect(toggled).toEqual(['windy_webcams']);
  });
});

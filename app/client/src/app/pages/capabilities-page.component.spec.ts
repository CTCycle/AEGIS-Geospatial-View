import { TestBed } from '@angular/core/testing';

import { ApiClientService } from '../core/api-client.service';
import { CapabilitiesPageComponent } from './capabilities-page.component';

describe('pages/capabilities-page.component', () => {
  beforeEach(async () => {
    const apiClient = jasmine.createSpyObj<ApiClientService>('ApiClientService', ['fetchCatalog']);
    const fetchCatalogMock = jasmine.createSpy('fetchCatalog').and.resolveTo({
      capabilities: [],
      providers: [{ id: 'gibs', name: 'NASA GIBS', kind: 'provider', provider: 'gibs', requires_credentials: false, is_available: true, supports_map: true, supports_direct_text: false, coverage: 'global', intent_tags: [], task_tags: [], metadata: { docs_url: 'https://earthdata.nasa.gov/' } }],
      basemaps: [{ id: 'osm_default', name: 'OpenStreetMap', kind: 'basemap', type: 'tile', description: 'Street map', provider: 'fallback', requires_credentials: false, is_available: true, supports_map: true, supports_direct_text: false, coverage: 'global', intent_tags: [], task_tags: [], metadata: { temporal_behavior: 'static tiles' } }],
      overlays: [{ id: 'tomtom_traffic_flow', name: 'TomTom Traffic Flow', kind: 'overlay', type: 'tile', description: 'Traffic', provider: 'tomtom', requires_credentials: true, is_available: false, supports_map: true, supports_direct_text: false, coverage: 'global', intent_tags: [], task_tags: [], metadata: {} }],
      tools: [{ id: 'get_weather_forecast', name: 'Weather Forecast', kind: 'tool', type: 'direct-tool', description: 'Forecast', provider: 'openmeteo', requires_credentials: false, is_available: true, supports_map: true, supports_direct_text: true, coverage: 'global', intent_tags: [], task_tags: [], metadata: {} }],
    });
    apiClient.fetchCatalog.and.callFake(() => fetchCatalogMock());

    await TestBed.configureTestingModule({
      imports: [CapabilitiesPageComponent],
      providers: [{ provide: ApiClientService, useValue: apiClient }],
    }).compileComponents();
  });

  it('renders grouped catalog data and access constraints', async () => {
    const fixture = TestBed.createComponent(CapabilitiesPageComponent);
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();

    const text = fixture.nativeElement.textContent as string;
    expect(text).toContain('Data Providers');
    expect(text).toContain('Map Types');
    expect(text).toContain('TomTom Traffic Flow');
    expect(text).toContain('Optional provider key required before use.');
  });
});

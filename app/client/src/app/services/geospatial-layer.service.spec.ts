import { TestBed } from '@angular/core/testing';

import { GeospatialLayerService } from './geospatial-layer.service';

describe('services/geospatial-layer.service', () => {
  let service: GeospatialLayerService;
  let hadFetch = false;
  let originalFetch: typeof window.fetch | undefined;

  beforeEach(() => {
    hadFetch = typeof window.fetch === 'function';
    originalFetch = window.fetch;
    if (!hadFetch) {
      Object.defineProperty(window, 'fetch', {
        configurable: true,
        writable: true,
        value: () => Promise.reject(new Error('fetch was not mocked')),
      });
    }
    TestBed.configureTestingModule({});
    service = TestBed.inject(GeospatialLayerService);
  });

  afterEach(() => {
    (window.fetch as jasmine.Spy | undefined)?.and?.stub();
    if (hadFetch) {
      window.fetch = originalFetch as typeof window.fetch;
    } else {
      delete (window as Partial<Window>).fetch;
    }
  });

  it('lists grouped geospatial layers', async () => {
    spyOn(window, 'fetch').and.resolveTo(new Response(JSON.stringify({
      basemaps: [{ id: 'osm_default', name: 'OSM', provider: 'fallback' }],
      overlays: [],
      cameras: [],
      transit: [],
    }), { status: 200 }));

    const result = await service.listLayers();

    expect(result.basemaps?.[0].id).toBe('osm_default');
  });

  it('fetches layer features with bbox, zoom, time, and live flags', async () => {
    const fetchSpy = spyOn(window, 'fetch').and.resolveTo(new Response(JSON.stringify({
      status: 'ok',
      provider: 'usgs',
      payload: { renderingMode: 'clustered-points' },
    }), { status: 200 }));

    const result = await service.fetchFeatures('usgs_earthquakes', {
      bbox: '1,2,3,4',
      zoom: 7,
      time: '2026-05-14T00:00:00Z',
      live: true,
    });

    expect(result.status).toBe('ok');
    expect(fetchSpy.calls.mostRecent().args[0] as string).toContain('bbox=1%2C2%2C3%2C4');
    expect(fetchSpy.calls.mostRecent().args[0] as string).toContain('zoom=7');
    expect(fetchSpy.calls.mostRecent().args[0] as string).toContain('live=true');
  });

  it('checks credential status without exposing secrets', async () => {
    spyOn(window, 'fetch').and.resolveTo(new Response(JSON.stringify({
      provider: 'windy_webcams',
      required: true,
      configured: true,
      environmentVariable: 'WINDY_WEBCAMS_API_KEY',
    }), { status: 200 }));

    const result = await service.credentialStatus('windy_webcams');

    expect(result).toEqual({
      provider: 'windy_webcams',
      required: true,
      configured: true,
      environmentVariable: 'WINDY_WEBCAMS_API_KEY',
    });
  });
});

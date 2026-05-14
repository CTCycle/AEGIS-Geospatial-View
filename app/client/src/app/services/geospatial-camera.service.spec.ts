import { TestBed } from '@angular/core/testing';

import { GeospatialCameraService } from './geospatial-camera.service';

describe('services/geospatial-camera.service', () => {
  let service: GeospatialCameraService;
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
    service = TestBed.inject(GeospatialCameraService);
  });

  afterEach(() => {
    (window.fetch as jasmine.Spy | undefined)?.and?.stub();
    if (hadFetch) {
      window.fetch = originalFetch as typeof window.fetch;
    } else {
      delete (window as Partial<Window>).fetch;
    }
  });

  it('fetches camera collections with bbox and provider filters', async () => {
    const fetchSpy = spyOn(window, 'fetch').and.resolveTo(new Response(JSON.stringify({
      status: 'ok',
      provider: 'windy_webcams',
      payload: { renderingMode: 'camera-points', features: [] },
    }), { status: 200 }));

    const result = await service.fetchCameras({
      bbox: '1,2,3,4',
      provider: 'windy_webcams',
      camera_type: 'traffic',
    });

    expect(result.status).toBe('ok');
    const url = fetchSpy.calls.mostRecent().args[0] as string;
    expect(url).toContain('bbox=1%2C2%2C3%2C4');
    expect(url).toContain('provider=windy_webcams');
    expect(url).toContain('camera_type=traffic');
  });

  it('fetches camera detail by encoded id', async () => {
    const fetchSpy = spyOn(window, 'fetch').and.resolveTo(new Response(JSON.stringify({
      status: 'ok',
      provider: 'windy_webcams',
      camera: { id: 'cam-1' },
    }), { status: 200 }));

    const result = await service.fetchCamera('windy_webcams/cam-1');

    expect(result.status).toBe('ok');
    expect(fetchSpy.calls.mostRecent().args[0] as string).toContain('windy_webcams%2Fcam-1');
  });
});

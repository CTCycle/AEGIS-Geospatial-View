import {
  buildRasterTileProbe,
  countNonTransparentPixels,
  inspectRasterTileContent,
  observeRasterOverlay,
  RasterTileInspectionDependencies,
} from './raster-visibility';
import { MapOverlayEntry } from '../core/types';

describe('raster visibility evidence', () => {
  const overlay = (overrides: Partial<MapOverlayEntry> = {}): MapOverlayEntry => ({
    id: 'fixture-raster',
    capability_id: 'fixture-raster',
    label: 'Fixture raster',
    provider: 'fixture',
    type: 'raster-tile',
    rendering_mode: 'raster-tile',
    tile_url_template: '/tiles/fixture/{z}/{x}/{y}.png',
    default_opacity: 1,
    ...overrides,
  });

  const dependencies = (pixels: ArrayLike<number>): RasterTileInspectionDependencies => ({
    fetch: async () => new Response(new Blob(['fixture']), {
      status: 200,
      headers: { 'content-type': 'image/png' },
    }),
    decodeImage: async () => ({
      width: 2,
      height: 2,
      draw: () => undefined,
    }),
    createCanvas: () => ({
      width: 0,
      height: 0,
      getContext: () => ({
        getImageData: () => ({ data: pixels }),
      }),
    } as unknown as HTMLCanvasElement),
  });

  it('counts only nontransparent image pixels', () => {
    expect(countNonTransparentPixels(new Uint8ClampedArray([
      0, 0, 0, 0,
      0, 0, 0, 255,
      0, 0, 0, 1,
      0, 0, 0, 0,
    ]))).toBe(2);
  });

  it('materializes a viewport-intersecting WMS tile without unresolved placeholders', () => {
    const probe = buildRasterTileProbe(
      overlay({
        type: 'wms',
        rendering_mode: 'wms',
        tile_url_template: undefined,
        url: '/wms',
        layers: 'fixture',
      }),
      [12, 41, 13, 42],
      8,
      [12.5, 41.5],
    );

    expect(probe?.url).toContain('bbox=');
    expect(probe?.url).not.toContain('{bbox-epsg-3857}');
    expect(probe?.tileIntersectsViewport).toBeTrue();
    expect(probe?.zoomSupported).toBeTrue();
  });

  it('accepts an opaque decoded tile as visible raster data', async () => {
    const result = await observeRasterOverlay(
      overlay(),
      {
        viewportBounds: [12, 41, 13, 42],
        zoom: 8,
        center: [12.5, 41.5],
        sourcePresent: true,
        layerPresent: true,
        sourceLoaded: true,
        layerVisible: true,
        opacity: 1,
      },
      dependencies(new Uint8ClampedArray([
        0, 0, 0, 255,
        0, 0, 0, 0,
        0, 0, 0, 0,
        0, 0, 0, 0,
      ])),
    );

    expect(result.resultVisible).toBeTrue();
    expect(result.nonTransparentPixelCount).toBe(1);
    expect(result.tileIntersectsViewport).toBeTrue();
  });

  it('keeps transparent and non-image tiles from becoming visible', async () => {
    const transparent = await observeRasterOverlay(
      overlay(),
      {
        viewportBounds: [12, 41, 13, 42],
        zoom: 8,
        center: [12.5, 41.5],
        sourcePresent: true,
        layerPresent: true,
        sourceLoaded: true,
        layerVisible: true,
        opacity: 1,
      },
      dependencies(new Uint8ClampedArray(16)),
    );
    const nonImage = await inspectRasterTileContent('/tiles/fixture/1/1/1.png', {
      fetch: async () => new Response('not an image', {
        status: 200,
        headers: { 'content-type': 'text/plain' },
      }),
    });

    expect(transparent.resultVisible).toBeFalse();
    expect(transparent.nonTransparentPixelCount).toBe(0);
    expect(nonImage.nonTransparentPixelCount).toBeNull();
    expect(nonImage.failureCode).toBe('raster_tile_not_image');
  });

  it('keeps hidden, transparent, and outside-viewport rasters non-visible', async () => {
    const hidden = await observeRasterOverlay(overlay(), {
      viewportBounds: [12, 41, 13, 42],
      zoom: 8,
      center: [12.5, 41.5],
      sourcePresent: true,
      layerPresent: true,
      sourceLoaded: true,
      layerVisible: false,
      opacity: 1,
    });
    const transparentLayer = await observeRasterOverlay(overlay(), {
      viewportBounds: [12, 41, 13, 42],
      zoom: 8,
      center: [12.5, 41.5],
      sourcePresent: true,
      layerPresent: true,
      sourceLoaded: true,
      layerVisible: true,
      opacity: 0,
    });
    const outside = await observeRasterOverlay(overlay({ bounds: [-10, -10, -5, -5] }), {
      viewportBounds: [12, 41, 13, 42],
      zoom: 8,
      center: [12.5, 41.5],
      sourcePresent: true,
      layerPresent: true,
      sourceLoaded: true,
      layerVisible: true,
      opacity: 1,
    });

    expect(hidden.resultVisible).toBeFalse();
    expect(transparentLayer.resultVisible).toBeFalse();
    expect(outside.resultVisible).toBeFalse();
    expect(outside.tileIntersectsViewport).toBeFalse();
  });

  it('leaves missing source or layer state unproven', async () => {
    const missingSource = await observeRasterOverlay(overlay(), {
      viewportBounds: [12, 41, 13, 42],
      zoom: 8,
      center: [12.5, 41.5],
      sourcePresent: false,
      layerPresent: true,
      sourceLoaded: null,
      layerVisible: true,
      opacity: 1,
    });
    const missingLayer = await observeRasterOverlay(overlay(), {
      viewportBounds: [12, 41, 13, 42],
      zoom: 8,
      center: [12.5, 41.5],
      sourcePresent: true,
      layerPresent: false,
      sourceLoaded: true,
      layerVisible: true,
      opacity: 1,
    });

    expect(missingSource.resultVisible).toBeNull();
    expect(missingSource.failureCode).toBe('raster_source_not_loaded');
    expect(missingLayer.resultVisible).toBeNull();
    expect(missingLayer.failureCode).toBe('raster_source_not_loaded');
  });

  it('does not claim support outside the declared zoom range', () => {
    const probe = buildRasterTileProbe(
      overlay({ min_zoom: 4, max_zoom: 6 }),
      [12, 41, 13, 42],
      8,
      [12.5, 41.5],
    );

    expect(probe?.zoomSupported).toBeFalse();
    expect(probe?.url).toBeNull();
    expect(probe?.failureCode).toBe('raster_zoom_unsupported');
  });

  it('preserves temporal tile selection while proving decoded pixels', async () => {
    let requestedUrl = '';
    const result = await observeRasterOverlay(
      overlay({
        tile_url_template: '/tiles/{time}/{z}/{x}/{y}.png',
        default_time: '2026-09-29',
      }),
      {
        viewportBounds: [12, 41, 13, 42],
        zoom: 8,
        center: [12.5, 41.5],
        sourcePresent: true,
        layerPresent: true,
        sourceLoaded: true,
        layerVisible: true,
        opacity: 1,
      },
      {
        ...dependencies(new Uint8ClampedArray([
          0, 0, 0, 255,
          0, 0, 0, 0,
          0, 0, 0, 0,
          0, 0, 0, 0,
        ])),
        fetch: async (input) => {
          requestedUrl = String(input);
          return new Response(new Blob(['fixture']), {
            status: 200,
            headers: { 'content-type': 'image/png' },
          });
        },
      },
    );

    expect(requestedUrl).toContain('/tiles/2026-09-29/');
    expect(result.resultVisible).toBeTrue();
  });

  it('keeps a failed tile unknown and proves visibility after recovery', async () => {
    let calls = 0;
    const probeDependencies: RasterTileInspectionDependencies = {
      fetch: async () => {
        calls += 1;
        if (calls === 1) {
          return new Response('upstream failure', {
            status: 503,
            headers: { 'content-type': 'text/plain' },
          });
        }
        return new Response(new Blob(['fixture']), {
          status: 200,
          headers: { 'content-type': 'image/png' },
        });
      },
      decodeImage: async () => ({
        width: 1,
        height: 1,
        draw: () => undefined,
      }),
      createCanvas: () => ({
        width: 0,
        height: 0,
        getContext: () => ({
          getImageData: () => ({ data: new Uint8ClampedArray([0, 0, 0, 255]) }),
        }),
      } as unknown as HTMLCanvasElement),
    };
    const context = {
      viewportBounds: [12, 41, 13, 42] as [number, number, number, number],
      zoom: 8,
      center: [12.5, 41.5] as [number, number],
      sourcePresent: true,
      layerPresent: true,
      sourceLoaded: true,
      layerVisible: true,
      opacity: 1,
    };

    const failed = await observeRasterOverlay(overlay(), context, probeDependencies);
    const recovered = await observeRasterOverlay(overlay(), context, probeDependencies);

    expect(failed.resultVisible).toBeNull();
    expect(failed.failureCode).toBe('raster_tile_http_503');
    expect(recovered.resultVisible).toBeTrue();
    expect(recovered.nonTransparentPixelCount).toBe(1);
    expect(calls).toBe(2);
  });
});

import { routes } from './app.routes';

describe('application routes', () => {
  it('keeps only the supported primary destinations and removes Access', () => {
    expect(routes.map((route) => route.path)).toEqual(['', 'geodata', 'settings', '**']);
    expect(routes.some((route) => route.path === 'access-configurations')).toBeFalse();
  });

  it('describes Settings as the unified configuration destination', () => {
    const settings = routes.find((route) => route.path === 'settings');
    expect(settings?.data?.['title']).toBe('AEGIS | Settings');
    expect(settings?.data?.['description']).toContain('model and geospatial provider access');
  });
});

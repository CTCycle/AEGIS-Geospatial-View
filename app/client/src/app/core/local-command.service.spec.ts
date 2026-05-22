import { TestBed } from '@angular/core/testing';

import { ApiClientService } from './api-client.service';
import { LocalCommandService } from './local-command.service';

describe('LocalCommandService', () => {
  let service: LocalCommandService;
  let apiClient: jasmine.SpyObj<ApiClientService>;

  beforeEach(() => {
    apiClient = jasmine.createSpyObj<ApiClientService>('ApiClientService', ['fetchCatalog']);
    TestBed.configureTestingModule({
      providers: [
        LocalCommandService,
        { provide: ApiClientService, useValue: apiClient },
      ],
    });
    service = TestBed.inject(LocalCommandService);
  });

  it('handles zoom in command', async () => {
    const result = await service.resolve('zoom in', { zoomIn: () => true, zoomOut: () => false });
    expect(result).toEqual({ handled: true, assistantMessage: 'Map zoomed in.', status: 'Complete' });
  });

  it('handles zoom out command', async () => {
    const result = await service.resolve('zoom out', { zoomIn: () => false, zoomOut: () => true });
    expect(result).toEqual({ handled: true, assistantMessage: 'Map zoomed out.', status: 'Complete' });
  });

  it('returns handled false for unknown command', async () => {
    const result = await service.resolve('hello world', { zoomIn: () => false, zoomOut: () => false });
    expect(result).toEqual({ handled: false });
  });

  it('uses catalog for capability requests', async () => {
    apiClient.fetchCatalog.and.resolveTo({ capabilities: [], basemaps: [], overlays: [], tools: [] });
    const result = await service.resolve('what can you do', { zoomIn: () => false, zoomOut: () => false });
    expect(apiClient.fetchCatalog).toHaveBeenCalled();
    expect(result.handled).toBeTrue();
    expect(result.assistantMessage).toContain('Current catalog: 0 map types, 0 layers, and 0 direct tools.');
  });
});

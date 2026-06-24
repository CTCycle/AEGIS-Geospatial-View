import { TestBed } from '@angular/core/testing';

import { LocalCommandService } from './local-command.service';

describe('LocalCommandService', () => {
  let service: LocalCommandService;

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [LocalCommandService],
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

  it('leaves capability requests for the agent', async () => {
    const result = await service.resolve('what can you do', { zoomIn: () => false, zoomOut: () => false });
    expect(result).toEqual({ handled: false });
  });
});

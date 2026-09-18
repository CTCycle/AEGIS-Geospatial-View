import { TestBed } from '@angular/core/testing';

import { ExecutionStatusComponent } from './execution-status.component';

describe('components/execution-status.component', () => {
  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [ExecutionStatusComponent],
    }).compileComponents();
  });

  it('renders a compact idle tool activity trigger', () => {
    const fixture = TestBed.createComponent(ExecutionStatusComponent);
    fixture.detectChanges();

    const trigger = fixture.nativeElement.querySelector('.execution-status__trigger') as HTMLButtonElement;
    expect(trigger.textContent).toContain('Tool activity');
    expect(trigger.textContent).toContain('Idle');
    expect(trigger.getAttribute('aria-expanded')).toBe('false');
    expect(fixture.nativeElement.querySelector('.execution-status__panel')).toBeNull();
  });

  it('summarizes running and failed tool activity without exposing arbitrary payloads', () => {
    const fixture = TestBed.createComponent(ExecutionStatusComponent);
    const component = fixture.componentInstance;
    component.runId = 'run-1';
    component.active = true;
    component.toolProgress = [{
      call_id: 'call-1',
      tool_name: 'execute_geospatial_capability',
      status: 'running',
      label: 'Loading provider data',
      summary: 'Provider request is in progress.',
      duration_ms: null,
      error: null,
    }];
    fixture.detectChanges();

    expect(component.summaryLabel).toBe('Loading provider data');

    component.toolProgress = [{
      call_id: 'call-1',
      tool_name: 'execute_geospatial_capability',
      status: 'failed',
      summary: 'The provider request failed.',
      duration_ms: 1250,
      error: 'Provider unavailable.',
    }];
    fixture.detectChanges();

    expect(component.summaryLabel).toBe('Needs attention');
    expect(component.failedToolCount).toBe(1);
  });

  it('emits expansion changes and renders execution details outside the chat', () => {
    const fixture = TestBed.createComponent(ExecutionStatusComponent);
    const component = fixture.componentInstance;
    component.runId = 'run-1';
    component.runVersion = 2;
    component.expanded = true;
    component.toolProgress = [{
      call_id: 'call-1',
      tool_name: 'discover_geospatial_capabilities',
      status: 'success',
      summary: 'Found compatible capabilities.',
      duration_ms: 42,
      error: null,
    }];
    const expandedChange = spyOn(component.expandedChange, 'emit');
    fixture.detectChanges();

    const panel = fixture.nativeElement.querySelector('.execution-status__panel') as HTMLElement;
    expect(panel).not.toBeNull();
    expect(panel.textContent).toContain('Execution details');
    expect(panel.textContent).toContain('discover_geospatial_capabilities');
    expect(panel.textContent).toContain('42 ms');

    (fixture.nativeElement.querySelector('.execution-status__trigger') as HTMLButtonElement).click();
    expect(expandedChange).toHaveBeenCalledWith(false);
  });

  it('closes the expanded panel with Escape', () => {
    const fixture = TestBed.createComponent(ExecutionStatusComponent);
    const component = fixture.componentInstance;
    component.expanded = true;
    const expandedChange = spyOn(component.expandedChange, 'emit');
    fixture.detectChanges();

    document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }));

    expect(expandedChange).toHaveBeenCalledWith(false);
  });
});

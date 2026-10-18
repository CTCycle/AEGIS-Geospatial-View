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

  it('renders multiple tool calls and retry trace metadata in the expanded panel', () => {
    const fixture = TestBed.createComponent(ExecutionStatusComponent);
    const component = fixture.componentInstance;
    component.runId = 'run-1';
    component.expanded = true;
    component.toolProgress = [
      {
        call_id: 'call-1',
        tool_name: 'discover_geospatial_capabilities',
        status: 'success',
        summary: 'Capabilities discovered.',
        duration_ms: 30,
        error: null,
      },
      {
        call_id: 'call-2',
        tool_name: 'execute_geospatial_capability',
        status: 'partial',
        summary: 'Primary source was unavailable; recovery continued.',
        duration_ms: 225,
        error: null,
      },
    ];
    component.traceEntries = [{
      event_id: 'trace-retry',
      sequence: 4,
      run_id: 'run-1',
      run_version: 1,
      kind: 'tool_retry',
      timestamp: '2026-09-18T10:00:00Z',
      tool_name: 'execute_geospatial_capability',
      call_id: 'call-2',
      iteration: 2,
      summary: 'Retrying with a compatible source.',
      duration_ms: 225,
      evidence_refs: [],
      retryable: true,
      error: null,
    }];
    fixture.detectChanges();

    const panel = fixture.nativeElement.querySelector('.execution-status__panel') as HTMLElement;
    expect(panel.textContent).toContain('discover_geospatial_capabilities');
    expect(panel.textContent).toContain('execute_geospatial_capability');
    expect(panel.textContent).toContain('tool_retry');
    expect(panel.textContent).toContain('Retrying with a compatible source.');
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

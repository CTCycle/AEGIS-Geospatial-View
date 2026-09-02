import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';

import { CapabilityStatusListComponent } from './capability-status-list.component';

describe('CapabilityStatusListComponent', () => {
  let fixture: ComponentFixture<CapabilityStatusListComponent>;
  let component: CapabilityStatusListComponent;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [CapabilityStatusListComponent],
      providers: [provideRouter([])],
    }).compileComponents();

    fixture = TestBed.createComponent(CapabilityStatusListComponent);
    component = fixture.componentInstance;
  });

  it('renders typed status items with matching tone classes', () => {
    component.items = [
      { label: 'Agent online', statusLabel: 'Active', tone: 'none' },
      { label: 'Satellite Imagery', statusLabel: 'Active', tone: 'ok' },
      { label: 'Optional Keys', statusLabel: 'Disabled', tone: 'warn' },
    ];

    fixture.detectChanges();

    const host = fixture.nativeElement as HTMLElement;
    const items = Array.from(host.querySelectorAll('li'));
    const labels = Array.from(host.querySelectorAll<HTMLElement>('.status-item__content, .status-item__action'));
    expect(labels.map((item) => item.textContent?.replace(/\s+/g, ' ').trim())).toEqual([
      'Agent online Active',
      'Satellite Imagery Active',
      'Optional Keys Disabled',
    ]);
    expect(items[0].querySelector('.state-dot--ok')).toBeNull();
    expect(items[1].querySelector('.state-dot--ok')).not.toBeNull();
    expect(items[2].querySelector('.state-dot--warn')).not.toBeNull();
  });

  it('shows hover descriptions and exposes only configured navigation actions', () => {
    component.items = [
      { label: 'Agent model', statusLabel: 'Configured', tone: 'ok' },
      { label: 'Satellite', statusLabel: 'Available', tone: 'ok', detail: 'Satellite imagery is available.' },
    ];
    component.interactions = {
      'Agent model': {
        route: '/settings',
        actionLabel: 'Open model settings',
        description: 'The configured agent model is ready for use.',
      },
    };

    fixture.detectChanges();

    const host = fixture.nativeElement as HTMLElement;
    const items = Array.from(host.querySelectorAll('li'));
    const action = items[0].querySelector<HTMLAnchorElement>('.status-item__action');

    expect(action?.getAttribute('href')).toBe('/settings');
    expect(items[1].querySelector('.status-item__action')).toBeNull();

    items[0].dispatchEvent(new MouseEvent('mouseenter'));
    fixture.detectChanges();

    const tooltip = host.querySelector<HTMLElement>('[role="tooltip"]');
    expect(tooltip?.textContent?.replace(/\s+/g, ' ').trim()).toBe(
      'The configured agent model is ready for use. Open model settings',
    );

    items[0].dispatchEvent(new MouseEvent('mouseleave'));
    fixture.detectChanges();
    expect(host.querySelector('[role="tooltip"]')).toBeNull();
  });
});

import { ComponentFixture, TestBed } from '@angular/core/testing';

import { CapabilityStatusListComponent } from './capability-status-list.component';

describe('CapabilityStatusListComponent', () => {
  let fixture: ComponentFixture<CapabilityStatusListComponent>;
  let component: CapabilityStatusListComponent;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [CapabilityStatusListComponent],
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
    expect(items.map((item) => item.textContent?.replace(/\s+/g, ' ').trim())).toEqual([
      'Agent online Active',
      'Satellite Imagery Active',
      'Optional Keys Disabled',
    ]);
    expect(items[0].querySelector('.state-dot--ok')).toBeNull();
    expect(items[1].querySelector('.state-dot--ok')).not.toBeNull();
    expect(items[2].querySelector('.state-dot--warn')).not.toBeNull();
  });
});

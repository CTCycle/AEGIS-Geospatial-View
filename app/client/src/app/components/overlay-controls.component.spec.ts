import { ComponentFixture, TestBed } from '@angular/core/testing';

import { OverlayControlsComponent } from './overlay-controls.component';

describe('OverlayControlsComponent', () => {
  let fixture: ComponentFixture<OverlayControlsComponent>;
  let component: OverlayControlsComponent;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [OverlayControlsComponent],
    }).compileComponents();

    fixture = TestBed.createComponent(OverlayControlsComponent);
    component = fixture.componentInstance;
    component.overlays = [{ id: 'ov1', label: 'Overlay 1', provider: 'x', type: 'tile' }] as never;
    component.overlayVisibility = { ov1: true };
    component.overlayOpacity = { ov1: 0.5 };
  });

  it('emits visibility updates', () => {
    const spy = jasmine.createSpy('visibility');
    component.overlayVisibilityChange.subscribe(spy);
    component.onOverlayVisibilityChange('ov1', { target: { checked: false } } as unknown as Event);
    expect(spy).toHaveBeenCalledWith({ overlayId: 'ov1', checked: false });
  });

  it('emits clamped opacity updates for valid values', () => {
    const spy = jasmine.createSpy('opacity');
    component.overlayOpacityChange.subscribe(spy);
    component.onOpacityChange('ov1', '120');
    expect(spy).toHaveBeenCalledWith({ overlayId: 'ov1', percentValue: '100' });
  });

  it('emits nothing for non numeric opacity input', () => {
    const spy = jasmine.createSpy('opacity');
    component.overlayOpacityChange.subscribe(spy);
    component.onOpacityChange('ov1', 'abc');
    expect(spy).not.toHaveBeenCalled();
  });

  it('disables opacity controls for metadata-only overlays and exposes status text', () => {
    component.overlayRenderStatuses = [
      {
        overlayId: 'ov1',
        status: 'metadata-only',
        message: 'Metadata only.',
      },
    ];

    fixture.detectChanges();

    const range = fixture.nativeElement.querySelector('input[type="range"]') as HTMLInputElement | null;
    const note = fixture.nativeElement.querySelector('.overlay-render-note') as HTMLParagraphElement | null;

    expect(range?.disabled).toBeTrue();
    expect(note?.textContent).toContain('metadata-only');
  });
});

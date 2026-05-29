import { ComponentFixture, TestBed } from '@angular/core/testing';

import { SettingsModalShellComponent } from './settings-modal-shell.component';

describe('SettingsModalShellComponent', () => {
  let fixture: ComponentFixture<SettingsModalShellComponent>;
  let component: SettingsModalShellComponent;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [SettingsModalShellComponent],
    }).compileComponents();

    fixture = TestBed.createComponent(SettingsModalShellComponent);
    component = fixture.componentInstance;
    component.title = 'Settings';
    component.ariaLabel = 'Settings';
  });

  it('emits close on backdrop click', () => {
    const spy = jasmine.createSpy('close');
    component.requestClose.subscribe(spy);
    const target = {} as EventTarget;
    component.onBackdropClick({ target, currentTarget: target } as unknown as MouseEvent);
    expect(spy).toHaveBeenCalled();
  });

  it('does not emit close on content click', () => {
    const spy = jasmine.createSpy('close');
    component.requestClose.subscribe(spy);
    component.onBackdropClick({ target: {}, currentTarget: {} } as unknown as MouseEvent);
    expect(spy).not.toHaveBeenCalled();
  });

  it('does not emit close on backdrop click when backdrop close is disabled', () => {
    const spy = jasmine.createSpy('close');
    component.closeOnBackdrop = false;
    component.requestClose.subscribe(spy);
    const target = {} as EventTarget;
    component.onBackdropClick({ target, currentTarget: target } as unknown as MouseEvent);
    expect(spy).not.toHaveBeenCalled();
  });
});

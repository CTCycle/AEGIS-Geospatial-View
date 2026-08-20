import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';

import { AppComponent } from './app.component';

describe('AppComponent desktop viewport contract', () => {
  let fixture: ComponentFixture<AppComponent>;
  let originalInnerWidth: number;

  beforeEach(async () => {
    originalInnerWidth = window.innerWidth;
    await TestBed.configureTestingModule({
      imports: [AppComponent],
      providers: [provideRouter([])],
    }).compileComponents();
  });

  afterEach(() => {
    fixture?.destroy();
    setWindowInnerWidth(originalInnerWidth);
  });

  it('keeps the full desktop shell active at the minimum supported width', () => {
    setWindowInnerWidth(1024);
    fixture = TestBed.createComponent(AppComponent);
    fixture.detectChanges();

    const element: HTMLElement = fixture.nativeElement;
    expect(fixture.componentInstance.isDesktopViewport).toBeTrue();
    expect(element.querySelector('.desktop-viewport-gate')?.classList.contains('desktop-viewport-gate--visible')).toBeFalse();
    expect(element.querySelector('.app-shell')?.hasAttribute('inert')).toBeFalse();
    expect(element.querySelector('.operations-bar')?.textContent).toContain('Model Settings');
    expect(element.querySelector('.nav-label--compact')).toBeNull();
  });

  it('blocks the application below the minimum supported width', async () => {
    setWindowInnerWidth(900);
    fixture = TestBed.createComponent(AppComponent);
    fixture.detectChanges();
    await new Promise((resolve) => window.setTimeout(resolve));

    const element: HTMLElement = fixture.nativeElement;
    const gate = element.querySelector('.desktop-viewport-gate');
    const shell = element.querySelector('.app-shell');
    expect(fixture.componentInstance.isDesktopViewport).toBeFalse();
    expect(gate?.classList.contains('desktop-viewport-gate--visible')).toBeTrue();
    expect(gate?.getAttribute('aria-hidden')).toBeNull();
    expect(shell?.hasAttribute('inert')).toBeTrue();
    expect(shell?.getAttribute('aria-hidden')).toBe('true');
    expect(document.activeElement).toBe(gate);
  });

  it('updates the gate when the browser crosses the desktop threshold', () => {
    setWindowInnerWidth(900);
    fixture = TestBed.createComponent(AppComponent);
    fixture.detectChanges();

    setWindowInnerWidth(1280);
    window.dispatchEvent(new Event('resize'));
    fixture.detectChanges();
    expect(fixture.componentInstance.isDesktopViewport).toBeTrue();
    expect(fixture.nativeElement.querySelector('.app-shell')?.hasAttribute('inert')).toBeFalse();

    setWindowInnerWidth(1023);
    window.dispatchEvent(new Event('resize'));
    fixture.detectChanges();
    expect(fixture.componentInstance.isDesktopViewport).toBeFalse();
    expect(fixture.nativeElement.querySelector('.app-shell')?.hasAttribute('inert')).toBeTrue();
  });
});

function setWindowInnerWidth(width: number): void {
  Object.defineProperty(window, 'innerWidth', {
    configurable: true,
    value: width,
  });
}

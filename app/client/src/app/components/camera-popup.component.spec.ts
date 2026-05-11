import { ComponentFixture, TestBed } from '@angular/core/testing';

import { CameraFeature } from '../core/types';
import { CameraPopupComponent } from './camera-popup.component';

describe('components/camera-popup.component', () => {
  let fixture: ComponentFixture<CameraPopupComponent>;
  let component: CameraPopupComponent;

  const camera: CameraFeature = {
    id: 'cam-1',
    name: 'Pass view',
    provider: 'windy_webcams',
    camera_type: 'webcam',
    latitude: 45.1,
    longitude: 7.2,
    preview_image_url: 'https://example.test/preview.jpg',
    official_url: 'https://example.test/camera',
    embed_url: 'https://example.test/embed',
    embedding_allowed: false,
    stale: true,
    metadata: {},
  };

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [CameraPopupComponent],
    }).compileComponents();

    fixture = TestBed.createComponent(CameraPopupComponent);
    component = fixture.componentInstance;
  });

  it('renders preview metadata, stale state, and official link', () => {
    component.camera = camera;
    fixture.detectChanges();

    const element = fixture.nativeElement as HTMLElement;
    const image = element.querySelector('img') as HTMLImageElement;
    const link = element.querySelector('a') as HTMLAnchorElement;

    expect(element.textContent).toContain('Pass view');
    expect(element.textContent).toContain('Stale');
    expect(element.textContent).toContain('windy_webcams');
    expect(image.src).toContain('/preview.jpg');
    expect(link.href).toBe('https://example.test/camera');
  });

  it('does not embed camera player URLs when embedding is not allowed', () => {
    component.camera = camera;
    fixture.detectChanges();

    const element = fixture.nativeElement as HTMLElement;

    expect(element.querySelector('iframe')).toBeNull();
    expect(element.innerHTML).not.toContain('https://example.test/embed');
  });

  it('embeds camera player URLs only when provider permission allows it', () => {
    component.camera = {
      ...camera,
      embedding_allowed: true,
      stale: false,
    };
    fixture.detectChanges();

    const iframe = fixture.nativeElement.querySelector('iframe') as HTMLIFrameElement;

    expect(iframe).not.toBeNull();
    expect(iframe.title).toBe('Pass view live camera');
    expect(iframe.src).toBe('https://example.test/embed');
  });
});

import { Component, Input } from '@angular/core';
import { DomSanitizer, SafeResourceUrl } from '@angular/platform-browser';

import { CameraFeature } from '../core/types';

@Component({
  selector: 'app-camera-popup',
  standalone: true,
  templateUrl: './camera-popup.component.html',
})
export class CameraPopupComponent {
  @Input() camera?: CameraFeature;

  constructor(private readonly sanitizer: DomSanitizer) {}

  get safeEmbedUrl(): SafeResourceUrl | null {
    if (!this.camera?.embedding_allowed || !this.camera.embed_url) {
      return null;
    }
    return this.sanitizer.bypassSecurityTrustResourceUrl(this.camera.embed_url);
  }
}

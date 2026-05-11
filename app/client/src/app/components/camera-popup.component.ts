import { Component, Input } from '@angular/core';

import { CameraFeature } from '../core/types';

@Component({
  selector: 'app-camera-popup',
  standalone: true,
  templateUrl: './camera-popup.component.html',
})
export class CameraPopupComponent {
  @Input() camera?: CameraFeature;
}

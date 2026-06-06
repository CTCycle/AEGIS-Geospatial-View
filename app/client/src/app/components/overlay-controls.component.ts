import { Component, EventEmitter, Input, Output } from '@angular/core';

import { DEFAULT_OVERLAY_OPACITY } from '../core/constants';
import {
  MapSession,
  OverlayOpacityChange,
  OverlayRenderStatus,
  OverlayVisibilityChange,
} from '../core/types';

type OverlayEntry = NonNullable<MapSession['overlays']>[number];

@Component({
  selector: 'app-overlay-controls',
  standalone: true,
  templateUrl: './overlay-controls.component.html',
  styleUrl: './overlay-controls.component.css',
})
export class OverlayControlsComponent {
  @Input({ required: true }) overlays: OverlayEntry[] = [];
  @Input({ required: true }) overlayVisibility: Record<string, boolean> = {};
  @Input({ required: true }) overlayOpacity: Record<string, number> = {};
  @Input() overlayRenderStatuses: OverlayRenderStatus[] = [];

  @Output() overlayVisibilityChange = new EventEmitter<OverlayVisibilityChange>();
  @Output() overlayOpacityChange = new EventEmitter<OverlayOpacityChange>();

  trackOverlay(_: number, overlay: OverlayEntry): string {
    return overlay.id;
  }

  getOpacityPercent(overlay: OverlayEntry): number {
    return Math.round((this.overlayOpacity[overlay.id] ?? overlay.default_opacity ?? DEFAULT_OVERLAY_OPACITY) * 100);
  }

  getRenderStatus(overlayId: string): OverlayRenderStatus['status'] {
    return this.overlayRenderStatuses.find((status) => status.overlayId === overlayId)?.status ?? 'pending';
  }

  getRenderMessage(overlayId: string): string | undefined {
    return this.overlayRenderStatuses.find((status) => status.overlayId === overlayId)?.message;
  }

  isOpacityDisabled(overlayId: string): boolean {
    return this.getRenderStatus(overlayId) === 'metadata-only';
  }

  onOverlayVisibilityChange(overlayId: string, event: Event): void {
    const target = event.target as HTMLInputElement | null;
    this.overlayVisibilityChange.emit({ overlayId, checked: Boolean(target?.checked) });
  }

  onOverlayOpacityChange(overlayId: string, event: Event): void {
    const target = event.target as HTMLInputElement | null;
    this.overlayOpacityChange.emit({ overlayId, percentValue: target?.value ?? '0' });
  }

  onOpacityChange(overlayId: string, rawValue: string): void {
    const parsed = Number(rawValue);
    if (!Number.isFinite(parsed)) {
      return;
    }
    const clampedPercent = Math.min(100, Math.max(0, parsed));
    this.overlayOpacityChange.emit({ overlayId, percentValue: String(clampedPercent) });
  }
}

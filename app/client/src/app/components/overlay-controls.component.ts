import { Component, EventEmitter, Input, Output, ChangeDetectionStrategy } from '@angular/core';

import { DEFAULT_OVERLAY_OPACITY } from '../core/constants';
import {
  MapOverlayEntry,
  OverlayOpacityChange,
  OverlayRenderStatus,
  OverlayVisibilityChange,
} from '../core/types';

@Component({
  selector: 'app-overlay-controls',
  standalone: true,
  templateUrl: './overlay-controls.component.html',
  changeDetection: ChangeDetectionStrategy.Eager,
  styleUrl: './overlay-controls.component.css',
})
export class OverlayControlsComponent {
  @Input({ required: true }) overlays: MapOverlayEntry[] = [];
  @Input({ required: true }) overlayVisibility: Record<string, boolean> = {};
  @Input({ required: true }) overlayOpacity: Record<string, number> = {};
  @Input() overlayRenderStatuses: OverlayRenderStatus[] = [];

  @Output() overlayVisibilityChange = new EventEmitter<OverlayVisibilityChange>();
  @Output() overlayOpacityChange = new EventEmitter<OverlayOpacityChange>();

  isExpanded = false;

  toggleExpanded(): void {
    this.isExpanded = !this.isExpanded;
  }

  get visibleOverlayCount(): number {
    return this.overlays.filter((overlay) => this.overlayVisibility[overlay.id] ?? true).length;
  }

  trackOverlay(_: number, overlay: MapOverlayEntry): string {
    return overlay.id;
  }

  getOpacityPercent(overlay: MapOverlayEntry): number {
    return Math.round((this.overlayOpacity[overlay.id] ?? overlay.default_opacity ?? DEFAULT_OVERLAY_OPACITY) * 100);
  }

  getRenderStatus(overlayId: string): OverlayRenderStatus['status'] {
    return this.overlayRenderStatuses.find((status) => status.overlayId === overlayId)?.status ?? 'pending';
  }

  getRenderMessage(overlayId: string): string | undefined {
    return this.overlayRenderStatuses.find((status) => status.overlayId === overlayId)?.message;
  }

  getOpacityLabel(overlay: MapOverlayEntry): string {
    return `Opacity for ${overlay.label}: ${this.getOpacityPercent(overlay)} percent`;
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

import { CommonModule } from '@angular/common';
import { ChangeDetectionStrategy, Component, Input } from '@angular/core';
import { RouterLink } from '@angular/router';

export type CapabilityStatusTone = 'ok' | 'warn' | 'error' | 'none';

export interface CapabilityStatusItem {
  label: string;
  statusLabel: string;
  tone: CapabilityStatusTone;
  detail?: string;
}

export interface CapabilityStatusInteraction {
  route?: string;
  actionLabel?: string;
  description?: string;
}

@Component({
  selector: 'app-capability-status-list',
  standalone: true,
  imports: [CommonModule, RouterLink],
  templateUrl: './capability-status-list.component.html',
  changeDetection: ChangeDetectionStrategy.Eager,
  styleUrl: './capability-status-list.component.css',
})
export class CapabilityStatusListComponent {
  private static nextInstanceId = 0;

  @Input({ required: true }) items: CapabilityStatusItem[] = [];
  @Input() nowrap = false;
  @Input() interactions: Record<string, CapabilityStatusInteraction> = {};

  activeTooltipIndex: number | null = null;
  tooltipLeft = 0;
  tooltipTop = 0;
  tooltipPlacement: 'above' | 'below' = 'above';

  private readonly tooltipIdPrefix = `capability-status-${CapabilityStatusListComponent.nextInstanceId++}`;

  trackStatusItem(_: number, item: CapabilityStatusItem): string {
    return `${item.label}:${item.statusLabel}`;
  }

  interactionFor(item: CapabilityStatusItem): CapabilityStatusInteraction | undefined {
    return this.interactions[item.label];
  }

  descriptionFor(item: CapabilityStatusItem): string {
    const interaction = this.interactionFor(item);
    return interaction?.description
      || item.detail
      || `${item.label} is currently ${item.statusLabel.toLowerCase()}.`;
  }

  tooltipId(index: number): string {
    return `${this.tooltipIdPrefix}-${index}`;
  }

  showTooltip(index: number, event: Event): void {
    const target = event.currentTarget as HTMLElement | null;
    if (!target) {
      return;
    }

    const rect = target.getBoundingClientRect();
    const tooltipHalfWidth = 168;
    const viewportWidth = window.innerWidth;
    const center = rect.left + rect.width / 2;

    this.tooltipLeft = Math.min(
      Math.max(center, tooltipHalfWidth),
      Math.max(tooltipHalfWidth, viewportWidth - tooltipHalfWidth),
    );
    this.tooltipPlacement = rect.top < 84 ? 'below' : 'above';
    this.tooltipTop = this.tooltipPlacement === 'below'
      ? rect.bottom + 8
      : Math.max(8, rect.top - 8);
    this.activeTooltipIndex = index;
  }

  hideTooltip(index: number): void {
    if (this.activeTooltipIndex === index) {
      this.activeTooltipIndex = null;
    }
  }
}

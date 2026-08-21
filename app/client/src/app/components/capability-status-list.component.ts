import { CommonModule } from '@angular/common';
import { Component, Input, ChangeDetectionStrategy } from '@angular/core';

export type CapabilityStatusTone = 'ok' | 'warn' | 'error' | 'none';

export interface CapabilityStatusItem {
  label: string;
  statusLabel: string;
  tone: CapabilityStatusTone;
  detail?: string;
}

@Component({
  selector: 'app-capability-status-list',
  standalone: true,
  imports: [CommonModule],
  templateUrl: './capability-status-list.component.html',
  changeDetection: ChangeDetectionStrategy.Eager,
  styleUrl: './capability-status-list.component.css',
})
export class CapabilityStatusListComponent {
  @Input({ required: true }) items: CapabilityStatusItem[] = [];

  trackStatusItem(_: number, item: CapabilityStatusItem): string {
    return `${item.label}:${item.statusLabel}`;
  }
}

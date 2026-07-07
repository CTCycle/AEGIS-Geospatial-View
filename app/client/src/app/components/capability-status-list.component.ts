import { CommonModule } from '@angular/common';
import { Component, Input } from '@angular/core';

export type CapabilityStatusTone = 'ok' | 'warn' | 'none';

export interface CapabilityStatusItem {
  label: string;
  statusLabel: string;
  tone: CapabilityStatusTone;
}

@Component({
  selector: 'app-capability-status-list',
  standalone: true,
  imports: [CommonModule],
  templateUrl: './capability-status-list.component.html',
  styleUrl: './capability-status-list.component.css',
})
export class CapabilityStatusListComponent {
  @Input({ required: true }) items: CapabilityStatusItem[] = [];

  trackStatusItem(_: number, item: CapabilityStatusItem): string {
    return `${item.label}:${item.statusLabel}`;
  }
}

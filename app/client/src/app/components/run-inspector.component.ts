import { CommonModule } from '@angular/common';
import { ChangeDetectionStrategy, Component, EventEmitter, Input, Output } from '@angular/core';

import {
  AgentTask,
  AgentTaskState,
  RunTraceEntry,
  ToolProgressItem,
} from '../core/types';

@Component({
  selector: 'app-run-inspector',
  standalone: true,
  imports: [CommonModule],
  templateUrl: './run-inspector.component.html',
  styleUrl: './run-inspector.component.css',
  changeDetection: ChangeDetectionStrategy.Eager,
})
export class RunInspectorComponent {
  @Input() runId?: string;
  @Input() runVersion?: number;
  @Input() taskState?: AgentTaskState | null;
  @Input() toolProgress: ToolProgressItem[] = [];
  @Input() traceEntries: RunTraceEntry[] = [];
  @Input() loading = false;
  @Input() error = '';
  @Input() expanded = false;

  @Output() readonly expandedChange = new EventEmitter<boolean>();
  @Output() readonly refresh = new EventEmitter<void>();

  get hasDetails(): boolean {
    return Boolean(this.runId || this.taskState || this.toolProgress.length || this.traceEntries.length);
  }

  get taskItems(): AgentTask[] {
    return this.taskState?.tasks ?? [];
  }

  trackTask(_: number, task: AgentTask): string {
    return task.id;
  }

  trackTrace(_: number, entry: RunTraceEntry): string {
    return `${entry.event_id}:${entry.sequence}`;
  }

  statusLabel(status: string | null | undefined): string {
    if (!status) {
      return 'Unknown';
    }
    return status.replaceAll('_', ' ');
  }

  taskStatusLabel(task: AgentTask): string {
    return this.statusLabel(task.status);
  }

  formatDuration(duration: number | null | undefined): string {
    if (duration === null || duration === undefined || !Number.isFinite(duration)) {
      return 'Duration unavailable';
    }
    return duration < 1000 ? `${Math.round(duration)} ms` : `${(duration / 1000).toFixed(1)} s`;
  }

  formatTimestamp(timestamp: string): string {
    const date = new Date(timestamp);
    return Number.isNaN(date.getTime())
      ? timestamp
      : new Intl.DateTimeFormat(undefined, { dateStyle: 'medium', timeStyle: 'short' }).format(date);
  }

  onToggle(event: Event): void {
    this.expandedChange.emit((event.currentTarget as HTMLDetailsElement | null)?.open ?? false);
  }
}

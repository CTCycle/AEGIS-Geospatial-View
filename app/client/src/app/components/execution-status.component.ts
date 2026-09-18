import { CommonModule } from '@angular/common';
import { ChangeDetectionStrategy, Component, EventEmitter, HostListener, Input, Output } from '@angular/core';

import {
  AgentTask,
  AgentTaskState,
  RunTraceEntry,
  ToolProgressItem,
} from '../core/types';

@Component({
  selector: 'app-execution-status',
  standalone: true,
  imports: [CommonModule],
  templateUrl: './execution-status.component.html',
  styleUrl: './execution-status.component.css',
  changeDetection: ChangeDetectionStrategy.Eager,
})
export class ExecutionStatusComponent {
  private static nextInstanceId = 0;

  @Input() runId?: string;
  @Input() runVersion?: number;
  @Input() taskState?: AgentTaskState | null;
  @Input() toolProgress: ToolProgressItem[] = [];
  @Input() traceEntries: RunTraceEntry[] = [];
  @Input() active = false;
  @Input() traceLoading = false;
  @Input() runError = '';
  @Input() traceError = '';
  @Input() expanded = false;

  @Output() readonly expandedChange = new EventEmitter<boolean>();
  @Output() readonly refresh = new EventEmitter<void>();

  readonly panelId = `execution-status-panel-${ExecutionStatusComponent.nextInstanceId++}`;

  get taskItems(): AgentTask[] {
    return this.taskState?.tasks ?? [];
  }

  get failedToolCount(): number {
    return this.toolProgress.filter((tool) => tool.status === 'failed').length;
  }

  get runningTool(): ToolProgressItem | undefined {
    return [...this.toolProgress].reverse().find((tool) => tool.status === 'running');
  }

  get summaryLabel(): string {
    if (this.runError || this.failedToolCount > 0 || this.taskState?.status === 'failed') {
      return 'Needs attention';
    }
    if (this.runningTool) {
      return this.runningTool.label || this.runningTool.tool_name;
    }
    if (this.active) {
      return 'Running';
    }
    if (this.toolProgress.length > 0) {
      const count = this.toolProgress.length;
      return `${count} call${count === 1 ? '' : 's'}`;
    }
    if (this.runId) {
      return 'Complete';
    }
    return 'Idle';
  }

  get tone(): 'idle' | 'active' | 'error' {
    if (this.runError || this.failedToolCount > 0 || this.taskState?.status === 'failed') {
      return 'error';
    }
    if (this.active || this.runningTool) {
      return 'active';
    }
    return 'idle';
  }

  toggle(): void {
    this.expandedChange.emit(!this.expanded);
  }

  close(): void {
    if (this.expanded) {
      this.expandedChange.emit(false);
    }
  }

  @HostListener('document:keydown.escape')
  onEscape(): void {
    this.close();
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
}

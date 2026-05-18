import { CommonModule } from '@angular/common';
import { Component, Input } from '@angular/core';

export interface ModelStatsRow {
  model: string;
  provider: string;
  local: boolean;
  assignedRoles: string[];
}

@Component({
  selector: 'app-model-stats-panel',
  standalone: true,
  imports: [CommonModule],
  templateUrl: './model-stats-panel.component.html',
  styleUrl: './model-stats-panel.component.css',
})
export class ModelStatsPanelComponent {
  @Input({ required: true }) rows: ModelStatsRow[] = [];
  @Input() isLoading = false;

  get dutyRows(): Array<{ duty: 'parser' | 'chat' | 'agent'; row: ModelStatsRow | null }> {
    const duties: Array<'parser' | 'chat' | 'agent'> = ['parser', 'chat', 'agent'];
    return duties.map((duty) => ({
      duty,
      row: this.rows.find((row) => row.assignedRoles.includes(duty)) ?? null,
    }));
  }

  dutyLabel(duty: 'parser' | 'chat' | 'agent'): string {
    if (duty === 'parser') {
      return 'Parser';
    }
    if (duty === 'chat') {
      return 'Chat';
    }
    return 'Agent';
  }

  statusText(row: ModelStatsRow | null): string {
    if (!row) {
      return 'Not assigned';
    }
    return 'Assigned';
  }
}

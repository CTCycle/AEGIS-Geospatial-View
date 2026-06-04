import { CommonModule } from '@angular/common';
import { Component, Input } from '@angular/core';

import { ModelRole, SelectedModelStat, modelRoleLabel } from '../core/model-selection';

@Component({
  selector: 'app-model-stats-panel',
  standalone: true,
  imports: [CommonModule],
  templateUrl: './model-stats-panel.component.html',
  styleUrl: './model-stats-panel.component.css',
})
export class ModelStatsPanelComponent {
  @Input({ required: true }) rows: readonly SelectedModelStat[] = [];
  @Input() isLoading = false;

  get dutyRows(): Array<{ duty: ModelRole; row: SelectedModelStat | null }> {
    const duties: readonly ModelRole[] = ['parser', 'chat', 'agent'];
    return duties.map((duty) => ({
      duty,
      row: this.rows.find((row) => row.assignedRoles.includes(duty)) ?? null,
    }));
  }

  dutyLabel(duty: ModelRole): string {
    return modelRoleLabel(duty);
  }

  statusText(row: SelectedModelStat | null): string {
    if (!row) {
      return 'Not assigned';
    }
    return 'Assigned';
  }
}

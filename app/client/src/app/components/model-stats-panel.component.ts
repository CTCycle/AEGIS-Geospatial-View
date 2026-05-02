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
}
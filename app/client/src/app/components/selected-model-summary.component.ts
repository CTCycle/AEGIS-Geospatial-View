import { CommonModule } from '@angular/common';
import { Component, Input } from '@angular/core';

import { SelectedAgentModelSummary } from '../core/model-selection';

@Component({
  selector: 'app-selected-model-summary',
  standalone: true,
  imports: [CommonModule],
  templateUrl: './selected-model-summary.component.html',
  styleUrl: './selected-model-summary.component.css',
  host: {
    style: 'display: flex; flex: 1 1 auto; min-height: 100%;',
  },
})
export class SelectedModelSummaryComponent {
  @Input() summary: SelectedAgentModelSummary | null = null;
  @Input() isLoading = false;

  boolLabel(value: boolean): string {
    return value ? 'Yes' : 'No';
  }
}

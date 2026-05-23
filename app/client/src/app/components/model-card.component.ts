import { Component, EventEmitter, Input, Output } from '@angular/core';

import { ModelRole } from '../core/model-selection';
import { ModelCardDescriptor, ModelSettingsResponse } from '../core/types';
import { ModelRoleActionsComponent } from './model-role-actions.component';

@Component({
  selector: 'article[appModelCard]',
  standalone: true,
  imports: [ModelRoleActionsComponent],
  templateUrl: './model-card.component.html',
  styleUrl: './model-card.component.css',
  host: {
    class: 'model-card',
    '[class.model-card--local]': 'isLocal',
  },
})
export class ModelCardComponent {
  @Input({ required: true }) model!: ModelCardDescriptor;
  @Input({ required: true }) settings!: ModelSettingsResponse;
  @Input({ required: true }) description = '';
  @Input() isLocal = false;
  @Input() requiresPull = false;

  @Output() roleSelected = new EventEmitter<ModelRole>();
  @Output() pullRequested = new EventEmitter<ModelCardDescriptor>();

  onRoleSelected(role: ModelRole): void {
    this.roleSelected.emit(role);
  }

  onPullRequested(): void {
    this.pullRequested.emit(this.model);
  }
}

import { CommonModule } from '@angular/common';
import { Component, EventEmitter, Input, Output } from '@angular/core';

import { ModelRole, isModelSelectedForRole } from '../core/model-selection';
import { ModelCardDescriptor, ModelSettingsResponse } from '../core/types';

const ROLE_BUTTON_ORDER: ModelRole[] = ['parser', 'chat', 'agent'];

@Component({
  selector: 'app-model-role-actions',
  standalone: true,
  imports: [CommonModule],
  templateUrl: './model-role-actions.component.html',
  styleUrl: './model-role-actions.component.css',
})
export class ModelRoleActionsComponent {
  @Input({ required: true }) model!: ModelCardDescriptor;
  @Input({ required: true }) settings!: ModelSettingsResponse;
  @Input() requiresPull = false;
  @Output() selectRole = new EventEmitter<ModelRole>();

  readonly roles = ROLE_BUTTON_ORDER;

  isSelected(role: ModelRole): boolean {
    return isModelSelectedForRole(this.settings, role, this.model);
  }

  getLabel(role: ModelRole): string {
    const selected = this.isSelected(role);
    if (role === 'parser') {
      if (this.requiresPull && !selected) {
        return 'Pull & use for parser';
      }
      return selected ? 'Parser model' : 'Use for parser';
    }
    if (role === 'chat') {
      if (this.requiresPull && !selected) {
        return 'Pull & use for chat';
      }
      return selected ? 'Chat model' : 'Use for chat';
    }
    if (this.requiresPull && !selected) {
      return 'Pull & use for agent';
    }
    return selected ? 'Agent model' : 'Use for agent';
  }

  onSelect(role: ModelRole): void {
    this.selectRole.emit(role);
  }
}

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

  roleName(role: ModelRole): string {
    if (role === 'parser') {
      return 'Parser';
    }
    if (role === 'chat') {
      return 'Chat';
    }
    return 'Agent';
  }

  roleHint(role: ModelRole): string {
    const selected = this.isSelected(role);
    if (selected) {
      return 'Assigned';
    }
    if (this.requiresPull) {
      return 'Pull + assign';
    }
    return 'Assign';
  }

  roleIcon(role: ModelRole): string {
    if (role === 'parser') {
      return 'parser';
    }
    if (role === 'chat') {
      return 'chat';
    }
    return 'agent';
  }

  onSelect(role: ModelRole): void {
    this.selectRole.emit(role);
  }
}

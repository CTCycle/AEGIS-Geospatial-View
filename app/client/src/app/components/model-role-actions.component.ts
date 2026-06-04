import { CommonModule } from '@angular/common';
import { Component, EventEmitter, Input, Output } from '@angular/core';

import { MODEL_ROLES, ModelRole, isModelSelectedForRole, roleDisabledReason } from '../core/model-selection';
import { ModelCardDescriptor, ModelSettingsResponse } from '../core/types';

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

  readonly roles = MODEL_ROLES;

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

  roleIcon(role: ModelRole): string {
    if (role === 'parser') {
      return 'parser';
    }
    if (role === 'chat') {
      return 'chat';
    }
    return 'agent';
  }

  roleTitle(role: ModelRole): string {
    const reason = this.disabledReason(role);
    return reason ? `${this.roleName(role)} unavailable. ${reason}` : this.roleName(role);
  }

  disabledReason(role: ModelRole): string | null {
    if (this.requiresPull) {
      return 'Pull this model before assigning a role.';
    }
    return roleDisabledReason(this.model, role);
  }

  isDisabled(role: ModelRole): boolean {
    return this.disabledReason(role) !== null;
  }

  onSelect(role: ModelRole): void {
    if (this.isDisabled(role)) {
      return;
    }
    this.selectRole.emit(role);
  }
}

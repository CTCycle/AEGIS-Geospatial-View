import { Component, EventEmitter, Input, Output } from '@angular/core';
import { FormsModule } from '@angular/forms';

type CredentialHealth = 'healthy' | 'unreadable' | string | null;

@Component({
  selector: 'app-settings-api-key-field',
  standalone: true,
  imports: [FormsModule],
  templateUrl: './settings-api-key-field.component.html',
})
export class SettingsApiKeyFieldComponent {
  @Input({ required: true }) label = '';
  @Input({ required: true }) inputName = '';
  @Input({ required: true }) placeholder = '';
  @Input() value = '';
  @Input() hint = '';
  @Input() configured = false;
  @Input() credentialHealth: CredentialHealth = null;
  @Input() validationError: string | undefined;
  @Input() providerSection = false;

  @Output() valueChange = new EventEmitter<string>();

  get labelText(): string {
    return `${this.label} API key ${this.configured ? '(Configured)' : '(Not configured)'}`;
  }

  onValueChange(value: string): void {
    this.valueChange.emit(value);
  }
}

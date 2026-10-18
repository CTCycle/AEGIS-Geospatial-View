import { Component, EventEmitter, Input, Output, ChangeDetectionStrategy } from '@angular/core';
import { FormsModule } from '@angular/forms';

type CredentialHealth = 'healthy' | 'unreadable' | string | null;

@Component({
  selector: 'app-settings-api-key-field',
  standalone: true,
  imports: [FormsModule],
  changeDetection: ChangeDetectionStrategy.Eager,
  templateUrl: './settings-api-key-field.component.html',
  styleUrl: './settings-api-key-field.component.css',
})
export class SettingsApiKeyFieldComponent {
  @Input({ required: true }) label = '';
  @Input({ required: true }) inputName = '';
  @Input({ required: true }) placeholder = '';
  @Input() value = '';
  @Input() hint = '';
  @Input() credentialHealth: CredentialHealth = null;
  @Input() validationError: string | undefined;

  @Output() valueChange = new EventEmitter<string>();

  get labelText(): string {
    return `${this.label} API key`;
  }

  get inputId(): string {
    return `settings-key-${this.inputName}`;
  }

  get descriptionIds(): string | null {
    const ids: string[] = [];
    if (this.hint) {
      ids.push(`${this.inputId}-hint`);
    }
    if (this.credentialHealth) {
      ids.push(`${this.inputId}-health`);
    }
    if (this.validationError) {
      ids.push(`${this.inputId}-error`);
    }
    return ids.length ? ids.join(' ') : null;
  }

  onValueChange(value: string): void {
    this.valueChange.emit(value);
  }
}

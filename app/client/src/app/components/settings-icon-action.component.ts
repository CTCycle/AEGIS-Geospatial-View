import { Component, EventEmitter, Input, Output, ChangeDetectionStrategy } from '@angular/core';

@Component({
  selector: 'app-settings-icon-action',
  standalone: true,
  templateUrl: './settings-icon-action.component.html',
  changeDetection: ChangeDetectionStrategy.Eager,
  styleUrl: './settings-icon-action.component.css',
})
export class SettingsIconActionComponent {
  @Input({ required: true }) ariaLabel!: string;
  @Input({ required: true }) title!: string;
  @Output() buttonClick = new EventEmitter<void>();

  onClick(): void {
    this.buttonClick.emit();
  }
}

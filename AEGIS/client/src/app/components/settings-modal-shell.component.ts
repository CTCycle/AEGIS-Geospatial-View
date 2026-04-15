import { Component, EventEmitter, Input, Output } from '@angular/core';

@Component({
  selector: 'app-settings-modal-shell',
  standalone: true,
  templateUrl: './settings-modal-shell.component.html',
  styleUrl: './settings-modal-shell.component.css',
})
export class SettingsModalShellComponent {
  @Input({ required: true }) title!: string;
  @Input({ required: true }) ariaLabel!: string;

  @Output() requestClose = new EventEmitter<void>();

  onBackdropClick(event: MouseEvent): void {
    if ((event.target as HTMLElement).classList.contains('settings-modal-backdrop')) {
      this.requestClose.emit();
    }
  }
}

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
  @Input() panelClass = '';
  @Input() closeOnBackdrop = true;
  @Input() showHeader = true;

  @Output() requestClose = new EventEmitter<void>();

  onBackdropClick(event: MouseEvent): void {
    if (this.closeOnBackdrop && event.target === event.currentTarget) {
      this.requestClose.emit();
    }
  }
}

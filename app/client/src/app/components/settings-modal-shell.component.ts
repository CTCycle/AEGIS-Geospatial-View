import {
  AfterViewInit,
  ChangeDetectionStrategy,
  Component,
  ElementRef,
  EventEmitter,
  HostListener,
  Input,
  OnDestroy,
  Output,
  ViewChild,
} from '@angular/core';

@Component({
  selector: 'app-settings-modal-shell',
  standalone: true,
  templateUrl: './settings-modal-shell.component.html',
  changeDetection: ChangeDetectionStrategy.Eager,
  styleUrl: './settings-modal-shell.component.css',
})
export class SettingsModalShellComponent implements AfterViewInit, OnDestroy {
  @ViewChild('dialog', { static: true }) dialogRef!: ElementRef<HTMLElement>;

  @Input({ required: true }) title!: string;
  @Input({ required: true }) ariaLabel!: string;
  @Input() panelClass = '';
  @Input() closeOnBackdrop = true;
  @Input() showHeader = true;

  @Output() requestClose = new EventEmitter<void>();

  private previouslyFocusedElement: HTMLElement | null = null;

  ngAfterViewInit(): void {
    this.previouslyFocusedElement = document.activeElement instanceof HTMLElement
      ? document.activeElement
      : null;
    queueMicrotask(() => this.focusableElements()[0]?.focus());
  }

  ngOnDestroy(): void {
    if (this.previouslyFocusedElement?.isConnected) {
      this.previouslyFocusedElement.focus();
    }
  }

  @HostListener('document:keydown', ['$event'])
  onDocumentKeydown(event: KeyboardEvent): void {
    if (event.key === 'Escape') {
      event.preventDefault();
      this.requestClose.emit();
      return;
    }
    if (event.key !== 'Tab') {
      return;
    }

    const focusable = this.focusableElements();
    if (focusable.length === 0) {
      event.preventDefault();
      return;
    }
    const activeElement = document.activeElement;
    const activeIndex = focusable.indexOf(activeElement as HTMLElement);
    if (activeIndex === -1 || (!event.shiftKey && activeIndex === focusable.length - 1)) {
      event.preventDefault();
      focusable[0].focus();
    } else if (event.shiftKey && activeIndex === 0) {
      event.preventDefault();
      focusable.at(-1)?.focus();
    }
  }

  onBackdropClick(event: MouseEvent): void {
    if (this.closeOnBackdrop && event.target === event.currentTarget) {
      this.requestClose.emit();
    }
  }

  private focusableElements(): HTMLElement[] {
    return Array.from(this.dialogRef.nativeElement.querySelectorAll<HTMLElement>(
      'button:not([disabled]), [href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])',
    )).filter((element) => !element.hasAttribute('hidden'));
  }
}

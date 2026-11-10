import { ChangeDetectionStrategy, Component, ElementRef, EventEmitter, Input, OnInit, Output, inject } from '@angular/core';

@Component({
  selector: 'app-clarification-popover',
  standalone: true,
  templateUrl: './clarification-popover.component.html',
  styleUrl: './clarification-popover.component.css',
  changeDetection: ChangeDetectionStrategy.Eager,
})
export class ClarificationPopoverComponent implements OnInit {
  private readonly host = inject<ElementRef<HTMLElement>>(ElementRef);

  @Input() options: string[] = [];

  @Output() readonly optionSelected = new EventEmitter<string>();
  /** Escape was pressed inside the popover; the owner returns focus to the composer. */
  @Output() readonly dismissed = new EventEmitter<void>();
  /** The popover took layout space; the owner keeps the transcript end in view. */
  @Output() readonly shown = new EventEmitter<void>();

  ngOnInit(): void {
    this.shown.emit();
  }

  onKeydown(event: KeyboardEvent): void {
    if (event.key === 'Escape') {
      event.preventDefault();
      this.dismissed.emit();
      return;
    }
    const step = ({ ArrowRight: 1, ArrowDown: 1, ArrowLeft: -1, ArrowUp: -1 } as Record<string, number>)[event.key];
    if (step === undefined) {
      return;
    }
    const buttons = Array.from(this.host.nativeElement.querySelectorAll<HTMLButtonElement>('button'));
    const index = buttons.indexOf(event.target as HTMLButtonElement);
    if (index < 0) {
      return;
    }
    event.preventDefault();
    buttons[(index + step + buttons.length) % buttons.length].focus();
  }
}

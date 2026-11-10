import { ComponentFixture, TestBed } from '@angular/core/testing';

import { ClarificationPopoverComponent } from './clarification-popover.component';

describe('components/clarification-popover.component', () => {
  let fixture: ComponentFixture<ClarificationPopoverComponent>;

  const buttons = (): HTMLButtonElement[] =>
    Array.from(fixture.nativeElement.querySelectorAll('button')) as HTMLButtonElement[];

  const press = (button: HTMLButtonElement, key: string): void => {
    button.dispatchEvent(new KeyboardEvent('keydown', { key, bubbles: true, cancelable: true }));
  };

  beforeEach(async () => {
    await TestBed.configureTestingModule({ imports: [ClarificationPopoverComponent] }).compileComponents();
    fixture = TestBed.createComponent(ClarificationPopoverComponent);
    fixture.componentInstance.options = ['Roads', 'Airports', 'Buildings'];
    document.body.appendChild(fixture.nativeElement);
    fixture.detectChanges();
  });

  afterEach(() => fixture.nativeElement.remove());

  it('renders each option as a labelled button and emits the chosen one', () => {
    const selected: string[] = [];
    fixture.componentInstance.optionSelected.subscribe((option) => selected.push(option));

    expect(fixture.nativeElement.querySelector('[role="group"]').getAttribute('aria-label')).toBe('Suggested answers');
    expect(buttons().map((button) => button.textContent?.trim())).toEqual(['Roads', 'Airports', 'Buildings']);

    buttons()[1].click();
    expect(selected).toEqual(['Airports']);
  });

  it('moves focus with the arrow keys, wrapping at both ends, and reports Escape', () => {
    const dismissed = jasmine.createSpy('dismissed');
    fixture.componentInstance.dismissed.subscribe(dismissed);
    const [first, second, third] = buttons();

    first.focus();
    press(first, 'ArrowRight');
    expect(document.activeElement).toBe(second);
    press(second, 'ArrowLeft');
    press(first, 'ArrowUp');
    expect(document.activeElement).toBe(third);
    press(third, 'ArrowDown');
    expect(document.activeElement).toBe(first);

    press(first, 'Escape');
    expect(dismissed).toHaveBeenCalledTimes(1);
  });
});

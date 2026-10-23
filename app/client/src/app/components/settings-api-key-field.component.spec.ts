import { ComponentFixture, TestBed } from '@angular/core/testing';

import { SettingsApiKeyFieldComponent } from './settings-api-key-field.component';

describe('SettingsApiKeyFieldComponent', () => {
  let fixture: ComponentFixture<SettingsApiKeyFieldComponent>;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [SettingsApiKeyFieldComponent],
    }).compileComponents();

    fixture = TestBed.createComponent(SettingsApiKeyFieldComponent);
    fixture.componentInstance.label = 'OpenCode Go';
    fixture.componentInstance.inputName = 'opencode-go_api_key';
    fixture.componentInstance.placeholder = 'OpenCode API key';
  });

  it('keeps stored credentials masked and out of the input value', () => {
    fixture.componentInstance.credentialHealth = 'healthy';
    fixture.detectChanges();

    const input = fixture.nativeElement.querySelector('input') as HTMLInputElement;
    expect(input.type).toBe('password');
    expect(input.autocomplete).toBe('off');
    expect(input.value).toBe('');
    expect(fixture.nativeElement.textContent).toContain('OpenCode Go API key');
    expect(fixture.nativeElement.textContent).not.toContain('(Configured)');
    expect(fixture.nativeElement.textContent).toContain('Saved key is readable.');
  });

  it('exposes invalid styling and validation text without revealing a key', () => {
    fixture.componentInstance.value = '';
    fixture.componentInstance.validationError = 'Enter a key before saving.';
    fixture.detectChanges();

    const input = fixture.nativeElement.querySelector('input') as HTMLInputElement;
    expect(input.classList.contains('input-invalid')).toBeTrue();
    expect(fixture.nativeElement.textContent).toContain('Enter a key before saving.');
    expect(input.value).toBe('');
  });

  it('references only the health message elements that are rendered', () => {
    fixture.componentInstance.credentialHealth = 'missing';
    fixture.detectChanges();

    const input = fixture.nativeElement.querySelector('input') as HTMLInputElement;
    expect(input.hasAttribute('aria-describedby')).toBeFalse();

    fixture.componentInstance.credentialHealth = 'healthy';
    fixture.detectChanges();
    const describedBy = input.getAttribute('aria-describedby') ?? '';
    expect(fixture.nativeElement.querySelector(`#${describedBy}`)).not.toBeNull();
  });

  it('emits commit from Save key and Enter only while the draft is savable', () => {
    const commits: number[] = [];
    fixture.componentInstance.commit.subscribe(() => commits.push(1));
    fixture.detectChanges();
    const input = fixture.nativeElement.querySelector('input') as HTMLInputElement;
    const button = fixture.nativeElement.querySelector('button') as HTMLButtonElement;
    expect(button.disabled).toBeTrue();
    input.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter' }));
    input.dispatchEvent(new Event('change'));
    expect(commits.length).toBe(0);

    fixture.componentInstance.value = 'sk-draft-value';
    fixture.detectChanges();
    expect(button.disabled).toBeFalse();
    input.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter' }));
    button.click();
    expect(commits.length).toBe(2);

    fixture.componentInstance.validationError = 'Invalid key.';
    fixture.detectChanges();
    expect(button.disabled).toBeTrue();
  });
});

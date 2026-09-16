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
    fixture.componentInstance.configured = true;
    fixture.componentInstance.credentialHealth = 'healthy';
    fixture.detectChanges();

    const input = fixture.nativeElement.querySelector('input') as HTMLInputElement;
    expect(input.type).toBe('password');
    expect(input.autocomplete).toBe('off');
    expect(input.value).toBe('');
    expect(fixture.nativeElement.textContent).toContain('OpenCode Go API key (Configured)');
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
});

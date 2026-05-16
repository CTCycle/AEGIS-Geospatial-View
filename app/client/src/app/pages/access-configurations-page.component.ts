import { CommonModule } from '@angular/common';
import { ChangeDetectorRef, Component, OnInit } from '@angular/core';
import { FormControl, FormGroup, ReactiveFormsModule } from '@angular/forms';

import { ApiClientService } from '../core/api-client.service';
import {
  ModelSettingsResponse,
  ProviderAccountSetup,
  ProviderCredentialValidationResult,
} from '../core/types';

@Component({
  selector: 'app-access-configurations-page',
  standalone: true,
  imports: [CommonModule, ReactiveFormsModule],
  templateUrl: './access-configurations-page.component.html',
  styleUrl: './access-configurations-page.component.css',
})
export class AccessConfigurationsPageComponent implements OnInit {
  settings?: ModelSettingsResponse;
  statusText = 'Loading access configuration';
  accountSetups: ProviderAccountSetup[] = [];
  selectedSetup: ProviderAccountSetup | null = null;
  activeStepIndex = 0;
  credentialForm = new FormGroup<Record<string, FormControl<string>>>({});
  validationResult: ProviderCredentialValidationResult | null = null;
  isValidating = false;
  isSaving = false;

  readonly wizardSteps = [
    'Overview',
    'Create/sign in',
    'Create project/application',
    'Create/restrict key',
    'Paste key',
    'Validate',
    'Save',
  ];

  constructor(
    private readonly apiClient: ApiClientService,
    private readonly changeDetector: ChangeDetectorRef,
  ) {}

  async ngOnInit(): Promise<void> {
    await Promise.all([this.loadAccessConfigurations(), this.loadAccountSetups()]);
  }

  async loadAccessConfigurations(): Promise<void> {
    try {
      this.settings = await this.apiClient.fetchChatSettings();
      this.statusText = 'Default workflow uses free and open providers. Optional keys are only used when configured.';
    } catch {
      this.statusText = 'Could not load access configuration.';
    } finally {
      this.changeDetector.detectChanges();
    }
  }

  async loadAccountSetups(): Promise<void> {
    try {
      this.accountSetups = await this.apiClient.getProviderAccountSetups();
      if (!this.selectedSetup && this.accountSetups.length) {
        this.selectProvider(this.accountSetups[0].provider_id);
      }
    } catch {
      this.statusText = 'Could not load provider setup guides.';
    } finally {
      this.changeDetector.detectChanges();
    }
  }

  selectProvider(providerId: string): void {
    const setup = this.accountSetups.find((item) => item.provider_id === providerId) ?? null;
    this.selectedSetup = setup;
    this.activeStepIndex = 0;
    this.validationResult = null;
    const controls: Record<string, FormControl<string>> = {};
    setup?.credential_fields.forEach((field) => {
      controls[field.name] = new FormControl('', { nonNullable: true });
    });
    this.credentialForm = new FormGroup(controls);
  }

  goToStep(index: number): void {
    this.activeStepIndex = Math.min(Math.max(index, 0), this.wizardSteps.length - 1);
  }

  nextStep(): void {
    this.goToStep(this.activeStepIndex + 1);
  }

  previousStep(): void {
    this.goToStep(this.activeStepIndex - 1);
  }

  openSetupUrl(url: string | null | undefined): void {
    if (!url) {
      return;
    }
    window.open(url, '_blank', 'noopener,noreferrer');
  }

  async validateCredentials(): Promise<void> {
    if (!this.selectedSetup || this.selectedSetup.mode === 'not_required' || this.isValidating) {
      return;
    }
    this.isValidating = true;
    this.validationResult = null;
    try {
      this.validationResult = await this.apiClient.validateProviderCredentials(
        this.selectedSetup.provider_id,
        this.credentialForm.getRawValue(),
      );
      this.statusText = this.validationResult.message;
    } catch {
      this.validationResult = {
        provider_id: this.selectedSetup.provider_id,
        valid: false,
        status: 'error',
        message: 'Credential validation request failed.',
      };
      this.statusText = this.validationResult.message;
    } finally {
      this.isValidating = false;
      this.changeDetector.detectChanges();
    }
  }

  async saveCredentials(): Promise<void> {
    if (!this.selectedSetup || !this.settings || this.isSaving) {
      return;
    }
    if (this.selectedSetup.mode === 'not_required') {
      this.statusText = 'No access key is required for this provider.';
      return;
    }
    if (!this.validationResult?.valid) {
      this.statusText = 'Validate the key successfully before saving it.';
      return;
    }
    const credentials = this.credentialForm.getRawValue();
    this.isSaving = true;
    try {
      this.settings = await this.apiClient.updateChatSettings({
        active_provider_mode: this.settings.active_provider_mode,
        chat_model_provider: this.settings.chat_model_provider,
        chat_model_name: this.settings.chat_model_name,
        parser_model_provider: this.settings.parser_model_provider,
        parser_model_name: this.settings.parser_model_name,
        agent_model_provider: this.settings.agent_model_provider,
        agent_model_name: this.settings.agent_model_name,
        ollama_url: this.settings.ollama_url,
        openai_base_url: this.settings.openai_base_url,
        google_base_url: this.settings.google_base_url,
        credentials: {
          [this.selectedSetup.provider_id]: { api_key: credentials.api_key },
        },
      });
      this.credentialForm.reset();
      this.statusText = `${this.providerName(this.selectedSetup)} key saved.`;
    } catch {
      this.statusText = `Could not update ${this.providerName(this.selectedSetup)} access.`;
    } finally {
      this.isSaving = false;
      this.changeDetector.detectChanges();
    }
  }

  configured(setup: ProviderAccountSetup): boolean {
    if (setup.mode === 'not_required') {
      return true;
    }
    return Boolean(this.settings?.credentials?.[setup.provider_id]?.['api_key']);
  }

  validationStatus(setup: ProviderAccountSetup): string {
    if (setup.mode === 'not_required') {
      return 'no key required';
    }
    const status = this.settings?.credential_health?.[setup.provider_id]?.['api_key'];
    if (status === 'healthy' || status === 'stored') {
      return 'stored (not validated)';
    }
    return status ?? (this.configured(setup) ? 'stored (not validated)' : 'not configured');
  }

  maskConfiguredCredential(setup: ProviderAccountSetup): string {
    return this.configured(setup) && setup.mode === 'manual' ? 'Saved as encrypted local credential' : 'Not saved';
  }

  providerName(setup: ProviderAccountSetup): string {
    return setup.provider_id
      .split('_')
      .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
      .join(' ');
  }
}

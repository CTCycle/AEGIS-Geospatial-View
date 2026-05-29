import { CommonModule } from '@angular/common';
import { Component, OnInit } from '@angular/core';
import { FormsModule } from '@angular/forms';

import { SettingsModalShellComponent } from '../components/settings-modal-shell.component';
import { ApiClientService } from '../core/api-client.service';
import { buildCredentialUpdateRequest } from '../core/chat-settings-update';
import { GeospatialProviderAccountSetup, ModelSettingsResponse } from '../core/types';

type GeoProviderId = string;

interface GeoProviderAccess {
  id: GeoProviderId;
  name: string;
  purpose: string;
  placeholder: string;
  docsUrl: string;
}

@Component({
  selector: 'app-access-configurations-page',
  standalone: true,
  imports: [CommonModule, FormsModule, SettingsModalShellComponent],
  templateUrl: './access-configurations-page.component.html',
  styleUrl: './access-configurations-page.component.css',
})
export class AccessConfigurationsPageComponent implements OnInit {
  settings?: ModelSettingsResponse;
  statusText = 'Loading access configuration';
  isSaving = false;
  isLoadingAccountSetups = false;
  drafts: Record<GeoProviderId, string> = {};
  providerAccountSetups: GeospatialProviderAccountSetup[] = [];
  selectedProviderAccountSetup?: GeospatialProviderAccountSetup;
  isSignupModalOpen = false;
  signupModalError = '';
  signupKeyInput = '';

  providers: GeoProviderAccess[] = [];

  constructor(
    private readonly apiClient: ApiClientService,
  ) {}

  async ngOnInit(): Promise<void> {
    await Promise.all([this.loadSettings(), this.loadProviderAccountSetups()]);
  }

  configured(provider: GeoProviderId): boolean {
    return Boolean(this.settings?.credentials?.[provider]?.['api_key']);
  }

  health(provider: GeoProviderId): string {
    const status = this.settings?.credential_health?.[provider]?.['api_key'];
    if (status === 'healthy' || status === 'stored') {
      return 'stored (not validated)';
    }
    return status ?? (this.configured(provider) ? 'stored (not validated)' : 'not configured');
  }

  async saveProvider(provider: GeoProviderId): Promise<void> {
    if (!this.settings || this.isSaving) {
      return;
    }
    const value = (this.drafts[provider] ?? '').trim();
    if (!value) {
      this.statusText = `Enter a ${provider} API key before saving, or clear the saved key.`;
      return;
    }
    if (await this.persistCredential(provider, value)) {
      this.drafts[provider] = '';
      this.statusText = `${this.providerName(provider)} key saved. Provider access has not been validated.`;
    }
  }

  async clearProvider(provider: GeoProviderId): Promise<void> {
    if (!this.settings || this.isSaving) {
      return;
    }
    if (await this.persistCredential(provider, '')) {
      this.drafts[provider] = '';
      this.statusText = `${this.providerName(provider)} key cleared. Optional capabilities are disabled.`;
    }
  }

  async loadProviderAccountSetups(): Promise<void> {
    this.isLoadingAccountSetups = true;
    try {
      const response = await this.apiClient.fetchGeospatialProviderAccountSetups();
      this.providerAccountSetups = response.providers.filter((setup) => setup.requiresCredentials);
      this.providers = this.providerAccountSetups.map((setup) => this.providerFromSetup(setup));
      this.providerAccountSetups.forEach((setup) => {
        this.drafts[setup.credentialStorageKey] = this.drafts[setup.credentialStorageKey] ?? '';
      });
    } catch {
      this.statusText = 'Could not load guided provider setup metadata.';
    } finally {
      this.isLoadingAccountSetups = false;
    }
  }

  getAccountSetupForProvider(providerKey: string): GeospatialProviderAccountSetup | undefined {
    return this.providerAccountSetups.find(
      (setup) => setup.providerId === providerKey || setup.credentialStorageKey === providerKey,
    );
  }

  canShowSignupTrigger(providerKey: string): boolean {
    return Boolean(this.getAccountSetupForProvider(providerKey));
  }

  openProviderSignup(setup: GeospatialProviderAccountSetup | undefined): void {
    if (!setup) {
      return;
    }
    this.selectedProviderAccountSetup = setup;
    this.signupKeyInput = '';
    this.signupModalError = '';
    this.isSignupModalOpen = true;
  }

  closeProviderSignup(): void {
    this.isSignupModalOpen = false;
    this.selectedProviderAccountSetup = undefined;
    this.signupModalError = '';
    this.signupKeyInput = '';
  }

  openProviderPortal(setup: GeospatialProviderAccountSetup): void {
    const target = setup.automation.developerPortalUrl ?? setup.automation.signupUrl ?? setup.automation.docsUrl ?? setup.docsUrl;
    if (!target) {
      this.signupModalError = 'No provider portal link is available for this setup.';
      return;
    }
    window.open(target, '_blank', 'noreferrer');
  }

  async saveGeneratedCredential(setup: GeospatialProviderAccountSetup): Promise<void> {
    if (setup.automation.support === 'unsupported') {
      this.signupModalError = 'This provider is documentation-only until automation support is verified.';
      return;
    }
    const value = this.signupKeyInput.trim();
    if (!value) {
      this.signupModalError = 'Paste the generated API key before saving.';
      return;
    }
    if (await this.persistCredential(setup.credentialStorageKey, value)) {
      this.signupKeyInput = '';
      this.isSignupModalOpen = false;
      this.selectedProviderAccountSetup = undefined;
      this.statusText = `${setup.name} key saved. Provider access has not been validated.`;
    }
  }

  supportLabel(setup: GeospatialProviderAccountSetup): string {
    const labels: Record<string, string> = {
      agent_assisted: 'Agent-assisted guidance',
      guided_playwright: 'Guided browser setup',
      manual_only: 'Manual setup guidance',
      unsupported: 'Documentation only',
    };
    return labels[setup.automation.support] ?? setup.automation.support;
  }

  private async loadSettings(): Promise<void> {
    try {
      this.settings = await this.apiClient.fetchChatSettings();
      this.statusText = 'Default workflow uses free and open providers. Optional keys are only used when configured.';
    } catch {
      this.statusText = 'Could not load access configuration.';
    }
  }

  private async persistCredential(provider: GeoProviderId, apiKey: string): Promise<boolean> {
    if (!this.settings) {
      return false;
    }
    this.isSaving = true;
    try {
      this.settings = await this.apiClient.updateChatSettings(
        buildCredentialUpdateRequest(this.settings, provider, apiKey),
      );
      return true;
    } catch {
      this.statusText = `Could not update ${this.providerName(provider)} access.`;
      return false;
    } finally {
      this.isSaving = false;
    }
  }

  private providerName(provider: GeoProviderId): string {
    return this.providers.find((item) => item.id === provider)?.name ?? provider;
  }

  private providerFromSetup(setup: GeospatialProviderAccountSetup): GeoProviderAccess {
    return {
      id: setup.credentialStorageKey,
      name: setup.name,
      purpose: `${this.supportLabel(setup)} for credential-gated geospatial capabilities.`,
      placeholder: setup.keyFormatHint ?? `${setup.name} API key`,
      docsUrl: setup.automation.docsUrl ?? setup.docsUrl ?? setup.automation.developerPortalUrl ?? '',
    };
  }
}

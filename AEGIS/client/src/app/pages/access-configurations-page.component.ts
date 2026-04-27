import { CommonModule } from '@angular/common';
import { ChangeDetectorRef, Component, OnInit } from '@angular/core';
import { FormsModule } from '@angular/forms';

import { fetchChatSettings, updateChatSettings } from '../core/api';
import { ModelSettingsResponse } from '../core/types';

type GeoProviderId = 'geoapify' | 'tomtom' | 'google_maps' | 'arcgis';

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
  imports: [CommonModule, FormsModule],
  templateUrl: './access-configurations-page.component.html',
  styleUrl: './access-configurations-page.component.css',
})
export class AccessConfigurationsPageComponent implements OnInit {
  settings?: ModelSettingsResponse;
  statusText = 'Loading access configuration';
  isSaving = false;
  drafts: Record<GeoProviderId, string> = { geoapify: '', tomtom: '', google_maps: '', arcgis: '' };

  readonly providers: GeoProviderAccess[] = [
    {
      id: 'geoapify',
      name: 'Geoapify',
      purpose: 'Optional OSM Bright basemap and Geoapify amenities provider.',
      placeholder: 'Geoapify API key',
      docsUrl: 'https://www.geoapify.com/',
    },
    {
      id: 'tomtom',
      name: 'TomTom',
      purpose: 'Optional traffic and TomTom basemap provider.',
      placeholder: 'TomTom API key',
      docsUrl: 'https://developer.tomtom.com/',
    },
    {
      id: 'google_maps',
      name: 'Google Maps Platform',
      purpose: 'Optional Google Places, commercial POI, and geocoding metadata provider.',
      placeholder: 'Google Maps API key',
      docsUrl: 'https://developers.google.com/maps',
    },
    {
      id: 'arcgis',
      name: 'ArcGIS',
      purpose: 'Optional access token/API key for credentialed ArcGIS portal and REST services.',
      placeholder: 'ArcGIS API key',
      docsUrl: 'https://developers.arcgis.com/',
    },
  ];

  constructor(private readonly changeDetector: ChangeDetectorRef) {}

  async ngOnInit(): Promise<void> {
    await this.loadSettings();
  }

  configured(provider: GeoProviderId): boolean {
    return Boolean(this.settings?.credentials?.[provider]?.['api_key']);
  }

  health(provider: GeoProviderId): string {
    return this.settings?.credential_health?.[provider]?.['api_key'] ?? (this.configured(provider) ? 'unknown' : 'not configured');
  }

  async saveProvider(provider: GeoProviderId): Promise<void> {
    if (!this.settings || this.isSaving) {
      return;
    }
    const value = this.drafts[provider].trim();
    if (!value) {
      this.statusText = `Enter a ${provider} API key before saving, or clear the saved key.`;
      return;
    }
    if (await this.persistCredential(provider, value)) {
      this.drafts[provider] = '';
      this.statusText = `${this.providerName(provider)} key saved. Optional capabilities will become available in the catalog.`;
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

  private async loadSettings(): Promise<void> {
    try {
      this.settings = await fetchChatSettings();
      this.statusText = 'Default workflow uses free and open providers. Optional keys are only used when configured.';
    } catch {
      this.statusText = 'Could not load access configuration.';
    } finally {
      this.changeDetector.detectChanges();
    }
  }

  private async persistCredential(provider: GeoProviderId, apiKey: string): Promise<boolean> {
    if (!this.settings) {
      return false;
    }
    this.isSaving = true;
    try {
      this.settings = await updateChatSettings({
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
          [provider]: { api_key: apiKey },
        },
      });
      return true;
    } catch {
      this.statusText = `Could not update ${this.providerName(provider)} access.`;
      return false;
    } finally {
      this.isSaving = false;
      this.changeDetector.detectChanges();
    }
  }

  private providerName(provider: GeoProviderId): string {
    return this.providers.find((item) => item.id === provider)?.name ?? provider;
  }
}

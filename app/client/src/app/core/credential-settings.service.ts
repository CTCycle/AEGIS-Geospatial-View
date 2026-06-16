import { Injectable } from '@angular/core';

import { ApiClientService } from './api-client.service';
import {
  CloudCredentialDrafts,
  buildCloudCredentialUpdateRequest,
  buildCredentialUpdateRequest,
} from './chat-settings-update';
import { ModelSettingsResponse } from './types';

@Injectable({ providedIn: 'root' })
export class CredentialSettingsService {
  constructor(private readonly apiClient: ApiClientService) {}

  fetchSettings(): Promise<ModelSettingsResponse> {
    return this.apiClient.fetchChatSettings();
  }

  saveProviderCredential(
    settings: ModelSettingsResponse,
    provider: string,
    apiKey: string,
  ): Promise<ModelSettingsResponse> {
    return this.apiClient.updateChatSettings(
      buildCredentialUpdateRequest(settings, provider, apiKey),
    );
  }

  saveCloudCredentials(
    settings: ModelSettingsResponse,
    drafts: CloudCredentialDrafts,
  ): Promise<ModelSettingsResponse> {
    return this.apiClient.updateChatSettings(
      buildCloudCredentialUpdateRequest(settings, drafts),
    );
  }
}

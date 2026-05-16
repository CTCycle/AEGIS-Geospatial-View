import { Injectable } from '@angular/core';

import {
  checkOllamaHealth,
  fetchCatalog,
  fetchChatModels,
  fetchChatSettings,
  fetchGeospatialCameras,
  fetchGeospatialCapabilities,
  fetchGeospatialCredentialStatus,
  fetchGeospatialLayerFeatures,
  fetchGeospatialLayers,
  fetchProviderAccountSetup,
  fetchProviderAccountSetups,
  pullOllamaModel,
  refreshOllamaModels,
  sendChatTurn,
  updateChatSettings,
  validateProviderCredentials,
} from './api';
import {
  CatalogResponse,
  ChatTurnRequest,
  ChatTurnResponse,
  GenericObjectResponse,
  GeospatialCredentialStatus,
  GeospatialProviderPayload,
  ModelCardDescriptor,
  ModelSettingsResponse,
  ModelSettingsUpdateRequest,
  OllamaHealthResponse,
  ProviderAccountSetup,
  ProviderCredentialValidationResult,
} from './types';

@Injectable({ providedIn: 'root' })
export class ApiClientService {
  fetchCatalog(): Promise<CatalogResponse> {
    return fetchCatalog();
  }

  fetchGeospatialCapabilities(): Promise<CatalogResponse> {
    return fetchGeospatialCapabilities();
  }

  fetchGeospatialLayers(): Promise<Pick<CatalogResponse, 'basemaps' | 'overlays' | 'cameras'>> {
    return fetchGeospatialLayers();
  }

  fetchGeospatialLayerFeatures(
    layerId: string,
    params: { bbox?: string; zoom?: number; time?: string } = {},
  ): Promise<GeospatialProviderPayload> {
    return fetchGeospatialLayerFeatures(layerId, params);
  }

  fetchGeospatialCameras(
    params: { bbox?: string; provider?: string; camera_type?: string } = {},
  ): Promise<GeospatialProviderPayload> {
    return fetchGeospatialCameras(params);
  }

  fetchGeospatialCredentialStatus(providerId: string): Promise<GeospatialCredentialStatus> {
    return fetchGeospatialCredentialStatus(providerId);
  }

  getProviderAccountSetups(): Promise<ProviderAccountSetup[]> {
    return fetchProviderAccountSetups();
  }

  getProviderAccountSetup(providerId: string): Promise<ProviderAccountSetup> {
    return fetchProviderAccountSetup(providerId);
  }

  validateProviderCredentials(
    providerId: string,
    credentials: Record<string, string>,
  ): Promise<ProviderCredentialValidationResult> {
    return validateProviderCredentials(providerId, credentials);
  }

  sendChatTurn(payload: ChatTurnRequest): Promise<ChatTurnResponse> {
    return sendChatTurn(payload);
  }

  fetchChatModels(): Promise<{ cloud: ModelCardDescriptor[]; local: ModelCardDescriptor[] }> {
    return fetchChatModels();
  }

  fetchChatSettings(): Promise<ModelSettingsResponse> {
    return fetchChatSettings();
  }

  updateChatSettings(payload: ModelSettingsUpdateRequest): Promise<ModelSettingsResponse> {
    return updateChatSettings(payload);
  }

  refreshOllamaModels(): Promise<GenericObjectResponse> {
    return refreshOllamaModels();
  }

  pullOllamaModel(model: string): Promise<GenericObjectResponse> {
    return pullOllamaModel(model);
  }

  checkOllamaHealth(): Promise<OllamaHealthResponse> {
    return checkOllamaHealth();
  }
}

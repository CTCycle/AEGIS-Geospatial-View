import { Injectable } from '@angular/core';

import {
  checkOllamaHealth,
  createConversation,
  fetchCatalog,
  fetchChatModels,
  fetchConversationSnapshot,
  fetchChatSettings,
  fetchGeospatialCameras,
  fetchGeospatialCredentialStatus,
  fetchGeospatialProviderAccountSetups,
  fetchGeospatialLayerFeatures,
  fetchGeospatialLayers,
  pullOllamaModel,
  refreshOllamaModels,
  sendChatTurn,
  updateChatSettings,
} from './api';
import {
  CatalogResponse,
  ChatTurnRequest,
  ChatTurnResponse,
  ConversationCreateRequest,
  ConversationCreateResponse,
  ConversationSnapshotResponse,
  GenericObjectResponse,
  GeospatialCredentialStatus,
  GeospatialProviderAccountSetupListResponse,
  GeospatialProviderPayload,
  ModelLibraryResponse,
  ModelSettingsResponse,
  ModelSettingsUpdateRequest,
  OllamaHealthResponse,
} from './types';

@Injectable({ providedIn: 'root' })
export class ApiClientService {
  fetchCatalog(): Promise<CatalogResponse> {
    return fetchCatalog();
  }

  fetchGeospatialLayers(): Promise<Pick<CatalogResponse, 'basemaps' | 'overlays' | 'cameras' | 'transit'>> {
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

  fetchGeospatialProviderAccountSetups(): Promise<GeospatialProviderAccountSetupListResponse> {
    return fetchGeospatialProviderAccountSetups();
  }

  sendChatTurn(payload: ChatTurnRequest): Promise<ChatTurnResponse> {
    return sendChatTurn(payload);
  }

  createConversation(payload: ConversationCreateRequest): Promise<ConversationCreateResponse> {
    return createConversation(payload);
  }

  fetchConversationSnapshot(conversationId: string): Promise<ConversationSnapshotResponse> {
    return fetchConversationSnapshot(conversationId);
  }

  fetchChatModels(provider?: 'deepseek' | 'opencode' | 'opencode-go'): Promise<ModelLibraryResponse> {
    return fetchChatModels(provider);
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

import { Injectable } from '@angular/core';

import {
  checkOllamaHealth,
  cancelAgentRun,
  createAgentRun,
  createConversation,
  fetchCatalog,
  fetchChatModels,
  fetchChatSettings,
  fetchGeospatialCameras,
  fetchGeospatialCapabilities,
  fetchGeospatialCredentialStatus,
  fetchGeospatialProviderAccountSetups,
  fetchGeospatialLayerFeatures,
  fetchGeospatialLayers,
  pullOllamaModel,
  refreshOllamaModels,
  sendChatTurn,
  sendRunSteering,
  openRunEventSource,
  updateChatSettings,
} from './api';
import {
  CatalogResponse,
  AgentRunCancelResponse,
  AgentRunCreateRequest,
  AgentRunCreateResponse,
  ChatTurnRequest,
  ChatTurnResponse,
  ConversationCreateRequest,
  ConversationCreateResponse,
  GenericObjectResponse,
  GeospatialCredentialStatus,
  GeospatialProviderAccountSetupListResponse,
  GeospatialProviderPayload,
  ModelCardDescriptor,
  ModelSettingsResponse,
  ModelSettingsUpdateRequest,
  OllamaHealthResponse,
  SteeringMessageRequest,
  SteeringMessageResponse,
} from './types';

@Injectable({ providedIn: 'root' })
export class ApiClientService {
  fetchCatalog(): Promise<CatalogResponse> {
    return fetchCatalog();
  }

  fetchGeospatialCapabilities(): Promise<CatalogResponse> {
    return fetchGeospatialCapabilities();
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

  createAgentRun(conversationId: string, payload: AgentRunCreateRequest): Promise<AgentRunCreateResponse> {
    return createAgentRun(conversationId, payload);
  }

  sendRunSteering(
    conversationId: string,
    runId: string,
    payload: SteeringMessageRequest,
  ): Promise<SteeringMessageResponse> {
    return sendRunSteering(conversationId, runId, payload);
  }

  cancelAgentRun(conversationId: string, runId: string): Promise<AgentRunCancelResponse> {
    return cancelAgentRun(conversationId, runId);
  }

  openRunEventSource(conversationId: string, runId: string, afterEventId?: string): EventSource {
    return openRunEventSource(conversationId, runId, afterEventId);
  }

  fetchChatModels(provider?: 'deepseek'): Promise<{ cloud: ModelCardDescriptor[]; local: ModelCardDescriptor[] }> {
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

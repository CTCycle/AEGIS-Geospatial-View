import { Injectable } from '@angular/core';

import {
  checkOllamaHealth,
  fetchCatalog,
  fetchChatModels,
  fetchChatSettings,
  pullOllamaModel,
  refreshOllamaModels,
  sendChatTurn,
  updateChatSettings,
} from './api';
import {
  CatalogResponse,
  ChatTurnRequest,
  ChatTurnResponse,
  GenericObjectResponse,
  ModelCardDescriptor,
  ModelSettingsResponse,
  ModelSettingsUpdateRequest,
  OllamaHealthResponse,
} from './types';

@Injectable({ providedIn: 'root' })
export class ApiClientService {
  fetchCatalog(): Promise<CatalogResponse> {
    return fetchCatalog();
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

import { Injectable } from '@angular/core';

import {
  fetchGeospatialCredentialStatus,
  fetchGeospatialLayerFeatures,
  fetchGeospatialLayers,
} from '../core/api';
import {
  CatalogResponse,
  GeospatialCredentialStatus,
  GeospatialProviderPayload,
} from '../core/types';

@Injectable({ providedIn: 'root' })
export class GeospatialLayerService {
  listLayers(): Promise<Pick<CatalogResponse, 'basemaps' | 'overlays' | 'cameras' | 'transit'>> {
    return fetchGeospatialLayers();
  }

  fetchFeatures(
    layerId: string,
    params: { bbox?: string; zoom?: number; time?: string; live?: boolean; incidents?: boolean } = {},
  ): Promise<GeospatialProviderPayload> {
    return fetchGeospatialLayerFeatures(layerId, params);
  }

  credentialStatus(providerId: string): Promise<GeospatialCredentialStatus> {
    return fetchGeospatialCredentialStatus(providerId);
  }
}

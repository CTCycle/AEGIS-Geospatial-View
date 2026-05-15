import { Injectable } from '@angular/core';

import { fetchGeospatialCameraDetail, fetchGeospatialCameras } from '../core/api';
import { GeospatialProviderPayload } from '../core/types';

@Injectable({ providedIn: 'root' })
export class GeospatialCameraService {
  fetchCameras(
    params: { bbox?: string; provider?: string; camera_type?: string } = {},
  ): Promise<GeospatialProviderPayload> {
    return fetchGeospatialCameras(params);
  }

  fetchCamera(cameraId: string): Promise<GeospatialProviderPayload> {
    return fetchGeospatialCameraDetail(cameraId);
  }
}

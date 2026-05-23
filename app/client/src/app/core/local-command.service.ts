import { Injectable } from '@angular/core';

import { ApiClientService } from './api-client.service';
import { formatCapabilitySummary } from './local-command-response';

export type ChatStatus = 'Complete' | 'Failed' | 'Need map session';

export interface LocalCommandController {
  zoomIn(): boolean;
  zoomOut(): boolean;
}

export interface LocalCommandResult {
  handled: boolean;
  assistantMessage?: string;
  status?: ChatStatus;
}

@Injectable({ providedIn: 'root' })
export class LocalCommandService {
  constructor(private readonly apiClient: ApiClientService) {}

  async resolve(message: string, controller: LocalCommandController): Promise<LocalCommandResult> {
    const trimmed = message.trim();
    const normalized = trimmed.toLowerCase();
    const zoomInPattern = /^(zoom\s*in|map\s*zoom\s*in|increase\s+zoom)$/i;
    const zoomOutPattern = /^(zoom\s*out|map\s*zoom\s*out|decrease\s+zoom)$/i;
    if (zoomInPattern.test(trimmed) || zoomOutPattern.test(trimmed)) {
      const isZoomIn = zoomInPattern.test(trimmed);
      const ok = isZoomIn ? controller.zoomIn() : controller.zoomOut();
      return {
        handled: true,
        assistantMessage: ok
          ? `Map ${isZoomIn ? 'zoomed in' : 'zoomed out'}.`
          : 'No active interactive map is available to zoom yet.',
        status: ok ? 'Complete' : 'Need map session',
      };
    }

    if (
      normalized.includes('what can you do')
      || normalized.includes('your capabilities')
      || normalized.includes('available layers')
      || normalized.includes('map types')
    ) {
      try {
        const catalog = await this.apiClient.fetchCatalog();
        const optional = catalog.capabilities
          .filter((item) => item.requires_credentials)
          .map((item) => item.name);
        const sampleBasemaps = (catalog.basemaps ?? []).slice(0, 4).map((item) => item.name).join(', ');
        const sampleOverlays = (catalog.overlays ?? []).slice(0, 6).map((item) => item.name).join(', ');
        const optionalText = optional.length
          ? ` Optional key-based capabilities include ${optional.slice(0, 6).join(', ')}${optional.length > 6 ? ', and more' : ''}; configure those from Access.`
          : '';
        return {
          handled: true,
          assistantMessage: [
            'I can create location-focused map sessions, resolve coordinates, show basemaps, add thematic overlays, run weather, air-quality, POI, and coordinate tools, and adjust the active map with lightweight zoom commands.',
            formatCapabilitySummary(catalog),
            sampleBasemaps ? `Map types include ${sampleBasemaps}.` : '',
            sampleOverlays ? `Layers include ${sampleOverlays}.` : '',
            `The default workflow uses free/open sources; ask for a place plus a goal, such as satellite context, precipitation, air quality, POIs, terrain, or solar potential.${optionalText}`,
          ].filter(Boolean).join(' '),
          status: 'Complete',
        };
      } catch {
        return {
          handled: true,
          assistantMessage: 'I can explain map types, layers, direct tools, access requirements, and how to use them, but the live catalog is unavailable right now.',
          status: 'Failed',
        };
      }
    }

    return { handled: false };
  }
}

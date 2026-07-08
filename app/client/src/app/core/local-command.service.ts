import { Injectable } from '@angular/core';

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
  async resolve(message: string, controller: LocalCommandController): Promise<LocalCommandResult> {
    const trimmed = message.trim();
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

    return { handled: false };
  }
}

import { CatalogResponse } from './types';

export const sanitizeCapabilityName = (value: string): string => value.trim();

export const formatKnownLocations = (locations: string[]): string => {
  const normalized = locations.map((item) => sanitizeCapabilityName(item)).filter(Boolean);
  if (normalized.length === 0) {
    return 'No known locations yet.';
  }
  return `Known locations: ${normalized.join(', ')}.`;
};

export const formatCapabilitySummary = (catalog: CatalogResponse): string => {
  const basemapCount = catalog.basemaps?.length ?? 0;
  const overlayCount = catalog.overlays?.length ?? 0;
  const toolCount = catalog.tools?.length ?? 0;
  return `Current catalog: ${basemapCount} map types, ${overlayCount} layers, and ${toolCount} direct tools.`;
};

export const buildDirectAnswerFromResult = (result: unknown): string => {
  if (typeof result === 'string') {
    return result.trim() || 'No result available.';
  }
  if (result == null) {
    return 'No result available.';
  }
  if (typeof result === 'object') {
    return JSON.stringify(result);
  }
  return String(result);
};
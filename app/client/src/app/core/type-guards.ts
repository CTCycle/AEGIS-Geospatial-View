import type { JsonObject, JsonValue } from './types';

export const isRecord = (value: unknown): value is Record<string, unknown> =>
  typeof value === 'object' && value !== null;

export const isStringArray = (value: unknown): value is string[] =>
  Array.isArray(value) && value.every((item) => typeof item === 'string');

export const isFiniteNumber = (value: unknown): value is number =>
  typeof value === 'number' && Number.isFinite(value);

export const isJsonValue = (value: unknown): value is JsonValue => {
  if (value === null || typeof value === 'string' || typeof value === 'boolean') {
    return true;
  }

  if (isFiniteNumber(value)) {
    return true;
  }

  if (Array.isArray(value)) {
    return value.every((item) => isJsonValue(item));
  }

  return isRecord(value) && Object.values(value).every((item) => isJsonValue(item));
};

export const isJsonObject = (value: unknown): value is JsonObject =>
  isRecord(value) && !Array.isArray(value) && Object.values(value).every((item) => isJsonValue(item));

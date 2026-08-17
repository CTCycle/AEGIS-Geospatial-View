import { mergeModelCards } from './model-selection';
import type { ModelLibraryResponse } from './types';

export type DynamicCloudProvider = 'deepseek' | 'opencode' | 'opencode-go';

export const DYNAMIC_CLOUD_PROVIDERS: readonly DynamicCloudProvider[] = [
  'deepseek',
  'opencode',
  'opencode-go',
];

export const isDynamicCloudProvider = (value: string): value is DynamicCloudProvider =>
  DYNAMIC_CLOUD_PROVIDERS.includes(value as DynamicCloudProvider);

export const mergeModelLibraries = (
  baseLibrary: ModelLibraryResponse,
  dynamicLibrary: ModelLibraryResponse,
  provider: DynamicCloudProvider,
): ModelLibraryResponse => ({
  cloud: mergeModelCards(
    baseLibrary.cloud.filter((model) => model.provider !== provider),
    dynamicLibrary.cloud,
  ),
  local: dynamicLibrary.local.length ? dynamicLibrary.local : baseLibrary.local,
  sources: {
    ...baseLibrary.sources,
    ...dynamicLibrary.sources,
  },
});

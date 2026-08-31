import type { OverlayStateChange } from './types';
import { isRecord } from './type-guards';

export const APP_STATE_STORAGE_KEY = 'aegis:webapp-ui-state:v1';
const STATE_TTL_MS = 6 * 60 * 60 * 1000;
const DEFAULT_CHAT_PANEL_RATIO = 0.3;

export interface PersistedChatPanelState {
  conversationId?: string;
  lastRunSequence: number;
  composerDraft: string;
  transcriptScrollTop: number;
}

export interface PersistedMapState extends OverlayStateChange {}

export interface PersistedChatPageState {
  toolbarWidth: number;
  isToolbarCollapsed: boolean;
  chatPanel: PersistedChatPanelState;
  mapState: PersistedMapState;
  scrollY: number;
}

export interface PersistedSettingsPageState {
  searchText: string;
  scrollY: number;
  modelGridScrollTop: number;
}

export interface PersistedAppState {
  version: 1;
  savedAt: number;
  chatPage: PersistedChatPageState;
  settingsPage: PersistedSettingsPageState;
}

const parseBooleanRecord = (value: unknown): Record<string, boolean> => {
  if (!isRecord(value)) {
    return {};
  }
  return Object.entries(value).reduce<Record<string, boolean>>((acc, [key, entry]) => {
    if (typeof entry === 'boolean') {
      acc[key] = entry;
    }
    return acc;
  }, {});
};

const parseNumberRecord = (value: unknown): Record<string, number> => {
  if (!isRecord(value)) {
    return {};
  }
  return Object.entries(value).reduce<Record<string, number>>((acc, [key, entry]) => {
    if (typeof entry === 'number' && Number.isFinite(entry)) {
      acc[key] = entry;
    }
    return acc;
  }, {});
};

const parseNonNegativeNumber = (value: unknown, fallback: number): number => (
  typeof value === 'number' && Number.isFinite(value) && value >= 0 ? value : fallback
);

const parseRunSequence = (value: unknown): number => (
  typeof value === 'number' && Number.isFinite(value) && value >= 0 ? Math.floor(value) : 0
);

const defaultToolbarWidth = (): number => {
  if (typeof window === 'undefined') {
    return 480;
  }
  const width = Math.round(window.innerWidth * DEFAULT_CHAT_PANEL_RATIO);
  return Math.max(280, Math.min(760, width));
};

export const defaultAppState = (): PersistedAppState => ({
  version: 1,
  savedAt: Date.now(),
  chatPage: {
    toolbarWidth: defaultToolbarWidth(),
    isToolbarCollapsed: false,
    chatPanel: {
      conversationId: undefined,
      lastRunSequence: 0,
      composerDraft: '',
      transcriptScrollTop: 0,
    },
    mapState: {
      overlayVisibility: {},
      overlayOpacity: {},
    },
    scrollY: 0,
  },
  settingsPage: {
    searchText: '',
    scrollY: 0,
    modelGridScrollTop: 0,
  },
});

const discardStoredState = (): void => {
  if (typeof window !== 'undefined') {
    window.sessionStorage.removeItem(APP_STATE_STORAGE_KEY);
  }
};

export const loadPersistedAppState = (): PersistedAppState => {
  if (typeof window === 'undefined') {
    return defaultAppState();
  }

  const raw = window.sessionStorage.getItem(APP_STATE_STORAGE_KEY);
  if (!raw) {
    return defaultAppState();
  }

  try {
    const parsed: unknown = JSON.parse(raw);
    if (!isRecord(parsed) || parsed.version !== 1) {
      discardStoredState();
      return defaultAppState();
    }
    const savedAt = parsed.savedAt;
    if (typeof savedAt !== 'number'
      || !Number.isFinite(savedAt)
      || savedAt <= 0
      || Date.now() - savedAt > STATE_TTL_MS) {
      discardStoredState();
      return defaultAppState();
    }

    const defaults = defaultAppState();
    const next: PersistedAppState = {
      ...defaults,
      savedAt,
    };

    if (isRecord(parsed.chatPage)) {
      next.chatPage.toolbarWidth = typeof parsed.chatPage.toolbarWidth === 'number'
        ? Math.max(280, Math.min(760, parsed.chatPage.toolbarWidth))
        : defaults.chatPage.toolbarWidth;
      next.chatPage.isToolbarCollapsed = Boolean(parsed.chatPage.isToolbarCollapsed);
      next.chatPage.scrollY = parseNonNegativeNumber(parsed.chatPage.scrollY, 0);

      if (isRecord(parsed.chatPage.mapState)) {
        next.chatPage.mapState = {
          overlayVisibility: parseBooleanRecord(parsed.chatPage.mapState.overlayVisibility),
          overlayOpacity: parseNumberRecord(parsed.chatPage.mapState.overlayOpacity),
        };
      }

      if (isRecord(parsed.chatPage.chatPanel)) {
        next.chatPage.chatPanel = {
          conversationId: typeof parsed.chatPage.chatPanel.conversationId === 'string'
            && parsed.chatPage.chatPanel.conversationId.trim().length > 0
            ? parsed.chatPage.chatPanel.conversationId
            : undefined,
          lastRunSequence: parseRunSequence(parsed.chatPage.chatPanel.lastRunSequence),
          composerDraft: typeof parsed.chatPage.chatPanel.composerDraft === 'string'
            ? parsed.chatPage.chatPanel.composerDraft
            : '',
          transcriptScrollTop: parseNonNegativeNumber(
            parsed.chatPage.chatPanel.transcriptScrollTop,
            0,
          ),
        };
      }
    }

    if (isRecord(parsed.settingsPage)) {
      next.settingsPage = {
        searchText: typeof parsed.settingsPage.searchText === 'string'
          ? parsed.settingsPage.searchText
          : '',
        scrollY: parseNonNegativeNumber(parsed.settingsPage.scrollY, 0),
        modelGridScrollTop: parseNonNegativeNumber(parsed.settingsPage.modelGridScrollTop, 0),
      };
    }

    return next;
  } catch {
    discardStoredState();
    return defaultAppState();
  }
};

export const persistAppState = (state: PersistedAppState): void => {
  if (typeof window === 'undefined') {
    return;
  }
  window.sessionStorage.setItem(
    APP_STATE_STORAGE_KEY,
    JSON.stringify({ ...state, version: 1, savedAt: Date.now() }),
  );
};

export const clearPersistedAppState = (): void => {
  discardStoredState();
};

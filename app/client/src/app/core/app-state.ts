import {
  ChatMessage,
  ChatRole,
  ContextUsage,
  MapSession,
  ModelProviderMode,
  OverlayStateChange,
  PolicyDecision,
  SearchResponsePayload,
} from './types';

const STORAGE_KEY = 'aegis:webapp-state:v3';
const STATE_TTL_MS = 6 * 60 * 60 * 1000;
const TAB_ID_KEY = 'aegis:webapp-tab-id:v1';
const TAB_HEARTBEAT_PREFIX = 'aegis:webapp-tab-heartbeat:v1:';
const TAB_HEARTBEAT_TTL_MS = 15000;
const DEFAULT_CHAT_PANEL_RATIO = 0.3;

export interface PersistedChatPanelState {
  sessionId?: number;
  conversationNonce: number;
  messages: ChatMessage[];
  lastDecision?: PolicyDecision;
  memorySnapshot?: Record<string, unknown>;
  mapSession?: MapSession;
  contextUsage?: ContextUsage;
  status: string;
  assistantDraft: string;
  composerDraft: string;
  transcriptScrollTop: number;
}

export interface PersistedMapState extends OverlayStateChange {}

export interface PersistedChatPageState {
  toolbarWidth: number;
  isToolbarCollapsed: boolean;
  payload?: SearchResponsePayload;
  chatPanel: PersistedChatPanelState;
  mapState: PersistedMapState;
  scrollY: number;
}

export interface PersistedSettingsPageState {
  searchText: string;
  providerMode: ModelProviderMode;
  statusText: string;
  scrollY: number;
  modelGridScrollTop: number;
}

export interface PersistedAppState {
  version: 3;
  savedAt: number;
  tabId: string;
  chatPage: PersistedChatPageState;
  settingsPage: PersistedSettingsPageState;
}

const isRecord = (value: unknown): value is Record<string, unknown> =>
  typeof value === 'object' && value !== null;

const isProviderMode = (value: unknown): value is ModelProviderMode =>
  value === 'local' || value === 'cloud';

const isChatRole = (value: unknown): value is ChatRole =>
  value === 'user' || value === 'assistant' || value === 'system' || value === 'tool';

const isPersistedChatMessage = (value: unknown): value is ChatMessage => (
  isRecord(value)
  && isChatRole(value.role)
  && typeof value.content === 'string'
  && (value.created_at === undefined || typeof value.created_at === 'string')
);

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

const parsePersistedMessages = (value: unknown): ChatMessage[] => {
  if (!Array.isArray(value)) {
    return [];
  }
  return value
    .filter(isPersistedChatMessage)
    .map((entry) => ({
      role: entry.role,
      content: entry.content,
      created_at: typeof entry.created_at === 'string' ? entry.created_at : undefined,
    }));
};

export const defaultAppState = (): PersistedAppState => ({
  version: 3,
  savedAt: Date.now(),
  tabId: '',
  chatPage: {
    toolbarWidth: (() => {
      if (typeof window === 'undefined') {
        return 480;
      }
      const width = Math.round(window.innerWidth * DEFAULT_CHAT_PANEL_RATIO);
      return Math.max(280, Math.min(760, width));
    })(),
    isToolbarCollapsed: false,
    payload: undefined,
    chatPanel: {
      sessionId: undefined,
      conversationNonce: 1,
      messages: [],
      lastDecision: undefined,
      memorySnapshot: {},
        mapSession: undefined,
        contextUsage: undefined,
      status: 'Idle',
      assistantDraft: '',
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
    providerMode: 'local',
    statusText: 'Ready',
    scrollY: 0,
    modelGridScrollTop: 0,
  },
});

const ensureTabId = (): string => {
  if (typeof window === 'undefined') {
    return '';
  }
  const existing = window.sessionStorage.getItem(TAB_ID_KEY);
  if (existing) {
    return existing;
  }
  const next = window.crypto.randomUUID();
  window.sessionStorage.setItem(TAB_ID_KEY, next);
  return next;
};

const setTabId = (tabId: string): void => {
  if (typeof window === 'undefined') {
    return;
  }
  window.sessionStorage.setItem(TAB_ID_KEY, tabId);
};

const rotateTabId = (): string => {
  const next = window.crypto.randomUUID();
  setTabId(next);
  return next;
};

const heartbeatKey = (tabId: string): string => `${TAB_HEARTBEAT_PREFIX}${tabId}`;

const hasActiveOwner = (tabId: string): boolean => {
  if (typeof window === 'undefined') {
    return false;
  }
  const raw = window.localStorage.getItem(heartbeatKey(tabId));
  const lastSeen = raw ? Number(raw) : 0;
  return Number.isFinite(lastSeen) && lastSeen > 0 && Date.now() - lastSeen < TAB_HEARTBEAT_TTL_MS;
};

const touchHeartbeat = (tabId: string): void => {
  if (typeof window === 'undefined') {
    return;
  }
  window.localStorage.setItem(heartbeatKey(tabId), String(Date.now()));
};

export const loadPersistedAppState = (): PersistedAppState => {
  if (typeof window === 'undefined') {
    return defaultAppState();
  }
  const raw = window.sessionStorage.getItem(STORAGE_KEY);
  let currentTabId = ensureTabId();
  if (hasActiveOwner(currentTabId)) {
    currentTabId = rotateTabId();
    window.sessionStorage.removeItem(STORAGE_KEY);
  }
  touchHeartbeat(currentTabId);
  if (!raw) {
    return {
      ...defaultAppState(),
      tabId: currentTabId,
    };
  }
  try {
    const parsed = JSON.parse(raw);
    if (!isRecord(parsed) || parsed.version !== 3) {
      return {
        ...defaultAppState(),
        tabId: currentTabId,
      };
    }
    const savedAt = typeof parsed.savedAt === 'number' ? parsed.savedAt : 0;
    if (!savedAt || Date.now() - savedAt > STATE_TTL_MS) {
      window.sessionStorage.removeItem(STORAGE_KEY);
      return {
        ...defaultAppState(),
        tabId: currentTabId,
      };
    }

    if (typeof parsed.tabId !== 'string' || parsed.tabId !== currentTabId) {
      window.sessionStorage.removeItem(STORAGE_KEY);
      return {
        ...defaultAppState(),
        tabId: currentTabId,
      };
    }

    const defaults = defaultAppState();
    const next: PersistedAppState = {
      ...defaults,
      savedAt,
      tabId: currentTabId,
    };

    if (isRecord(parsed.chatPage)) {
      next.chatPage.toolbarWidth = typeof parsed.chatPage.toolbarWidth === 'number'
        ? Math.max(280, Math.min(760, parsed.chatPage.toolbarWidth))
        : defaults.chatPage.toolbarWidth;
      next.chatPage.isToolbarCollapsed = Boolean(parsed.chatPage.isToolbarCollapsed);
      next.chatPage.payload = isRecord(parsed.chatPage.payload)
        ? parsed.chatPage.payload as SearchResponsePayload
        : undefined;
      next.chatPage.scrollY = typeof parsed.chatPage.scrollY === 'number' ? parsed.chatPage.scrollY : 0;
      if (isRecord(parsed.chatPage.mapState)) {
        next.chatPage.mapState = {
          overlayVisibility: parseBooleanRecord(parsed.chatPage.mapState.overlayVisibility),
          overlayOpacity: parseNumberRecord(parsed.chatPage.mapState.overlayOpacity),
        };
      }
      if (isRecord(parsed.chatPage.chatPanel)) {
        next.chatPage.chatPanel = {
          sessionId: typeof parsed.chatPage.chatPanel.sessionId === 'number'
            ? parsed.chatPage.chatPanel.sessionId
            : undefined,
          conversationNonce: typeof parsed.chatPage.chatPanel.conversationNonce === 'number'
            ? parsed.chatPage.chatPanel.conversationNonce
            : 1,
          messages: parsePersistedMessages(parsed.chatPage.chatPanel.messages),
          lastDecision: isRecord(parsed.chatPage.chatPanel.lastDecision)
            ? parsed.chatPage.chatPanel.lastDecision as unknown as PolicyDecision
            : undefined,
          memorySnapshot: isRecord(parsed.chatPage.chatPanel.memorySnapshot)
            ? parsed.chatPage.chatPanel.memorySnapshot as Record<string, unknown>
            : {},
          mapSession: isRecord(parsed.chatPage.chatPanel.mapSession)
            ? parsed.chatPage.chatPanel.mapSession as unknown as MapSession
            : undefined,
          contextUsage: isRecord(parsed.chatPage.chatPanel.contextUsage)
            ? parsed.chatPage.chatPanel.contextUsage as unknown as ContextUsage
            : undefined,
          status: typeof parsed.chatPage.chatPanel.status === 'string'
            ? parsed.chatPage.chatPanel.status
            : defaults.chatPage.chatPanel.status,
          assistantDraft: typeof parsed.chatPage.chatPanel.assistantDraft === 'string'
            ? parsed.chatPage.chatPanel.assistantDraft
            : '',
          composerDraft: typeof parsed.chatPage.chatPanel.composerDraft === 'string'
            ? parsed.chatPage.chatPanel.composerDraft
            : '',
          transcriptScrollTop: typeof parsed.chatPage.chatPanel.transcriptScrollTop === 'number'
            ? parsed.chatPage.chatPanel.transcriptScrollTop
            : 0,
        };
      }
    }

    if (isRecord(parsed.settingsPage)) {
      next.settingsPage.searchText = typeof parsed.settingsPage.searchText === 'string'
        ? parsed.settingsPage.searchText
        : '';
      next.settingsPage.providerMode = isProviderMode(parsed.settingsPage.providerMode)
        ? parsed.settingsPage.providerMode
        : defaults.settingsPage.providerMode;
      next.settingsPage.statusText = typeof parsed.settingsPage.statusText === 'string'
        ? parsed.settingsPage.statusText
        : defaults.settingsPage.statusText;
      next.settingsPage.scrollY = typeof parsed.settingsPage.scrollY === 'number' ? parsed.settingsPage.scrollY : 0;
      next.settingsPage.modelGridScrollTop = typeof parsed.settingsPage.modelGridScrollTop === 'number'
        ? parsed.settingsPage.modelGridScrollTop
        : 0;
    }
    return next;
  } catch {
    window.sessionStorage.removeItem(STORAGE_KEY);
    return {
      ...defaultAppState(),
      tabId: currentTabId,
    };
  }
};

export const persistAppState = (state: PersistedAppState): void => {
  if (typeof window === 'undefined') {
    return;
  }
  const withTimestamp: PersistedAppState = {
    ...state,
    tabId: ensureTabId(),
    savedAt: Date.now(),
  };
  window.sessionStorage.setItem(STORAGE_KEY, JSON.stringify(withTimestamp));
};

export const startTabHeartbeat = (tabId: string): (() => void) => {
  if (typeof window === 'undefined' || !tabId) {
    return () => {};
  }
  const key = heartbeatKey(tabId);
  const update = () => touchHeartbeat(tabId);
  update();
  const intervalId = window.setInterval(update, TAB_HEARTBEAT_TTL_MS / 3);
  const onBeforeUnload = () => {
    window.localStorage.removeItem(key);
  };
  window.addEventListener('beforeunload', onBeforeUnload);
  return () => {
    window.clearInterval(intervalId);
    window.removeEventListener('beforeunload', onBeforeUnload);
    window.localStorage.removeItem(key);
  };
};

export const clearPersistedAppState = (): void => {
  if (typeof window === 'undefined') {
    return;
  }
  window.sessionStorage.removeItem(STORAGE_KEY);
};

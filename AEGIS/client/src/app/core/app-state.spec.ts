import {
  defaultAppState,
  loadPersistedAppState,
  persistAppState,
} from './app-state';

describe('core/app-state', () => {
  const storageKey = 'aegis:webapp-state:v3';
  const tabKey = 'aegis:webapp-tab-id:v1';
  const heartbeatPrefix = 'aegis:webapp-tab-heartbeat:v1:';

  beforeEach(() => {
    window.sessionStorage.clear();
    window.localStorage.clear();
  });

  it('creates default state', () => {
    const state = defaultAppState();
    expect(state.version).toBe(3);
    expect(state.chatPage.chatPanel.messages).toEqual([]);
    expect(state.settingsPage.providerMode).toBe('local');
  });

  it('loads valid persisted state', () => {
    const now = Date.now();
    window.sessionStorage.setItem(tabKey, 'tab-1');
    window.sessionStorage.setItem(storageKey, JSON.stringify({
      ...defaultAppState(),
      tabId: 'tab-1',
      savedAt: now,
      chatPage: {
        ...defaultAppState().chatPage,
        chatPanel: {
          ...defaultAppState().chatPage.chatPanel,
          composerDraft: 'persisted draft',
          contextUsage: {
            estimated_input_tokens: 200,
            selected_context_window: 2048,
            model_context_limit: 8192,
            usage_percent: 9.8,
            provider: 'ollama',
            model: 'llama3.2',
          },
        },
      },
    }));
    const state = loadPersistedAppState();
    expect(state.chatPage.chatPanel.composerDraft).toBe('persisted draft');
    expect(state.chatPage.chatPanel.contextUsage?.usage_percent).toBe(9.8);
    expect(state.tabId).toBe('tab-1');
  });

  it('resets on corrupted storage', () => {
    window.sessionStorage.setItem(tabKey, 'tab-2');
    window.sessionStorage.setItem(storageKey, '{invalid');
    const state = loadPersistedAppState();
    expect(state.chatPage.chatPanel.composerDraft).toBe('');
  });

  it('resets on expired ttl', () => {
    const old = Date.now() - (7 * 60 * 60 * 1000);
    window.sessionStorage.setItem(tabKey, 'tab-3');
    window.sessionStorage.setItem(storageKey, JSON.stringify({
      ...defaultAppState(),
      tabId: 'tab-3',
      savedAt: old,
    }));
    const state = loadPersistedAppState();
    expect(state.chatPage.chatPanel.messages.length).toBe(0);
  });

  it('rotates tab on heartbeat ownership conflict', () => {
    window.sessionStorage.setItem(tabKey, 'tab-owned');
    window.localStorage.setItem(`${heartbeatPrefix}tab-owned`, String(Date.now()));
    window.sessionStorage.setItem(storageKey, JSON.stringify({
      ...defaultAppState(),
      tabId: 'tab-owned',
      savedAt: Date.now(),
      chatPage: {
        ...defaultAppState().chatPage,
        chatPanel: {
          ...defaultAppState().chatPage.chatPanel,
          composerDraft: 'should be reset',
        },
      },
    }));
    const state = loadPersistedAppState();
    expect(state.chatPage.chatPanel.composerDraft).toBe('');
    expect(state.tabId).not.toBe('tab-owned');
  });

  it('persists schema version and timestamp', () => {
    const state = defaultAppState();
    persistAppState(state);
    const raw = window.sessionStorage.getItem(storageKey);
    expect(raw).toBeTruthy();
    const persisted = JSON.parse(String(raw));
    expect(persisted.version).toBe(3);
    expect(typeof persisted.savedAt).toBe('number');
  });

  it('invalidates persisted state from older schema versions', () => {
    const now = Date.now();
    window.sessionStorage.setItem(tabKey, 'tab-old-version');
    window.sessionStorage.setItem(storageKey, JSON.stringify({
      ...defaultAppState(),
      version: 2,
      tabId: 'tab-old-version',
      savedAt: now,
      chatPage: {
        ...defaultAppState().chatPage,
        chatPanel: {
          ...defaultAppState().chatPage.chatPanel,
          composerDraft: 'legacy-schema-draft',
        },
      },
    }));
    const loaded = loadPersistedAppState();
    expect(loaded.version).toBe(3);
    expect(loaded.chatPage.chatPanel.composerDraft).toBe('');
  });

  it('stale overlay ids are tolerated in persisted payload and remain serializable', () => {
    const state = defaultAppState();
    state.chatPage.mapState.overlayVisibility = { removed_overlay: true };
    state.chatPage.mapState.overlayOpacity = { removed_overlay: 0.4 };
    persistAppState(state);
    const loaded = loadPersistedAppState();
    expect(loaded.chatPage.mapState.overlayVisibility['removed_overlay']).toBeTrue();
    expect(loaded.chatPage.mapState.overlayOpacity['removed_overlay']).toBe(0.4);
  });
});

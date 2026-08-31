import {
  APP_STATE_STORAGE_KEY,
  defaultAppState,
  loadPersistedAppState,
  persistAppState,
} from './app-state';

describe('core/app-state', () => {
  const storageKey = APP_STATE_STORAGE_KEY;

  beforeEach(() => {
    window.sessionStorage.clear();
  });

  it('creates UI-only default state', () => {
    const state = defaultAppState();
    expect(state.version).toBe(1);
    expect(state.chatPage.chatPanel.composerDraft).toBe('');
    expect(state.chatPage.chatPanel.lastRunSequence).toBe(0);
    expect(state.settingsPage.searchText).toBe('');
  });

  it('loads valid UI state without restoring server-owned fields', () => {
    const now = Date.now();
    window.sessionStorage.setItem(storageKey, JSON.stringify({
      ...defaultAppState(),
      savedAt: now,
      chatPage: {
        ...defaultAppState().chatPage,
        chatPanel: {
          ...defaultAppState().chatPage.chatPanel,
          conversationId: 'conversation-1',
          lastRunSequence: 12,
          composerDraft: 'persisted draft',
          messages: [{ role: 'assistant', content: 'must not hydrate' }],
          mapSession: { session_id: 'must not hydrate' },
          memorySnapshot: { key: 'must not hydrate' },
        },
      },
      settingsPage: {
        ...defaultAppState().settingsPage,
        providerMode: 'cloud',
        statusText: 'must not hydrate',
      },
    }));
    const state = loadPersistedAppState();
    expect(state.chatPage.chatPanel.conversationId).toBe('conversation-1');
    expect(state.chatPage.chatPanel.lastRunSequence).toBe(12);
    expect(state.chatPage.chatPanel.composerDraft).toBe('persisted draft');
    expect((state.chatPage.chatPanel as unknown as Record<string, unknown>).messages).toBeUndefined();
    expect((state.chatPage.chatPanel as unknown as Record<string, unknown>).mapSession).toBeUndefined();
    expect((state.chatPage.chatPanel as unknown as Record<string, unknown>).memorySnapshot).toBeUndefined();
    expect((state.settingsPage as unknown as Record<string, unknown>).providerMode).toBeUndefined();
    expect((state.settingsPage as unknown as Record<string, unknown>).statusText).toBeUndefined();
  });

  it('resets on corrupted storage', () => {
    window.sessionStorage.setItem(storageKey, '{invalid');
    const state = loadPersistedAppState();
    expect(state.chatPage.chatPanel.composerDraft).toBe('');
    expect(window.sessionStorage.getItem(storageKey)).toBeNull();
  });

  it('resets on expired ttl', () => {
    const old = Date.now() - (7 * 60 * 60 * 1000);
    window.sessionStorage.setItem(storageKey, JSON.stringify({
      ...defaultAppState(),
      savedAt: old,
    }));
    const state = loadPersistedAppState();
    expect(state.chatPage.chatPanel.conversationId).toBeUndefined();
    expect(window.sessionStorage.getItem(storageKey)).toBeNull();
  });

  it('ignores older schema versions without migration', () => {
    window.sessionStorage.setItem(storageKey, JSON.stringify({
      ...defaultAppState(),
      version: 2,
      savedAt: Date.now(),
      chatPage: {
        ...defaultAppState().chatPage,
        chatPanel: {
          ...defaultAppState().chatPage.chatPanel,
          composerDraft: 'old-schema-draft',
        },
      },
    }));
    const loaded = loadPersistedAppState();
    expect(loaded.version).toBe(1);
    expect(loaded.chatPage.chatPanel.composerDraft).toBe('');
    expect(window.sessionStorage.getItem(storageKey)).toBeNull();
  });

  it('persists only the current UI schema', () => {
    const state = defaultAppState();
    state.chatPage.chatPanel.conversationId = 'conversation-1';
    state.chatPage.chatPanel.composerDraft = 'draft';
    persistAppState(state);
    const persisted = JSON.parse(String(window.sessionStorage.getItem(storageKey))) as Record<string, unknown>;
    expect(persisted.version).toBe(1);
    expect(typeof persisted.savedAt).toBe('number');
    const raw = JSON.stringify(persisted);
    expect(raw).not.toContain('messages');
    expect(raw).not.toContain('mapSession');
    expect(raw).not.toContain('memorySnapshot');
    expect(raw).not.toContain('providerMode');
    expect(raw).not.toContain('statusText');
  });

  it('retains presentation overlay preferences', () => {
    const state = defaultAppState();
    state.chatPage.mapState.overlayVisibility = { removed_overlay: true };
    state.chatPage.mapState.overlayOpacity = { removed_overlay: 0.4 };
    persistAppState(state);
    const loaded = loadPersistedAppState();
    expect(loaded.chatPage.mapState.overlayVisibility['removed_overlay']).toBeTrue();
    expect(loaded.chatPage.mapState.overlayOpacity['removed_overlay']).toBe(0.4);
  });
});

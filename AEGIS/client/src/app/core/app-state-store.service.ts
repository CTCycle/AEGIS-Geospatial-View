import { Injectable, OnDestroy } from '@angular/core';

import {
  PersistedAppState,
  PersistedChatPageState,
  PersistedSettingsPageState,
  clearPersistedAppState,
  defaultAppState,
  loadPersistedAppState,
  persistAppState,
  startTabHeartbeat,
} from './app-state';

@Injectable({ providedIn: 'root' })
export class AppStateStoreService implements OnDestroy {
  private state: PersistedAppState = loadPersistedAppState();
  private heartbeatDisposer: (() => void) | null = null;

  constructor() {
    this.heartbeatDisposer = startTabHeartbeat(this.state.tabId);
    window.addEventListener('storage', this.onStorage);
  }

  ngOnDestroy(): void {
    this.heartbeatDisposer?.();
    window.removeEventListener('storage', this.onStorage);
  }

  getChatPage(): PersistedChatPageState {
    return structuredClone(this.state.chatPage);
  }

  getSettingsPage(): PersistedSettingsPageState {
    return structuredClone(this.state.settingsPage);
  }

  updateChatPage(chatPage: PersistedChatPageState): void {
    this.state = { ...this.state, chatPage };
    persistAppState(this.state);
  }

  updateSettingsPage(settingsPage: PersistedSettingsPageState): void {
    this.state = { ...this.state, settingsPage };
    persistAppState(this.state);
  }

  resetState(): void {
    clearPersistedAppState();
    this.state = defaultAppState();
    persistAppState(this.state);
  }

  private readonly onStorage = (event: StorageEvent): void => {
    if (event.key !== null) {
      return;
    }
    this.resetState();
  };
}

import { APP_STATE_STORAGE_KEY } from './app-state';
import { AppStateStoreService } from './app-state-store.service';

describe('core/app-state-store.service', () => {
  beforeEach(() => {
    window.sessionStorage.clear();
    window.localStorage.clear();
  });

  it('getters return clones instead of mutable references', () => {
    const service = new AppStateStoreService();
    const chat = service.getChatPage();
    chat.chatPanel.status = 'Changed';
    expect(service.getChatPage().chatPanel.status).not.toBe('Changed');
    service.ngOnDestroy();
  });

  it('updateChatPage and updateSettingsPage persist state', () => {
    const service = new AppStateStoreService();
    const chat = service.getChatPage();
    chat.chatPanel.composerDraft = 'hello';
    service.updateChatPage(chat);
    expect(service.getChatPage().chatPanel.composerDraft).toBe('hello');

    const settings = service.getSettingsPage();
    settings.searchText = 'gpt';
    service.updateSettingsPage(settings);
    expect(service.getSettingsPage().searchText).toBe('gpt');
    service.ngOnDestroy();
  });

  it('resetState and resetChatPage clear relevant state', () => {
    const service = new AppStateStoreService();
    const chat = service.getChatPage();
    chat.chatPanel.composerDraft = 'hello';
    service.updateChatPage(chat);
    service.resetChatPage();
    expect(service.getChatPage().chatPanel.composerDraft).toBe('');

    const settings = service.getSettingsPage();
    settings.searchText = 'gpt';
    service.updateSettingsPage(settings);
    service.resetState();
    expect(service.getSettingsPage().searchText).toBe('');
    service.ngOnDestroy();
  });

  it('storage event with null key resets state', () => {
    const service = new AppStateStoreService();
    const chat = service.getChatPage();
    chat.chatPanel.composerDraft = 'pending';
    service.updateChatPage(chat);
    window.dispatchEvent(new StorageEvent('storage', { key: null }));
    expect(service.getChatPage().chatPanel.composerDraft).toBe('');
    service.ngOnDestroy();
  });

  it('storage event for unrelated key does not reset state', () => {
    const service = new AppStateStoreService();
    const chat = service.getChatPage();
    chat.chatPanel.composerDraft = 'pending';
    service.updateChatPage(chat);
    window.dispatchEvent(new StorageEvent('storage', { key: 'other:key' }));
    expect(service.getChatPage().chatPanel.composerDraft).toBe('pending');
    service.ngOnDestroy();
  });

  it('storage event for app state key resets state', () => {
    const service = new AppStateStoreService();
    const chat = service.getChatPage();
    chat.chatPanel.composerDraft = 'pending';
    service.updateChatPage(chat);
    window.dispatchEvent(new StorageEvent('storage', { key: APP_STATE_STORAGE_KEY }));
    expect(service.getChatPage().chatPanel.composerDraft).toBe('');
    service.ngOnDestroy();
  });

  it('heartbeat disposer cleanup runs on destroy', () => {
    const removeSpy = spyOn(window.localStorage, 'removeItem').and.callThrough();
    const service = new AppStateStoreService();
    service.ngOnDestroy();
    expect(removeSpy).toHaveBeenCalled();
  });
});

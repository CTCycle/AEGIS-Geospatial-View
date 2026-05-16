import { TestBed } from '@angular/core/testing';
import { Component } from '@angular/core';
import { provideRouter, Router } from '@angular/router';

import { ApiClientService } from '../core/api-client.service';
import { defaultAppState } from '../core/app-state';
import { AppStateStoreService } from '../core/app-state-store.service';
import { UserFacingErrorService } from '../core/user-facing-error.service';
import { SettingsPageComponent } from './settings-page.component';

@Component({ template: '' })
class TestRouteComponent {}

describe('pages/settings-page.component', () => {
  let router: Router;
  let store: jasmine.SpyObj<AppStateStoreService>;
  let errors: jasmine.SpyObj<UserFacingErrorService>;
  let apiClient: jasmine.SpyObj<ApiClientService>;
  let fetchChatSettingsMock: jasmine.Spy;
  let fetchChatModelsMock: jasmine.Spy;
  let updateChatSettingsMock: jasmine.Spy;
  let checkOllamaHealthMock: jasmine.Spy;
  let refreshOllamaModelsMock: jasmine.Spy;
  let pullOllamaModelMock: jasmine.Spy;

  beforeEach(async () => {
    store = jasmine.createSpyObj<AppStateStoreService>('AppStateStoreService', ['getSettingsPage', 'updateSettingsPage']);
    store.getSettingsPage.and.returnValue(defaultAppState().settingsPage);
    errors = jasmine.createSpyObj<UserFacingErrorService>('UserFacingErrorService', ['toUserFacingError', 'normalizeDisplayText', 'isLowLevelConnectionError']);
    errors.toUserFacingError.and.callFake((_: unknown, fallback: string) => fallback);
    errors.normalizeDisplayText.and.callFake((value: string) => value);
    errors.isLowLevelConnectionError.and.returnValue(true);

    apiClient = jasmine.createSpyObj<ApiClientService>('ApiClientService', [
      'fetchChatSettings',
      'fetchChatModels',
      'updateChatSettings',
      'checkOllamaHealth',
      'refreshOllamaModels',
      'pullOllamaModel',
    ]);
    fetchChatSettingsMock = jasmine.createSpy('fetchChatSettings').and.resolveTo({
      active_provider_mode: 'local',
      chat_model_provider: 'ollama',
      chat_model_name: 'llama3.2',
      parser_model_provider: 'ollama',
      parser_model_name: 'llama3.2',
      agent_model_provider: 'ollama',
      agent_model_name: 'llama3.2',
      ollama_url: 'http://localhost:11434',
      credentials: {},
      credential_health: {},
    });
    fetchChatModelsMock = jasmine.createSpy('fetchChatModels').and.resolveTo({
      cloud: [{ id: 'gpt-4.1-mini', name: 'gpt-4.1-mini', description: 'cloud', provider: 'openai', capabilities: [], metadata: {} }],
      local: [{ id: 'llama3.2', name: 'llama3.2', description: 'local', provider: 'ollama', capabilities: [], metadata: {} }],
    });
    updateChatSettingsMock = jasmine.createSpy('updateChatSettings').and.callFake(async (payload) => payload as never);
    checkOllamaHealthMock = jasmine.createSpy('checkOllamaHealth').and.resolveTo({ ok: true, detail: 'ok' });
    refreshOllamaModelsMock = jasmine.createSpy('refreshOllamaModels').and.resolveTo({});
    pullOllamaModelMock = jasmine.createSpy('pullOllamaModel').and.resolveTo({});

    apiClient.fetchChatSettings.and.callFake(() => fetchChatSettingsMock());
    apiClient.fetchChatModels.and.callFake(() => fetchChatModelsMock());
    apiClient.updateChatSettings.and.callFake((payload) => updateChatSettingsMock(payload));
    apiClient.checkOllamaHealth.and.callFake(() => checkOllamaHealthMock());
    apiClient.refreshOllamaModels.and.callFake(() => refreshOllamaModelsMock());
    apiClient.pullOllamaModel.and.callFake((model) => pullOllamaModelMock(model));

    await TestBed.configureTestingModule({
      imports: [SettingsPageComponent],
      providers: [
        provideRouter([{ path: 'settings', component: TestRouteComponent }]),
        { provide: ApiClientService, useValue: apiClient },
        { provide: AppStateStoreService, useValue: store },
        { provide: UserFacingErrorService, useValue: errors },
      ],
    }).compileComponents();
    router = TestBed.inject(Router);
  });

  it('parses initial query params', () => {
    window.history.replaceState({}, '', '/settings?q=gpt&mode=cloud');
    const fixture = TestBed.createComponent(SettingsPageComponent);
    fixture.detectChanges();
    const component = fixture.componentInstance;
    expect(component.searchText).toBe('gpt');
    expect(component.providerMode).toBe('cloud');
  });

  it('loadData success and failure paths', async () => {
    const fixture = TestBed.createComponent(SettingsPageComponent);
    fixture.detectChanges();
    await fixture.whenStable();
    expect(fetchChatSettingsMock).toHaveBeenCalled();
    expect(fetchChatModelsMock).toHaveBeenCalled();

    fetchChatSettingsMock.and.rejectWith(new Error('boom'));
    const fixture2 = TestBed.createComponent(SettingsPageComponent);
    fixture2.detectChanges();
    await fixture2.whenStable();
    expect(fixture2.componentInstance.statusText).toContain('Could not load model settings right now.');
  });

  it('provider/search filters apply correctly', async () => {
    const fixture = TestBed.createComponent(SettingsPageComponent);
    fixture.detectChanges();
    await fixture.whenStable();
    const component = fixture.componentInstance;
    component.setProviderFilter('openai');
    component.setSearchText('gpt');
    expect(component.displayedModels.length).toBe(1);
  });

  it('applyModelSelection updates settings and status text', async () => {
    const fixture = TestBed.createComponent(SettingsPageComponent);
    fixture.detectChanges();
    await fixture.whenStable();
    const component = fixture.componentInstance;
    await component.applyModelSelection('chat', component.displayedModels[0]);
    expect(updateChatSettingsMock).toHaveBeenCalled();
    expect(component.statusText).toContain('Selected');
  });

  it('pulls a missing Ollama model before assigning it', async () => {
    fetchChatModelsMock.and.resolveTo({
      cloud: [{ id: 'llama3.1', name: 'llama3.1', description: 'library', provider: 'ollama', capabilities: [], metadata: {} }],
      local: [],
    });
    const fixture = TestBed.createComponent(SettingsPageComponent);
    fixture.detectChanges();
    await fixture.whenStable();
    const component = fixture.componentInstance;
    component.setProviderFilter('ollama');

    fetchChatModelsMock.and.resolveTo({
      cloud: [{ id: 'llama3.1', name: 'llama3.1', description: 'library', provider: 'ollama', capabilities: [], metadata: {} }],
      local: [{ id: 'llama3.1', name: 'llama3.1', description: 'local', provider: 'ollama', capabilities: [], metadata: {} }],
    });

    await component.applyModelSelection('parser', {
      id: 'llama3.1',
      name: 'llama3.1',
      description: 'library',
      provider: 'ollama',
      capabilities: [],
      metadata: {},
    });

    expect(pullOllamaModelMock).toHaveBeenCalledWith('llama3.1');
    expect(refreshOllamaModelsMock).toHaveBeenCalled();
    expect(updateChatSettingsMock).toHaveBeenCalled();
    expect(component.statusText).toContain('Selected llama3.1 for parser');
  });

  it('applyModelSelection does not send read-only credential health fields', async () => {
    fetchChatSettingsMock.and.resolveTo({
      active_provider_mode: 'local',
      chat_model_provider: 'ollama',
      chat_model_name: 'llama3.2',
      parser_model_provider: 'ollama',
      parser_model_name: 'llama3.2',
      agent_model_provider: 'ollama',
      agent_model_name: 'llama3.2',
      ollama_url: 'http://localhost:11434',
      openai_base_url: null,
      google_base_url: null,
      credentials: { openai: { api_key: true }, google: { api_key: true } },
      credential_health: { openai: { api_key: 'unreadable' }, google: { api_key: 'healthy' } },
    });
    const fixture = TestBed.createComponent(SettingsPageComponent);
    fixture.detectChanges();
    await fixture.whenStable();

    await fixture.componentInstance.applyModelSelection('chat', fixture.componentInstance.displayedModels[0]);

    const payload = updateChatSettingsMock.calls.mostRecent().args[0];
    expect(payload.credential_health).toBeUndefined();
    expect(payload.credentials.openai.api_key).toBeUndefined();
    expect(payload.credentials.google.api_key).toBeUndefined();
  });

  it('API key validation rules enforce OpenAI and Google prefixes', async () => {
    const fixture = TestBed.createComponent(SettingsPageComponent);
    fixture.detectChanges();
    await fixture.whenStable();
    const component = fixture.componentInstance;
    component.openaiKey = 'bad-openai-key';
    component.googleKey = 'bad-google-key';
    await component.saveKeys();
    expect(component.keyValidationErrors.openai).toContain('sk-');
    expect(component.keyValidationErrors.google).toContain('AIza');
  });

  it('save keys success and failure', async () => {
    const fixture = TestBed.createComponent(SettingsPageComponent);
    fixture.detectChanges();
    await fixture.whenStable();
    const component = fixture.componentInstance;
    component.openaiKey = 'sk-valid-openai-key-12345';
    await component.saveKeys();
    expect(component.statusText).toContain('API keys saved');

    updateChatSettingsMock.and.rejectWith(new Error('fail'));
    component.openaiKey = 'sk-valid-openai-key-12345';
    await component.saveKeys();
    expect(component.statusText).toContain('Could not save API keys right now.');
  });

  it('saveOllamaSettings sends a sanitized update payload', async () => {
    fetchChatSettingsMock.and.resolveTo({
      active_provider_mode: 'local',
      chat_model_provider: 'ollama',
      chat_model_name: 'llama3.2',
      parser_model_provider: 'ollama',
      parser_model_name: 'llama3.2',
      agent_model_provider: 'ollama',
      agent_model_name: 'llama3.2',
      ollama_url: 'http://localhost:11434',
      openai_base_url: null,
      google_base_url: null,
      credentials: { openai: { api_key: true }, google: { api_key: true } },
      credential_health: { openai: { api_key: 'unreadable' }, google: { api_key: 'healthy' } },
    });
    const fixture = TestBed.createComponent(SettingsPageComponent);
    fixture.detectChanges();
    await fixture.whenStable();

    fixture.componentInstance.ollamaUrlDraft = 'http://localhost:11435';
    await fixture.componentInstance.saveOllamaSettings();

    const payload = updateChatSettingsMock.calls.mostRecent().args[0];
    expect(payload.ollama_url).toBe('http://localhost:11435');
    expect(payload.credentials).toEqual({});
    expect(payload.credential_health).toBeUndefined();
  });

  it('reports unreadable credential health in API key modal state', async () => {
    fetchChatSettingsMock.and.resolveTo({
      active_provider_mode: 'cloud',
      chat_model_provider: 'openai',
      chat_model_name: 'gpt-4.1-mini',
      parser_model_provider: 'openai',
      parser_model_name: 'gpt-4.1-mini',
      agent_model_provider: 'openai',
      agent_model_name: 'gpt-4.1-mini',
      ollama_url: 'http://localhost:11434',
      credentials: { openai: { api_key: true } },
      credential_health: { openai: { api_key: 'unreadable' } },
    });
    const fixture = TestBed.createComponent(SettingsPageComponent);
    fixture.detectChanges();
    await fixture.whenStable();

    expect(fixture.componentInstance.openAiCredentialHealth()).toBe('unreadable');
  });

  it('Ollama health success and degraded failure message formatting', async () => {
    const fixture = TestBed.createComponent(SettingsPageComponent);
    fixture.detectChanges();
    await fixture.whenStable();
    const component = fixture.componentInstance;
    await component.checkOllamaConnection();
    expect(component.statusText).toContain('Ollama:');

    checkOllamaHealthMock.and.rejectWith(new Error('connection refused'));
    await component.checkOllamaConnection();
    expect(component.statusText).toContain('Unable to reach Ollama');
  });

  it('refresh library and pull model flows update status', async () => {
    const fixture = TestBed.createComponent(SettingsPageComponent);
    fixture.detectChanges();
    await fixture.whenStable();
    const component = fixture.componentInstance;
    await component.refreshOllamaLibrary();
    expect(component.statusText).toContain('refreshed');
    await component.pullLocalModel({ id: 'llama3.2', name: 'llama3.2', description: '', provider: 'ollama', capabilities: [], metadata: {} });
    expect(component.statusText).toContain('Pulled');
  });

  it('syncQueryState and persistence update URL and store', async () => {
    window.history.replaceState({}, '', '/settings');
    const fixture = TestBed.createComponent(SettingsPageComponent);
    fixture.detectChanges();
    await fixture.whenStable();
    const component = fixture.componentInstance;
    component.setSearchText('gpt');
    await fixture.whenStable();
    expect(window.location.pathname).toBe('/settings');
    expect(window.location.search).toBe('?q=gpt');
    expect(store.updateSettingsPage).toHaveBeenCalled();
  });

  it('exposes an accessible label on the model search input', async () => {
    const fixture = TestBed.createComponent(SettingsPageComponent);
    fixture.detectChanges();
    await fixture.whenStable();
    const input = fixture.nativeElement.querySelector('input.model-search-bar') as HTMLInputElement | null;
    expect(input).not.toBeNull();
    expect(input?.getAttribute('aria-label')).toBe('Search models');
  });

  it('navigateBack preserves state before routing', async () => {
    const navigateSpy = spyOn(router, 'navigateByUrl').and.resolveTo(true);
    const fixture = TestBed.createComponent(SettingsPageComponent);
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.componentInstance.navigateBack();
    expect(store.updateSettingsPage).toHaveBeenCalled();
    expect(navigateSpy).toHaveBeenCalledWith('/');
  });
});

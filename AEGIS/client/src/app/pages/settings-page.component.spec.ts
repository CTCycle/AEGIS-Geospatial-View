import { TestBed } from '@angular/core/testing';
import { provideRouter, Router } from '@angular/router';

import * as Api from '../core/api';
import { AppStateStoreService } from '../core/app-state-store.service';
import { defaultAppState } from '../core/app-state';
import { UserFacingErrorService } from '../core/user-facing-error.service';
import { SettingsPageComponent } from './settings-page.component';

describe('pages/settings-page.component', () => {
  let router: Router;
  let store: jasmine.SpyObj<AppStateStoreService>;
  let errors: jasmine.SpyObj<UserFacingErrorService>;

  beforeEach(async () => {
    store = jasmine.createSpyObj<AppStateStoreService>('AppStateStoreService', [
      'getSettingsPage',
      'updateSettingsPage',
    ]);
    store.getSettingsPage.and.returnValue(defaultAppState().settingsPage);
    errors = jasmine.createSpyObj<UserFacingErrorService>('UserFacingErrorService', [
      'toUserFacingError',
      'normalizeDisplayText',
      'isLowLevelConnectionError',
    ]);
    errors.toUserFacingError.and.callFake((_: unknown, fallback: string) => fallback);
    errors.normalizeDisplayText.and.callFake((value: string) => value);
    errors.isLowLevelConnectionError.and.returnValue(true);

    spyOn(Api, 'fetchChatSettings').and.resolveTo({
      active_provider_mode: 'local',
      chat_model_provider: 'ollama',
      chat_model_name: 'llama3.2',
      parser_model_provider: 'ollama',
      parser_model_name: 'llama3.2',
      agent_model_provider: 'ollama',
      agent_model_name: 'llama3.2',
      ollama_url: 'http://localhost:11434',
      credentials: {},
    });
    spyOn(Api, 'fetchChatModels').and.resolveTo({
      cloud: [{ id: 'gpt-4.1-mini', name: 'gpt-4.1-mini', description: 'cloud', provider: 'openai', capabilities: [], metadata: {} }],
      local: [{ id: 'llama3.2', name: 'llama3.2', description: 'local', provider: 'ollama', capabilities: [], metadata: {} }],
    });
    spyOn(Api, 'updateChatSettings').and.callFake(async (payload) => payload as never);
    spyOn(Api, 'checkOllamaHealth').and.resolveTo({ ok: true, detail: 'ok' });
    spyOn(Api, 'refreshOllamaModels').and.resolveTo({});
    spyOn(Api, 'pullOllamaModel').and.resolveTo({});

    await TestBed.configureTestingModule({
      imports: [SettingsPageComponent],
      providers: [
        provideRouter([]),
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
    expect(Api.fetchChatSettings).toHaveBeenCalled();
    expect(Api.fetchChatModels).toHaveBeenCalled();

    (Api.fetchChatSettings as jasmine.Spy).and.rejectWith(new Error('boom'));
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
    expect(Api.updateChatSettings).toHaveBeenCalled();
    expect(component.statusText).toContain('Selected');
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
    component.openaiKey = 'sk-valid';
    await component.saveKeys();
    expect(component.statusText).toContain('API keys saved');

    (Api.updateChatSettings as jasmine.Spy).and.rejectWith(new Error('fail'));
    component.openaiKey = 'sk-valid';
    await component.saveKeys();
    expect(component.statusText).toContain('Could not save API keys right now.');
  });

  it('Ollama health success and degraded failure message formatting', async () => {
    const fixture = TestBed.createComponent(SettingsPageComponent);
    fixture.detectChanges();
    await fixture.whenStable();
    const component = fixture.componentInstance;
    await component.checkOllamaConnection();
    expect(component.statusText).toContain('Ollama:');

    (Api.checkOllamaHealth as jasmine.Spy).and.rejectWith(new Error('connection refused'));
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
    expect(window.location.search).toContain('q=gpt');
    expect(store.updateSettingsPage).toHaveBeenCalled();
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

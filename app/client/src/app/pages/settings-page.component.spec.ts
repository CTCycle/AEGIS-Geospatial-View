import { TestBed } from '@angular/core/testing';
import { Component, ChangeDetectionStrategy } from '@angular/core';
import { provideRouter, Router } from '@angular/router';

import { ApiClientService } from '../core/api-client.service';
import { defaultAppState } from '../core/app-state';
import { AppStateStoreService } from '../core/app-state-store.service';
import { UserFacingErrorService } from '../core/user-facing-error.service';
import { RuntimeSettingsResponse } from '../core/types';
import { SettingsPageComponent } from './settings-page.component';

@Component({ changeDetection: ChangeDetectionStrategy.Eager,
 template: '' })
class TestRouteComponent {}

const libraryResponse = (overrides: Partial<{ cloud: unknown[]; local: unknown[]; sources: Record<string, unknown> }> = {}) => ({
  cloud: overrides.cloud ?? [],
  local: overrides.local ?? [],
  sources: overrides.sources ?? { ollama: { ok: true, reachable: true, model_count: 0, message: null } },
});

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
  let fetchGeospatialProviderAccountSetupsMock: jasmine.Spy;
  let fetchRuntimeSettingsMock: jasmine.Spy;
  let updateRuntimeSettingsMock: jasmine.Spy;

  const runtimeSettingsResponse = (): RuntimeSettingsResponse => ({
    schema_version: 1,
    nominatim: { base_url: 'https://nominatim.example/search', user_agent: 'AEGIS-test', timeout: 10 },
    geospatial: { min_timeline_year: 1900, max_lat: 90, min_lat: -90, max_lon: 180, min_lon: -180, max_mercator_extent: 20037508 },
    map: { default_size_m: 500, render_delay_s: 1, tiles: 'OpenStreetMap' },
    jobs: { polling_interval: 1 },
    chat: { max_history_messages: 12, application_timezone: 'UTC' },
    openmeteo: { weather_base_url: 'https://weather.example', air_quality_base_url: 'https://air.example', user_agent: 'AEGIS-test', timeout: 15, cache_ttl_s: 600, min_call_interval_s: 0.15 },
    overpass: { base_url: 'https://overpass.example', user_agent: 'AEGIS-test', timeout: 20, cache_ttl_s: 600, min_call_interval_s: 0.2, default_radius_m: 2500, default_limit: 30 },
    rainviewer: { metadata_url: 'https://rain.example', user_agent: 'AEGIS-test', timeout: 15, cache_ttl_s: 300, min_call_interval_s: 0.2, tile_color_scheme: 2, tile_smooth: 1, tile_snow: 1 },
    gibs: {
      user_agent: 'AEGIS-test', timeout: 20, capabilities_ttl_s: 21600, max_cache_entries: 24, bbox_precision: 6,
      wms_base_endpoints: { 'EPSG:3857': 'https://gibs.example/3857', 'EPSG:4326': 'https://gibs.example/4326' },
      retry_backoff_s: 2, min_visual_radius_m: 20000, image_width: 1024, image_height: 1024,
      default_layer: 'VIIRS', capabilities_endpoints: { 'EPSG:4326': 'https://gibs.example/4326-cap' },
      ows_namespaces: { ows: 'https://ows.example' }, layer_sync_user_agent: 'AEGIS-test', layer_sync_timeout: 30,
    },
    agent_execution: {
      initial_run_seconds: 90, simple_seconds: 150, complex_seconds: 300, context_assembly_seconds: 5,
      native_model_call_seconds: 60, tool_execution_seconds: 45, tool_absolute_seconds: 90, map_assembly_seconds: 20,
      persistence_seconds: 5, render_ack_seconds: 90, max_tool_result_chars: 4096, max_iterations: 12,
      max_render_attempts: 3, max_no_progress_corrections: 2, simple_max_model_calls: 4, complex_max_model_calls: 10,
      simple_max_tool_calls: 6, complex_max_tool_calls: 20, simple_max_state_transitions: 32,
      complex_max_state_transitions: 64, max_parallel_tool_calls: 8, max_consecutive_tool_failures: 3,
      max_same_failed_fingerprint: 2, max_route_corrections: 1, max_validation_corrections: 2,
      model_max_attempts: 2, provider_max_attempts: 2, retry_backoff_base_seconds: 0.25,
      retry_backoff_max_seconds: 2, provider_request_seconds: 10,
    },
    restart_required: false,
    message: null,
  });

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
      'fetchGeospatialProviderAccountSetups',
      'fetchRuntimeSettings',
      'updateRuntimeSettings',
    ]);
    fetchChatSettingsMock = jasmine.createSpy('fetchChatSettings').and.resolveTo({
      active_provider_mode: 'cloud',
      agent_model_provider: '',
      agent_model_name: '',
      ollama_url: 'http://127.0.0.1:11434',
      openai_base_url: null,
      google_base_url: null,
      deepseek_base_url: null,
      credentials: {},
      credential_health: {},
    });
    fetchChatModelsMock = jasmine.createSpy('fetchChatModels').and.resolveTo(libraryResponse({
      cloud: [{ id: 'gpt-4.1-mini', name: 'gpt-4.1-mini', description: 'cloud', provider: 'openai', capabilities: [], metadata: {} }],
      local: [{ id: 'llama3.2', name: 'llama3.2', description: 'local', provider: 'ollama', capabilities: [], metadata: {} }],
      sources: { ollama: { ok: true, reachable: true, model_count: 1, message: null } },
    }));
    updateChatSettingsMock = jasmine.createSpy('updateChatSettings').and.callFake(async (payload) => payload as never);
    checkOllamaHealthMock = jasmine.createSpy('checkOllamaHealth').and.resolveTo({ ok: true, detail: 'ok' });
    refreshOllamaModelsMock = jasmine.createSpy('refreshOllamaModels').and.resolveTo({});
    pullOllamaModelMock = jasmine.createSpy('pullOllamaModel').and.resolveTo({});
    fetchGeospatialProviderAccountSetupsMock = jasmine.createSpy('fetchGeospatialProviderAccountSetups').and.resolveTo({ providers: [] });
    fetchRuntimeSettingsMock = jasmine.createSpy('fetchRuntimeSettings').and.resolveTo(runtimeSettingsResponse());
    updateRuntimeSettingsMock = jasmine.createSpy('updateRuntimeSettings').and.callFake(async () => runtimeSettingsResponse());

    apiClient.fetchChatSettings.and.callFake(() => fetchChatSettingsMock());
    apiClient.fetchChatModels.and.callFake((provider) => fetchChatModelsMock(provider));
    apiClient.updateChatSettings.and.callFake((payload) => updateChatSettingsMock(payload));
    apiClient.checkOllamaHealth.and.callFake(() => checkOllamaHealthMock());
    apiClient.refreshOllamaModels.and.callFake(() => refreshOllamaModelsMock());
    apiClient.pullOllamaModel.and.callFake((model) => pullOllamaModelMock(model));
    apiClient.fetchGeospatialProviderAccountSetups.and.callFake(() => fetchGeospatialProviderAccountSetupsMock());
    apiClient.fetchRuntimeSettings.and.callFake(() => fetchRuntimeSettingsMock());
    apiClient.updateRuntimeSettings.and.callFake((payload) => updateRuntimeSettingsMock(payload));

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

  it('parses only the UI catalog query params', () => {
    window.history.replaceState({}, '', '/settings?q=gpt&mode=cloud');
    const fixture = TestBed.createComponent(SettingsPageComponent);
    fixture.detectChanges();
    const component = fixture.componentInstance;
    expect(component.searchText).toBe('gpt');
    expect(component.settings.active_provider_mode).toBe('cloud');
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

  it('loads DeepSeek models when the DeepSeek filter is selected with a saved key', async () => {
    window.history.replaceState({}, '', '/settings');
    fetchChatSettingsMock.and.resolveTo({
      active_provider_mode: 'cloud',
      agent_model_provider: 'openai',
      agent_model_name: 'gpt-4.1-mini',
      ollama_url: 'http://127.0.0.1:11434',
      openai_base_url: null,
      google_base_url: null,
      deepseek_base_url: null,
      credentials: { deepseek: { api_key: true } },
      credential_health: { deepseek: { api_key: 'healthy' } },
    });
    fetchChatModelsMock.and.callFake(async (provider?: string) => (
      provider === 'deepseek'
        ? libraryResponse({
          cloud: [{ id: 'deepseek-v4-flash', name: 'deepseek-v4-flash', description: 'deepseek', provider: 'deepseek', capabilities: ['tools', 'structured_output'], supports_tools: true, supports_structured_output: true, metadata: {} }],
          local: [{ id: 'llama3.2', name: 'llama3.2', description: 'local', provider: 'ollama', capabilities: [], metadata: {} }],
          sources: {
            ollama: { ok: true, reachable: true, model_count: 1, message: null },
            deepseek: { ok: true, model_count: 1, message: null },
          },
        })
        : libraryResponse({
          cloud: [{ id: 'gpt-4.1-mini', name: 'gpt-4.1-mini', description: 'cloud', provider: 'openai', capabilities: [], metadata: {} }],
          local: [{ id: 'llama3.2', name: 'llama3.2', description: 'local', provider: 'ollama', capabilities: [], metadata: {} }],
          sources: { ollama: { ok: true, reachable: true, model_count: 1, message: null } },
        })
    ));
    const fixture = TestBed.createComponent(SettingsPageComponent);
    fixture.detectChanges();
    await fixture.whenStable();

    await fixture.componentInstance.setProviderFilter('deepseek');
    await fixture.whenStable();

    expect(fetchChatModelsMock).toHaveBeenCalledWith('deepseek');
    expect(fixture.componentInstance.displayedModels.some((model) => model.provider === 'deepseek')).toBeTrue();
  });

  it('surfaces DeepSeek load failures instead of showing a silent empty state', async () => {
    fetchChatSettingsMock.and.resolveTo({
      active_provider_mode: 'cloud',
      agent_model_provider: 'deepseek',
      agent_model_name: 'deepseek-chat',
      ollama_url: 'http://127.0.0.1:11434',
      openai_base_url: null,
      google_base_url: null,
      deepseek_base_url: null,
      credentials: { deepseek: { api_key: true } },
      credential_health: { deepseek: { api_key: 'healthy' } },
    });
    fetchChatModelsMock.and.callFake(async (provider?: string) => (
      provider === 'deepseek'
        ? libraryResponse({
          cloud: [],
          local: [],
          sources: {
            ollama: { ok: false, reachable: false, model_count: 0, message: 'Unable to reach Ollama.' },
            deepseek: { ok: false, model_count: 0, message: 'Could not load DeepSeek models right now.' },
          },
        })
        : libraryResponse({
          cloud: [{ id: 'gpt-4.1-mini', name: 'gpt-4.1-mini', description: 'cloud', provider: 'openai', capabilities: [], metadata: {} }],
          local: [],
          sources: { ollama: { ok: false, reachable: false, model_count: 0, message: 'Unable to reach Ollama.' } },
        })
    ));

    const fixture = TestBed.createComponent(SettingsPageComponent);
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.componentInstance.setProviderFilter('deepseek');
    await fixture.whenStable();
    fixture.detectChanges();

    expect(fixture.componentInstance.deepSeekLoadFailed).toBeTrue();
    expect(fixture.componentInstance.statusText).toContain('Could not load DeepSeek models right now.');
    expect(fixture.nativeElement.textContent).toContain('DeepSeek models could not be loaded.');
  });

  it('keeps the All provider filter active after the initial model load', async () => {
    window.history.replaceState({}, '', '/settings');
    const fixture = TestBed.createComponent(SettingsPageComponent);
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();

    const buttons = Array.from(
      fixture.nativeElement.querySelectorAll('.provider-filter-toggle button'),
    ) as HTMLButtonElement[];
    const activeButton = buttons.find((button) => button.classList.contains('active'));

    expect(activeButton?.textContent?.trim()).toBe('All');
    expect(fixture.componentInstance.displayedModels.length).toBeGreaterThan(0);
  });

  it('does not show an unavailable Ollama assignment warning when nothing is selected', async () => {
    const fixture = TestBed.createComponent(SettingsPageComponent);
    fixture.detectChanges();
    await fixture.whenStable();

    expect(fixture.componentInstance.unavailableAssignedOllamaModels).toEqual([]);
    expect(fixture.nativeElement.textContent).not.toContain('Assigned local model unavailable.');
  });

  it('keeps richer Ollama library descriptions for installed models', async () => {
    window.history.replaceState({}, '', '/settings');
    fetchChatModelsMock.and.resolveTo(libraryResponse({
      cloud: [{
        id: 'gemma4',
        name: 'gemma4',
        description: 'Detailed library description for the installed model family.',
        provider: 'ollama',
        capabilities: ['chat'],
        metadata: { source: 'library' },
      }],
      local: [{
        id: 'gemma4:31b',
        name: 'gemma4:31b',
        description: 'local',
        provider: 'ollama',
        capabilities: [],
        metadata: { quantization: 'Q4_K_M' },
      }],
      sources: { ollama: { ok: true, reachable: true, model_count: 1, message: null } },
    }));
    const fixture = TestBed.createComponent(SettingsPageComponent);
    fixture.detectChanges();
    await fixture.whenStable();
    const model = fixture.componentInstance.displayedModels.find((item) => item.id === 'gemma4:31b');
    expect(model?.description).toContain('Detailed library description');
  });

  it('does not treat cloud DeepSeek models as local when names overlap', async () => {
    window.history.replaceState({}, '', '/settings');
    fetchChatSettingsMock.and.resolveTo({
      active_provider_mode: 'cloud',
      agent_model_provider: '',
      agent_model_name: '',
      ollama_url: 'http://127.0.0.1:11434',
      openai_base_url: null,
      google_base_url: null,
      deepseek_base_url: null,
      credentials: { deepseek: { api_key: true } },
      credential_health: { deepseek: { api_key: 'healthy' } },
    });
    fetchChatModelsMock.and.callFake(async (provider?: string) => (
      provider === 'deepseek'
        ? libraryResponse({
          cloud: [{
            id: 'deepseek-chat',
            name: 'deepseek-chat',
            description: 'cloud deepseek',
            provider: 'deepseek',
            capabilities: ['tools', 'structured_output'],
            supports_tools: true,
            supports_structured_output: true,
            metadata: {},
          }],
          local: [{
            id: 'deepseek-chat',
            name: 'deepseek-chat',
            description: 'local',
            provider: 'ollama',
            capabilities: ['tools', 'structured_output'],
            supports_tools: true,
            supports_structured_output: true,
            metadata: {},
          }],
          sources: {
            ollama: { ok: true, reachable: true, model_count: 1, message: null },
            deepseek: { ok: true, model_count: 1, message: null },
          },
        })
        : libraryResponse({
          cloud: [],
          local: [{
            id: 'deepseek-chat',
            name: 'deepseek-chat',
            description: 'local',
            provider: 'ollama',
            capabilities: ['tools', 'structured_output'],
            supports_tools: true,
            supports_structured_output: true,
            metadata: {},
          }],
          sources: { ollama: { ok: true, reachable: true, model_count: 1, message: null } },
        })
    ));

    const fixture = TestBed.createComponent(SettingsPageComponent);
    fixture.detectChanges();
    await fixture.whenStable();
    await fixture.componentInstance.setProviderFilter('deepseek');
    await fixture.whenStable();

    const deepseekModel = fixture.componentInstance.displayedModels.find((model) => model.provider === 'deepseek');
    expect(deepseekModel).toBeDefined();
    expect(fixture.componentInstance.requiresPull(deepseekModel!)).toBeFalse();
    const summary = fixture.componentInstance.selectedAgentModelSummary;
    expect(summary?.provider === 'deepseek' ? summary.installedLocally : true).toBeTrue();
  });

  it('provides fallback descriptions for installed local models', async () => {
    const fixture = TestBed.createComponent(SettingsPageComponent);
    fixture.detectChanges();
    await fixture.whenStable();
    const localModel = {
      id: 'qwen2.5:7b',
      name: 'qwen2.5:7b',
      description: 'local',
      provider: 'ollama',
      capabilities: [],
      metadata: {},
    };
    expect(fixture.componentInstance.modelDescription(localModel)).toContain('Installed Ollama model');
  });

  it('applyAgentModelSelection updates settings and status text', async () => {
    const fixture = TestBed.createComponent(SettingsPageComponent);
    fixture.detectChanges();
    await fixture.whenStable();
    const component = fixture.componentInstance;
    await component.applyAgentModelSelection({
      id: 'gpt-4.1',
      name: 'gpt-4.1',
      description: 'agent model',
      provider: 'openai',
      capabilities: ['tools', 'structured_output'],
      supports_tools: true,
      supports_structured_output: true,
      metadata: {},
    });
    expect(updateChatSettingsMock).toHaveBeenCalled();
    expect(component.statusText).toContain('Selected');
  });

  it('applyAgentModelSelection updates the selected card state before the save completes', async () => {
    let resolveUpdate: ((value: unknown) => void) | undefined;
    updateChatSettingsMock.and.returnValue(new Promise((resolve) => {
      resolveUpdate = resolve;
    }));

    const fixture = TestBed.createComponent(SettingsPageComponent);
    fixture.detectChanges();
    await fixture.whenStable();
    const component = fixture.componentInstance;
    const model = {
      id: 'gpt-4.1',
      name: 'gpt-4.1',
      description: 'agent model',
      provider: 'openai',
      capabilities: ['tools', 'structured_output'],
      supports_tools: true,
      supports_structured_output: true,
      metadata: {},
    };

    const selectionPromise = component.applyAgentModelSelection(model);

    expect(component.isAgentModelSelected(model)).toBeTrue();
    expect(component.statusText).toContain('Selecting gpt-4.1 as agent model...');

    resolveUpdate?.({
      active_provider_mode: 'cloud',
      agent_model_provider: 'openai',
      agent_model_name: 'gpt-4.1',
      ollama_url: 'http://127.0.0.1:11434',
      openai_base_url: null,
      google_base_url: null,
      deepseek_base_url: null,
      credentials: {},
      credential_health: {},
    });
    await selectionPromise;

    expect(component.statusText).toContain('Selected gpt-4.1 as agent model');
  });

  it('pulls a missing Ollama model before assigning it', async () => {
    fetchChatModelsMock.and.resolveTo(libraryResponse({
      cloud: [{ id: 'llama3.1', name: 'llama3.1', description: 'library', provider: 'ollama', capabilities: ['structured_output', 'tools'], supports_tools: true, supports_structured_output: true, metadata: {} }],
      local: [],
      sources: { ollama: { ok: true, reachable: true, model_count: 0, message: null } },
    }));
    const fixture = TestBed.createComponent(SettingsPageComponent);
    fixture.detectChanges();
    await fixture.whenStable();
    const component = fixture.componentInstance;
    component.setProviderFilter('ollama');

    fetchChatModelsMock.and.resolveTo(libraryResponse({
      cloud: [{ id: 'llama3.1', name: 'llama3.1', description: 'library', provider: 'ollama', capabilities: ['structured_output', 'tools'], supports_tools: true, supports_structured_output: true, metadata: {} }],
      local: [{ id: 'llama3.1', name: 'llama3.1', description: 'local', provider: 'ollama', capabilities: ['structured_output', 'tools'], supports_tools: true, supports_structured_output: true, metadata: {} }],
      sources: { ollama: { ok: true, reachable: true, model_count: 1, message: null } },
    }));

    await component.applyAgentModelSelection({
      id: 'llama3.1',
      name: 'llama3.1',
      description: 'library',
      provider: 'ollama',
      capabilities: ['structured_output', 'tools'],
      supports_tools: true,
      supports_structured_output: true,
      metadata: {},
    });

    expect(pullOllamaModelMock).toHaveBeenCalledWith('llama3.1');
    expect(refreshOllamaModelsMock).toHaveBeenCalled();
    expect(updateChatSettingsMock).toHaveBeenCalled();
    expect(component.statusText).toContain('Selected llama3.1 as agent model');
  });

  it('applyAgentModelSelection does not send read-only credential health fields', async () => {
    fetchChatSettingsMock.and.resolveTo({
      active_provider_mode: 'local',
      agent_model_provider: 'ollama',
      agent_model_name: 'llama3.2',
      ollama_url: 'http://127.0.0.1:11434',
      openai_base_url: null,
      google_base_url: null,
      deepseek_base_url: null,
      credentials: { openai: { api_key: true }, google: { api_key: true } },
      credential_health: { openai: { api_key: 'unreadable' }, google: { api_key: 'healthy' } },
    });
    const fixture = TestBed.createComponent(SettingsPageComponent);
    fixture.detectChanges();
    await fixture.whenStable();

    await fixture.componentInstance.applyAgentModelSelection({
      id: 'llama3.2',
      name: 'llama3.2',
      description: 'agent model',
      provider: 'ollama',
      capabilities: ['tools', 'structured_output'],
      supports_tools: true,
      supports_structured_output: true,
      metadata: {},
    });

    const payload = updateChatSettingsMock.calls.mostRecent().args[0];
    expect(payload.credential_health).toBeUndefined();
    expect(payload.credentials.openai.api_key).toBeUndefined();
    expect(payload.credentials.google.api_key).toBeUndefined();
  });

  it('API key validation rules enforce OpenAI, Google, and DeepSeek prefixes', async () => {
    const fixture = TestBed.createComponent(SettingsPageComponent);
    fixture.detectChanges();
    await fixture.whenStable();
    const component = fixture.componentInstance;
    component.setCloudCredentialValue('openai', 'bad-openai-key');
    component.setCloudCredentialValue('google', 'bad-google-key');
    component.setCloudCredentialValue('deepseek', 'bad-deepseek-key');
    await component.saveCloudProvider('openai');
    await component.saveCloudProvider('google');
    await component.saveCloudProvider('deepseek');
    expect(component.keyValidationErrors.openai).toContain('sk-');
    expect(component.keyValidationErrors.google).toContain('AIza');
    expect(component.keyValidationErrors.deepseek).toContain('sk-');
  });

  it('saves one model-provider credential through the shared settings owner', async () => {
    const fixture = TestBed.createComponent(SettingsPageComponent);
    fixture.detectChanges();
    await fixture.whenStable();
    const component = fixture.componentInstance;
    const updated = {
      ...component.settings,
      credentials: { 'opencode-go': { api_key: true } },
      credential_health: { 'opencode-go': { api_key: 'healthy' } },
    };
    updateChatSettingsMock.and.resolveTo(updated);
    component.opencodeGoKey = 'go-secret-value-12345';

    await component.saveCloudProvider('opencode-go');

    const payload = updateChatSettingsMock.calls.mostRecent().args[0];
    expect(payload.credentials).toEqual({ 'opencode-go': { api_key: 'go-secret-value-12345' } });
    expect(payload.credential_health).toBeUndefined();
    expect(component.settings.credentials['opencode-go']?.api_key).toBeTrue();
    expect(component.opencodeGoKey).toBe('');
    expect(component.modelProviderHealth('opencode-go')).toContain('readable');
  });

  it('requires an explicit clear action and treats a blank draft as no replacement', async () => {
    const fixture = TestBed.createComponent(SettingsPageComponent);
    fixture.detectChanges();
    await fixture.whenStable();
    const component = fixture.componentInstance;
    const configured = {
      ...component.settings,
      credentials: { 'opencode-go': { api_key: true } },
      credential_health: { 'opencode-go': { api_key: 'healthy' } },
    };
    component.settings = configured;
    component.opencodeGoKey = '  ';
    const updateCallsBeforeBlankSave = updateChatSettingsMock.calls.count();

    await component.saveCloudProvider('opencode-go');

    expect(updateChatSettingsMock.calls.count()).toBe(updateCallsBeforeBlankSave);
    expect(component.keyValidationErrors['opencode-go']).toContain('Clear saved key');

    updateChatSettingsMock.and.resolveTo({
      ...configured,
      credentials: {},
      credential_health: {},
    });
    await component.clearCloudProvider('opencode-go');

    const clearPayload = updateChatSettingsMock.calls.mostRecent().args[0];
    expect(clearPayload.credentials).toEqual({ 'opencode-go': { api_key: '' } });
    expect(component.settings.credentials['opencode-go']).toBeUndefined();
  });

  it('saveOllamaSettings sends a sanitized update payload', async () => {
    fetchChatSettingsMock.and.resolveTo({
      active_provider_mode: 'local',
      agent_model_provider: 'ollama',
      agent_model_name: 'llama3.2',
      ollama_url: 'http://127.0.0.1:11434',
      openai_base_url: null,
      google_base_url: null,
      deepseek_base_url: null,
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

  it('reports unreadable credential health in model provider state', async () => {
    fetchChatSettingsMock.and.resolveTo({
      active_provider_mode: 'cloud',
      agent_model_provider: 'openai',
      agent_model_name: 'gpt-4.1-mini',
      ollama_url: 'http://127.0.0.1:11434',
      openai_base_url: null,
      google_base_url: null,
      deepseek_base_url: null,
      credentials: { openai: { api_key: true } },
      credential_health: { openai: { api_key: 'unreadable' } },
    });
    const fixture = TestBed.createComponent(SettingsPageComponent);
    fixture.detectChanges();
    await fixture.whenStable();

    expect(fixture.componentInstance.credentialHealthForTemplate('openai')).toBe('unreadable');
  });

  it('Ollama health success and degraded failure message formatting', async () => {
    const fixture = TestBed.createComponent(SettingsPageComponent);
    fixture.detectChanges();
    await fixture.whenStable();
    const component = fixture.componentInstance;
    await component.checkOllamaConnection();
    expect(component.statusText).toContain('Ollama:');
    expect(fixture.nativeElement.textContent).toContain('Connection is healthy.');

    checkOllamaHealthMock.and.rejectWith(new Error('connection refused'));
    await component.checkOllamaConnection();
    expect(component.statusText).toContain('Unable to reach Ollama');
    expect(fixture.nativeElement.textContent).toContain('Unable to reach Ollama');
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

  it('prevents overlapping refresh requests', async () => {
    let releaseRefresh: (() => void) | undefined;
    refreshOllamaModelsMock.and.returnValue(new Promise((resolve) => {
      releaseRefresh = () => resolve({});
    }));
    const fixture = TestBed.createComponent(SettingsPageComponent);
    fixture.detectChanges();
    await fixture.whenStable();
    const component = fixture.componentInstance;

    const firstRefresh = component.refreshOllamaLibrary();
    const secondRefresh = component.refreshOllamaLibrary();

    expect(refreshOllamaModelsMock).toHaveBeenCalledTimes(1);
    expect(component.isRefreshingOllama).toBeTrue();

    releaseRefresh?.();
    await Promise.all([firstRefresh, secondRefresh]);
    expect(component.isRefreshingOllama).toBeFalse();
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

  it('gives credential fields unique label associations', async () => {
    const fixture = TestBed.createComponent(SettingsPageComponent);
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.componentInstance.activeSection = 'model-providers';
    fixture.detectChanges();

    const inputs = Array.from(fixture.nativeElement.querySelectorAll('input[type="password"]')) as HTMLInputElement[];
    const ids = inputs.map((input) => input.id);
    expect(ids.length).toBeGreaterThan(0);
    expect(new Set(ids).size).toBe(ids.length);
    ids.forEach((id) => {
      expect(fixture.nativeElement.querySelector(`label[for="${id}"]`)).not.toBeNull();
    });
  });

  it('renders model cards through the extracted model card component host', async () => {
    const fixture = TestBed.createComponent(SettingsPageComponent);
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();
    expect(fixture.nativeElement.querySelectorAll('article.model-card').length).toBeGreaterThan(0);
  });

  it('normalizes the Settings query and exposes the persistent sidebar sections', async () => {
    window.history.replaceState({}, '', '/settings?tab=unknown');
    const fixture = TestBed.createComponent(SettingsPageComponent);
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();

    const sections = Array.from(fixture.nativeElement.querySelectorAll('.settings-sidebar__item')) as HTMLButtonElement[];
    expect(fixture.componentInstance.activeSection).toBe('models');
    expect(sections).toHaveSize(7);
    expect(sections[0].getAttribute('aria-current')).toBe('page');
    expect(fixture.nativeElement.querySelector('[role="tab"]')).toBeNull();
  });

  it('moves Settings sections with clicks and router history', async () => {
    window.history.replaceState({}, '', '/settings');
    const navigateSpy = spyOn(router, 'navigateByUrl').and.resolveTo(true);
    const fixture = TestBed.createComponent(SettingsPageComponent);
    fixture.detectChanges();
    await fixture.whenStable();
    const sections = Array.from(fixture.nativeElement.querySelectorAll('.settings-sidebar__item')) as HTMLButtonElement[];
    sections[1].click();
    fixture.detectChanges();
    expect(fixture.componentInstance.activeSection).toBe('model-providers');
    expect(navigateSpy).toHaveBeenCalledWith('/settings?tab=model-providers');

    sections[6].click();
    fixture.detectChanges();
    expect(fixture.componentInstance.activeSection).toBe('agent-runtime');
    expect(navigateSpy).toHaveBeenCalledWith('/settings?tab=agent-runtime');
  });

  it('renders manifest-driven geospatial access providers in the shared Settings page', async () => {
    fetchGeospatialProviderAccountSetupsMock.and.resolveTo({
      providers: [{
        providerId: 'tomtom',
        name: 'TomTom',
        requiresCredentials: true,
        authMode: 'api-key',
        docsUrl: 'https://developer.tomtom.com/',
        configured: false,
        instructions: ['Create a key in the provider portal.'],
        automation: {
          support: 'manual_only',
          signupUrl: 'https://developer.tomtom.com/',
          developerPortalUrl: 'https://developer.tomtom.com/',
          docsUrl: 'https://developer.tomtom.com/',
          requiredFields: [],
          userActionNotes: ['Paste the key back into AEGIS.'],
          safetyNotes: ['AEGIS never collects provider passwords.'],
          experimental: true,
          experimentalLabel: 'Manual setup guidance',
        },
        credentialStorageKey: 'tomtom',
        credentialLabel: 'api_key',
        keyFormatHint: 'TomTom API key',
        validationSupported: true,
      }],
    });
    const fixture = TestBed.createComponent(SettingsPageComponent);
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.componentInstance.activeSection = 'geospatial-access';
    fixture.detectChanges();

    expect(fixture.nativeElement.textContent).toContain('TomTom');
    expect(fixture.nativeElement.textContent).toContain('Save key');
    expect(fixture.nativeElement.querySelector('input[type="password"]')).not.toBeNull();
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

import { CommonModule } from '@angular/common';
import { AfterViewInit, ChangeDetectorRef, Component, ElementRef, OnDestroy, OnInit, ViewChild, ChangeDetectionStrategy } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { NavigationEnd, Router } from '@angular/router';
import { Subscription } from 'rxjs';

import { ModelCardComponent } from '../components/model-card.component';
import { SelectedModelSummaryComponent } from '../components/selected-model-summary.component';
import { SettingsApiKeyFieldComponent } from '../components/settings-api-key-field.component';
import { SettingsModalShellComponent } from '../components/settings-modal-shell.component';
import { SettingsWarningBannerComponent } from '../components/settings-warning-banner.component';
import { ApiClientService } from '../core/api-client.service';
import { AppStateStoreService } from '../core/app-state-store.service';
import { PersistedSettingsPageState } from '../core/app-state';
import {
  ApiKeyValidationErrors,
  CloudCredentialProvider,
  ModelProviderFilter,
  buildSettingsUpdateBase,
} from '../core/chat-settings-update';
import { CredentialSettingsService } from '../core/credential-settings.service';
import {
  agentSelectionDisabledReason,
  buildAgentModelSelectionPayload,
  buildSelectedAgentModelSummary,
  ensureSelectedModelVisible,
  enrichInstalledOllamaModel,
  isSelectedAgentModel,
  mergeModelCards,
  modelDisplayDescription,
  providerDisplayLabel,
  SelectedAgentModelSummary,
} from '../core/model-selection';
import {
  isDynamicCloudProvider,
  mergeModelLibraries,
  type DynamicCloudProvider,
} from '../core/model-library';
import {
  ModelCardDescriptor,
  GeospatialProviderAccountSetup,
  ModelLibraryResponse,
  ModelLibrarySourceStatus,
  ModelSettingsResponse,
  ModelSettingsUpdateRequest,
  OllamaHealthResponse,
  RuntimeSettingsResponse,
  RuntimeSettingsUpdateRequest,
  StructuredProbeResponse,
} from '../core/types';
import { UserFacingErrorService } from '../core/user-facing-error.service';
import { ViewStateSyncService } from '../core/view-state-sync.service';

export type SettingsSectionId =
  | 'models'
  | 'model-providers'
  | 'geospatial-access'
  | 'application'
  | 'map-search'
  | 'data-sources'
  | 'agent-runtime';

export const SETTINGS_SECTIONS: readonly { id: SettingsSectionId; label: string }[] = [
  { id: 'models', label: 'Models' },
  { id: 'model-providers', label: 'Model Providers' },
  { id: 'geospatial-access', label: 'Geospatial Access' },
  { id: 'application', label: 'Application' },
  { id: 'map-search', label: 'Map & Search' },
  { id: 'data-sources', label: 'Data Sources' },
  { id: 'agent-runtime', label: 'Agent Runtime' },
];

const normalizeSettingsSection = (value: string | null | undefined): SettingsSectionId => (
  SETTINGS_SECTIONS.some((section) => section.id === value)
    ? value as SettingsSectionId
    : 'models'
);

const createDefaultRuntimeSettings = (): RuntimeSettingsResponse => ({
  schema_version: 1,
  nominatim: {
    base_url: 'https://nominatim.openstreetmap.org/search',
    user_agent: 'AEGIS-Geographics/1.0 (contact: support@aegis-geographics.local)',
    timeout: 10,
  },
  geospatial: {
    min_timeline_year: 1900,
    max_lat: 90,
    min_lat: -90,
    max_lon: 180,
    min_lon: -180,
    max_mercator_extent: 20037508.3427892,
  },
  map: { default_size_m: 500, render_delay_s: 1, tiles: 'OpenStreetMap' },
  jobs: { polling_interval: 1 },
  chat: { max_history_messages: 12, application_timezone: 'UTC' },
  openmeteo: {
    weather_base_url: 'https://api.open-meteo.com/v1/forecast',
    air_quality_base_url: 'https://air-quality-api.open-meteo.com/v1/air-quality',
    user_agent: 'AEGIS-OpenMeteo/1.0',
    timeout: 15,
    cache_ttl_s: 600,
    min_call_interval_s: 0.15,
  },
  overpass: {
    base_url: 'https://overpass-api.de/api/interpreter',
    user_agent: 'AEGIS-Overpass/1.0',
    timeout: 20,
    cache_ttl_s: 600,
    min_call_interval_s: 0.2,
    default_radius_m: 2500,
    default_limit: 30,
  },
  rainviewer: {
    metadata_url: 'https://api.rainviewer.com/public/weather-maps.json',
    user_agent: 'AEGIS-RainViewer/1.0',
    timeout: 15,
    cache_ttl_s: 300,
    min_call_interval_s: 0.2,
    tile_color_scheme: 2,
    tile_smooth: 1,
    tile_snow: 1,
  },
  gibs: {
    user_agent: 'AEGIS-GIBS/1.0',
    timeout: 20,
    capabilities_ttl_s: 21600,
    max_cache_entries: 24,
    bbox_precision: 6,
    wms_base_endpoints: {
      'EPSG:3857': 'https://gibs.earthdata.nasa.gov/wms/epsg3857/best/wms.cgi',
      'EPSG:4326': 'https://gibs.earthdata.nasa.gov/wms/epsg4326/best/wms.cgi',
    },
    retry_backoff_s: 2,
    min_visual_radius_m: 20000,
    image_width: 1024,
    image_height: 1024,
    default_layer: 'VIIRS_SNPP_CorrectedReflectance_TrueColor',
    capabilities_endpoints: {
      'EPSG:4326': 'https://gibs.earthdata.nasa.gov/wmts/epsg4326/best/1.0.0/WMTSCapabilities.xml',
      'EPSG:3857': 'https://gibs.earthdata.nasa.gov/wmts/epsg3857/best/1.0.0/WMTSCapabilities.xml',
      'EPSG:3413': 'https://gibs.earthdata.nasa.gov/wmts/epsg3413/best/1.0.0/WMTSCapabilities.xml',
      'EPSG:3031': 'https://gibs.earthdata.nasa.gov/wmts/epsg3031/best/1.0.0/WMTSCapabilities.xml',
    },
    ows_namespaces: { ows: 'http://www.opengis.net/ows/1.1' },
    layer_sync_user_agent: 'AEGIS-GIBS-LayerSync/1.0',
    layer_sync_timeout: 30,
  },
  agent_execution: {
    initial_run_seconds: 90,
    simple_seconds: 150,
    complex_seconds: 300,
    context_assembly_seconds: 5,
    native_model_call_seconds: 60,
    tool_execution_seconds: 45,
    tool_absolute_seconds: 90,
    map_assembly_seconds: 20,
    persistence_seconds: 5,
    render_ack_seconds: 90,
    max_tool_result_chars: 4096,
    max_iterations: 12,
    max_render_attempts: 3,
    max_no_progress_corrections: 2,
    simple_max_model_calls: 4,
    complex_max_model_calls: 10,
    simple_max_tool_calls: 6,
    complex_max_tool_calls: 20,
    simple_max_state_transitions: 32,
    complex_max_state_transitions: 64,
    max_parallel_tool_calls: 8,
    max_consecutive_tool_failures: 3,
    max_same_failed_fingerprint: 2,
    max_route_corrections: 1,
    max_validation_corrections: 2,
    model_max_attempts: 2,
    provider_max_attempts: 2,
    retry_backoff_base_seconds: 0.25,
    retry_backoff_max_seconds: 2,
    provider_request_seconds: 10,
  },
  restart_required: false,
  message: null,
});

const cloneRuntimeSettings = (settings: RuntimeSettingsResponse): RuntimeSettingsResponse =>
  JSON.parse(JSON.stringify(settings)) as RuntimeSettingsResponse;

interface GeoProviderAccess {
  id: string;
  name: string;
  purpose: string;
  placeholder: string;
  docsUrl: string;
  requiresCredentials: boolean;
  instructions: string[];
}

@Component({
  selector: 'app-settings-page',
  standalone: true,
  imports: [
    CommonModule,
    FormsModule,
    ModelCardComponent,
    SettingsApiKeyFieldComponent,
    SettingsModalShellComponent,
    SettingsWarningBannerComponent,
    SelectedModelSummaryComponent,
  ],
  templateUrl: './settings-page.component.html',
  changeDetection: ChangeDetectionStrategy.Eager,
  styleUrl: './settings-page.component.css',
})
export class SettingsPageComponent implements OnInit, AfterViewInit, OnDestroy {
  @ViewChild('modelGridScroll', { static: false }) modelGridRef?: ElementRef<HTMLDivElement>;

  readonly settingsSections = SETTINGS_SECTIONS;
  readonly cloudProviders: readonly {
    id: CloudCredentialProvider;
    name: string;
    purpose: string;
    placeholder: string;
    hint?: string;
  }[] = [
    { id: 'openai', name: 'OpenAI', purpose: 'Cloud models for general agent routing and chat.', placeholder: 'sk-...', hint: 'Stored credentials are masked and are never returned to the browser.' },
    { id: 'google', name: 'Google', purpose: 'Google model access for agent routing and chat.', placeholder: 'AIza...', hint: 'Stored credentials are masked and are never returned to the browser.' },
    { id: 'deepseek', name: 'DeepSeek', purpose: 'Discover and run models through the DeepSeek API.', placeholder: 'sk-...', hint: 'A saved key enables live DeepSeek model discovery.' },
    { id: 'opencode', name: 'OpenCode Zen', purpose: 'Discover and run OpenCode Zen OpenAI-compatible models.', placeholder: 'OpenCode API key', hint: 'OpenCode Zen model availability comes from its live account catalog.' },
    { id: 'opencode-go', name: 'OpenCode Go', purpose: 'Discover and run OpenCode Go OpenAI-compatible models.', placeholder: 'OpenCode API key', hint: 'DeepSeek V4.1 Flash is identified as deepseek-v4.1-flash when published by the live catalog.' },
  ];
  activeSection: SettingsSectionId = 'models';
  readonly state: PersistedSettingsPageState;
  settings: ModelSettingsResponse = {
    active_provider_mode: 'cloud',
    agent_model_provider: '',
    agent_model_name: '',
    ollama_url: 'http://127.0.0.1:11434',
    openai_base_url: null,
    google_base_url: null,
    deepseek_base_url: null,
    credentials: {},
    credential_health: {},
    selected_model_context: {
      provider: '',
      model: '',
      context_window_tokens: null,
      maximum_output_tokens: null,
      context_profile_source: 'unknown',
    },
  };

  cloudModels: ModelCardDescriptor[] = [];
  localModels: ModelCardDescriptor[] = [];

  searchText: string;
  statusText = 'Ready';
  isLoadingModels = false;
  isRefreshingOllama = false;
  isLoadingDynamicProviderModels = false;

  isSavingCredential = false;
  openaiKey = '';
  googleKey = '';
  deepseekKey = '';
  opencodeKey = '';
  opencodeGoKey = '';
  ollamaUrlDraft = 'http://127.0.0.1:11434';
  ollamaStatusText = '';
  keyValidationErrors: ApiKeyValidationErrors = {};
  ollamaStatus: ModelLibrarySourceStatus | null = null;
  deepseekStatus: ModelLibrarySourceStatus | null = null;
  opencodeStatus: ModelLibrarySourceStatus | null = null;
  opencodeGoStatus: ModelLibrarySourceStatus | null = null;
  structuredProbe: StructuredProbeResponse = {
    provider: '',
    model: '',
    protocol: 'unknown',
    status: 'not_tested',
    parse_status: 'not_tested',
    duration_ms: null,
    checked_at: null,
    expires_at: null,
    message: 'This model has not been verified against the native route/tool contract.',
  };
  isTestingStructuredProbe = false;

  runtimeSettings: RuntimeSettingsResponse = createDefaultRuntimeSettings();
  runtimeSettingsDraft: RuntimeSettingsResponse = cloneRuntimeSettings(this.runtimeSettings);
  runtimeSettingsError = '';
  isLoadingRuntimeSettings = false;
  isSavingRuntimeSettings = false;
  runtimeRestartRequired = false;

  providerFilter: ModelProviderFilter = 'all';
  private isDestroyed = false;
  private routerEventsSubscription?: Subscription;

  constructor(
    private readonly apiClient: ApiClientService,
    private readonly appStateStore: AppStateStoreService,
    private readonly userFacingErrorService: UserFacingErrorService,
    private readonly viewStateSync: ViewStateSyncService,
    private readonly credentialSettingsService: CredentialSettingsService,
    private readonly router: Router,
    private readonly changeDetectorRef: ChangeDetectorRef,
  ) {
    this.state = this.appStateStore.getSettingsPage();
    const query = new URLSearchParams(window.location.search);
    this.searchText = query.get('q') ?? this.state.searchText;
    this.activeSection = normalizeSettingsSection(query.get('tab'));
  }

  ngOnInit(): void {
    this.routerEventsSubscription = this.router.events.subscribe((event) => {
      if (event instanceof NavigationEnd && event.urlAfterRedirects.startsWith('/settings')) {
        this.applyUrlState(event.urlAfterRedirects);
      }
    });
    // Replace invalid or non-canonical tab values before the async settings
    // load completes, so the public URL contract is stable on first paint.
    this.syncQueryState();
    void this.loadData();
    void this.loadRuntimeSettings();
    void this.loadProviderAccountSetups();
    this.syncState();
  }

  ngAfterViewInit(): void {
    this.viewStateSync.restoreWindowScroll(this.state.scrollY);
    if (this.providerFilter === 'all') {
      this.resetModelGridScroll();
      return;
    }
    this.viewStateSync.restoreElementScroll(this.modelGridRef?.nativeElement, this.state.modelGridScrollTop);
  }

  ngOnDestroy(): void {
    this.isDestroyed = true;
    this.routerEventsSubscription?.unsubscribe();
    this.syncState();
  }

  get displayedModels(): ModelCardDescriptor[] {
    const source = (() => {
      if (this.providerFilter === 'all') {
        return mergeModelCards(this.localModels, this.cloudModels);
      }
      if (this.providerFilter === 'ollama') {
        return mergeModelCards(
          this.localModels,
          this.cloudModels.filter((model) => model.provider === 'ollama'),
        );
      }
      return this.cloudModels.filter((model) => model.provider === this.providerFilter);
    })();
    const visibleSource = this.providerFilter === 'all'
      || this.providerFilter === this.settings.agent_model_provider
      ? ensureSelectedModelVisible(this.settings, source)
      : source;

    const query = this.searchText.trim().toLowerCase();
    return visibleSource.filter((model) => {
      if (!query) {
        return true;
      }
      return model.name.toLowerCase().includes(query)
        || model.description.toLowerCase().includes(query)
        || model.provider.toLowerCase().includes(query);
    });
  }

  get groupedDisplayedModels(): Record<string, ModelCardDescriptor[]> {
    return this.displayedModels.reduce<Record<string, ModelCardDescriptor[]>>((acc, model) => {
      const key = model.provider === 'ollama'
        ? (this.isInstalledOllamaModel(model) ? 'ollama-installed' : 'ollama-library')
        : model.provider.toLowerCase();
      if (!acc[key]) {
        acc[key] = [];
      }
      acc[key].push(model);
      return acc;
    }, {});
  }

  get providerKeys(): string[] {
    return Object.keys(this.groupedDisplayedModels);
  }

  providerLabel(providerKey: string): string {
    return providerDisplayLabel(providerKey);
  }

  trackProviderGroup(provider: string): string {
    return provider;
  }

  get hasDisplayedModels(): boolean {
    return this.displayedModels.length > 0;
  }

  get localModelIds(): Set<string> {
    return new Set(this.localModels.map((item) => item.id));
  }

  get selectedAgentModelSummary(): SelectedAgentModelSummary | null {
    return buildSelectedAgentModelSummary(
      this.settings,
      this.localModelIds,
      ensureSelectedModelVisible(
        this.settings,
        mergeModelCards(this.localModels, this.cloudModels),
      ),
    );
  }

  get structuredProbeLabel(): string {
    if (this.structuredProbe.status === 'passed') return 'Verified';
    if (this.structuredProbe.status === 'not_tested') return 'Not verified';
    return 'Needs attention';
  }

  async testSelectedModel(): Promise<void> {
    if (
      !this.settings.agent_model_provider
      || !this.settings.agent_model_name
      || this.isTestingStructuredProbe
    ) {
      return;
    }
    this.isTestingStructuredProbe = true;
    this.statusText = `Testing ${this.settings.agent_model_name} against the native route/tool contract...`;
    this.changeDetectorRef.detectChanges();
    try {
      this.structuredProbe = await this.apiClient.runStructuredProbe();
      this.statusText = this.structuredProbe.message ?? 'Native structured-response probe completed.';
    } catch (error: unknown) {
      this.statusText = this.userFacingErrorService.toUserFacingError(
        error,
        'Could not run the native structured-response probe.',
      );
    } finally {
      this.isTestingStructuredProbe = false;
      this.syncState();
      this.changeDetectorRef.detectChanges();
    }
  }

  get unavailableAssignedOllamaModels(): string[] {
    const assignedModels = [
      this.settings.agent_model_provider === 'ollama' ? this.settings.agent_model_name : '',
    ].filter(Boolean);
    return [...new Set(assignedModels.filter((model) => !this.localModelIds.has(model)))];
  }

  get visibleStatusText(): string {
    return this.userFacingErrorService.normalizeDisplayText(this.statusText);
  }

  get visibleOllamaStatusText(): string {
    return this.userFacingErrorService.normalizeDisplayText(
      this.ollamaStatusText,
      `Unable to reach Ollama at ${this.settings.ollama_url || this.ollamaUrlDraft}. Check that the service is running and the URL is correct.`,
    );
  }

  get deepSeekLoadFailed(): boolean {
    return this.providerFilter === 'deepseek' && this.deepseekStatus !== null && !this.deepseekStatus.ok;
  }

  get unavailableAssignedOllamaModelsMessage(): string {
    const models = this.unavailableAssignedOllamaModels;
    return `${models.join(', ')} ${models.length === 1 ? 'is' : 'are'} selected but not installed in Ollama. Pull the model or select an installed local model before using the workspace.`;
  }

  get deepSeekFailureMessage(): string {
    if (!this.deepSeekLoadFailed) {
      return '';
    }
    return this.deepseekStatus?.message || 'Could not load DeepSeek models right now.';
  }

  get dynamicProvider(): DynamicCloudProvider | null {
    if (isDynamicCloudProvider(this.providerFilter)) {
      return this.providerFilter;
    }
    if (isDynamicCloudProvider(this.settings.agent_model_provider)) {
      return this.settings.agent_model_provider;
    }
    return null;
  }

  get dynamicProviderStatus(): ModelLibrarySourceStatus | null {
    const provider = this.dynamicProvider;
    if (provider === 'deepseek') return this.deepseekStatus;
    if (provider === 'opencode') return this.opencodeStatus;
    if (provider === 'opencode-go') return this.opencodeGoStatus;
    return null;
  }

  get dynamicProviderLabel(): string {
    return this.dynamicProvider ? providerDisplayLabel(this.dynamicProvider) : 'Cloud provider';
  }

  get dynamicProviderLoadFailed(): boolean {
    return this.dynamicProviderStatus !== null && !this.dynamicProviderStatus.ok;
  }

  get dynamicProviderFailureMessage(): string {
    return this.dynamicProviderStatus?.message || `Could not load ${this.dynamicProviderLabel} models right now.`;
  }

  isActiveSection(section: SettingsSectionId): boolean {
    return this.activeSection === section;
  }

  setSettingsSection(section: string): void {
    const nextSection = normalizeSettingsSection(section);
    this.activeSection = nextSection;
    if (typeof window === 'undefined') {
      return;
    }
    const params = new URLSearchParams();
    if (this.searchText.trim()) {
      params.set('q', this.searchText.trim());
    }
    if (nextSection !== 'models') {
      params.set('tab', nextSection);
    }
    const query = params.toString();
    void this.router.navigateByUrl(query ? `/settings?${query}` : '/settings');
  }

  setSearchText(value: string): void {
    this.searchText = value;
    this.syncQueryState();
    this.syncState();
  }

  async setProviderFilter(filter: ModelProviderFilter): Promise<void> {
    this.providerFilter = filter;
    this.resetModelGridScroll();
    this.syncState();
    await this.ensureProviderModelsLoaded(filter);
  }

  async applyAgentModelSelection(model: ModelCardDescriptor): Promise<void> {
    if (model.provider === 'ollama' && !this.isInstalledOllamaModel(model)) {
      const pulled = await this.pullLocalModel(model);
      if (!pulled || !this.isInstalledOllamaModel(model)) {
        return;
      }
    }
    const payload = buildAgentModelSelectionPayload(this.settings, model);
    const previousSettings = this.settings;
    const nextProviderMode = model.provider === 'ollama' ? 'local' : 'cloud';
    try {
      this.settings = {
        ...this.settings,
        active_provider_mode: nextProviderMode,
        agent_model_provider: model.provider,
        agent_model_name: model.name,
      };
      this.statusText = `Selecting ${model.name} as agent model...`;
      this.syncState();
      // Keep the optimistic selected-card state visible while the save is pending.
      this.changeDetectorRef.detectChanges();
      const updated = await this.saveModelSettings(payload);
      if (this.isDestroyed) {
        return;
      }
      this.settings = updated;
      this.structuredProbe = this.unverifiedProbe(updated);
      this.statusText = `Selected ${model.name} as agent model`;
      this.syncState();
    } catch (error: unknown) {
      if (this.isDestroyed) {
        return;
      }
      this.settings = previousSettings;
      this.statusText = this.userFacingErrorService.toUserFacingError(error, `Could not select ${model.name} as agent model.`);
      this.syncState();
      this.changeDetectorRef.detectChanges();
    }
  }

  async checkOllamaConnection(): Promise<void> {
    try {
      const health = await this.apiClient.checkOllamaHealth();
      const summary = this.formatOllamaHealthSummary(health);
      this.ollamaStatusText = summary;
      this.statusText = `Ollama: ${summary}`;
      this.syncState();
      this.changeDetectorRef.detectChanges();
    } catch (error: unknown) {
      const detail = this.getOllamaFailureMessage(error);
      this.statusText = detail;
      this.ollamaStatusText = detail;
      this.changeDetectorRef.detectChanges();
    }
  }

  async refreshOllamaLibrary(): Promise<void> {
    if (this.isRefreshingOllama) {
      return;
    }
    this.isRefreshingOllama = true;
    this.statusText = 'Refreshing Ollama library';
    this.syncState();
    try {
      await this.apiClient.refreshOllamaModels();
      await this.reloadOllamaCatalog();
      this.statusText = 'Ollama library refreshed';
      this.ollamaStatusText = 'Model library refreshed.';
      this.syncState();
    } catch (error: unknown) {
      const detail = this.getOllamaFailureMessage(error);
      this.statusText = detail;
      this.ollamaStatusText = detail;
    } finally {
      this.isRefreshingOllama = false;
    }
  }

  async saveOllamaSettings(): Promise<void> {
    try {
      const updated = await this.apiClient.updateChatSettings({
        ...this.settingsUpdateBase(),
        ollama_url: this.ollamaUrlDraft.trim() || 'http://127.0.0.1:11434',
      });
      this.settings = updated;
      this.structuredProbe = this.unverifiedProbe(updated);
      this.ollamaUrlDraft = updated.ollama_url;
      await this.reloadOllamaCatalog();
      this.statusText = 'Ollama settings saved';
      this.ollamaStatusText = 'Ollama settings saved.';
      this.syncState();
    } catch (error: unknown) {
      const detail = this.getOllamaFailureMessage(error);
      this.statusText = detail;
      this.ollamaStatusText = detail;
    }
  }

  async pullLocalModel(model: ModelCardDescriptor): Promise<boolean> {
    try {
      await this.apiClient.pullOllamaModel(model.name);
      await this.apiClient.refreshOllamaModels();
      await this.reloadOllamaCatalog();
      this.statusText = `Pulled ${model.name}`;
      this.syncState();
      return true;
    } catch (error: unknown) {
      this.statusText = this.userFacingErrorService.toUserFacingError(error, `Could not pull ${model.name}.`);
      return false;
    }
  }

  geoProviderConfigured(provider: string): boolean {
    return Boolean(this.settings.credentials[provider]?.['api_key']);
  }

  geoProviderHealth(provider: string): string {
    const status = this.settings.credential_health?.[provider]?.['api_key'];
    if (status === 'unreadable') {
      return 'Saved key cannot be read';
    }
    if (status === 'healthy' || status === 'stored' || this.geoProviderConfigured(provider)) {
      return 'Saved key is readable (not validated)';
    }
    return 'Not configured';
  }

  geoProviderCredentialHealth(provider: string): string | null {
    return this.settings.credential_health?.[provider]?.['api_key'] ?? null;
  }

  geoProviderSetup(provider: string): GeospatialProviderAccountSetup | undefined {
    return this.providerAccountSetups.find(
      (setup) => setup.providerId === provider || setup.credentialStorageKey === provider,
    );
  }

  canShowGeoSignupTrigger(provider: string): boolean {
    const setup = this.geoProviderSetup(provider);
    return Boolean(setup?.automation.developerPortalUrl || setup?.automation.signupUrl || setup?.automation.docsUrl);
  }

  openGeoProviderSignup(provider: string): void {
    const setup = this.geoProviderSetup(provider);
    if (!setup) return;
    this.selectedProviderAccountSetup = setup;
    this.signupKeyInput = '';
    this.signupModalError = '';
    this.isSignupModalOpen = true;
  }

  closeProviderSignup(): void {
    this.isSignupModalOpen = false;
    this.selectedProviderAccountSetup = undefined;
    this.signupModalError = '';
    this.signupKeyInput = '';
  }

  openProviderPortal(setup: GeospatialProviderAccountSetup): void {
    const target = setup.automation.developerPortalUrl
      ?? setup.automation.signupUrl
      ?? setup.automation.docsUrl
      ?? setup.docsUrl;
    if (!target) {
      this.signupModalError = 'No provider portal link is available for this setup.';
      return;
    }
    window.open(target, '_blank', 'noreferrer');
  }

  async saveGeoProvider(provider: string): Promise<void> {
    const setup = this.geoProviderSetup(provider);
    if (!setup || !setup.requiresCredentials || this.isSavingGeospatialCredential) {
      return;
    }
    const draft = this.geoCredentialDrafts[provider]?.trim() ?? '';
    if (!draft) {
      this.statusText = `Enter a ${setup.name} API key before saving, or clear the saved key.`;
      return;
    }
    await this.persistGeospatialCredential(provider, draft);
  }

  async clearGeoProvider(provider: string): Promise<void> {
    const setup = this.geoProviderSetup(provider);
    if (!setup || !this.geoProviderConfigured(provider) || this.isSavingGeospatialCredential) {
      return;
    }
    await this.persistGeospatialCredential(provider, '');
  }

  geoCredentialDrafts: Record<string, string> = {};

  setGeoCredentialDraft(provider: string, value: string): void {
    this.geoCredentialDrafts[provider] = value;
  }

  supportLabel(setup: GeospatialProviderAccountSetup): string {
    const labels: Record<string, string> = {
      agent_assisted: 'Agent-assisted guidance',
      guided_playwright: 'Guided browser setup',
      manual_only: 'Manual setup guidance',
      unsupported: 'Documentation only',
    };
    return labels[setup.automation.support] ?? setup.automation.support;
  }

  async saveGeneratedCredential(setup: GeospatialProviderAccountSetup): Promise<void> {
    if (setup.automation.support === 'unsupported') {
      this.signupModalError = 'This provider is documentation-only until automation support is verified.';
      return;
    }
    const value = this.signupKeyInput.trim();
    if (!value) {
      this.signupModalError = 'Paste the generated API key before saving.';
      return;
    }
    if (await this.persistGeospatialCredential(setup.credentialStorageKey, value)) {
      this.closeProviderSignup();
    }
  }

  onModelSelected(model: ModelCardDescriptor): Promise<void> {
    return this.applyAgentModelSelection(model);
  }

  isAgentModelSelected(model: ModelCardDescriptor): boolean {
    return isSelectedAgentModel(this.settings, model);
  }

  agentModelDisabledReason(model: ModelCardDescriptor): string | null {
    return this.requiresPull(model) ? null : agentSelectionDisabledReason(model);
  }

  onModelGridScroll(event: Event): void {
    this.state.modelGridScrollTop = (event.target as HTMLDivElement).scrollTop;
    this.syncState();
  }

  navigateBack(): void {
    this.syncState();
    void this.router.navigateByUrl('/');
  }

  cloudCredentialValue(provider: CloudCredentialProvider): string {
    return {
      openai: this.openaiKey,
      google: this.googleKey,
      deepseek: this.deepseekKey,
      opencode: this.opencodeKey,
      'opencode-go': this.opencodeGoKey,
    }[provider];
  }

  setCloudCredentialValue(provider: CloudCredentialProvider, value: string): void {
    if (provider === 'openai') this.openaiKey = value;
    if (provider === 'google') this.googleKey = value;
    if (provider === 'deepseek') this.deepseekKey = value;
    if (provider === 'opencode') this.opencodeKey = value;
    if (provider === 'opencode-go') this.opencodeGoKey = value;
    this.keyValidationErrors[provider] = undefined;
  }

  cloudCredentialValidationError(provider: CloudCredentialProvider): string | undefined {
    return this.keyValidationErrors[provider];
  }

  modelProviderHealth(provider: CloudCredentialProvider): string {
    if (!this.isCloudCredentialConfigured(provider)) {
      return 'Not configured';
    }
    return this.credentialHealth(provider) === 'unreadable'
      ? 'Saved key cannot be read'
      : 'Saved key is readable (not validated)';
  }

  credentialHealthForTemplate(provider: CloudCredentialProvider): string | null {
    return this.credentialHealth(provider);
  }

  async saveCloudProvider(provider: CloudCredentialProvider): Promise<void> {
    if (!this.settings || this.isSavingCredential) {
      return;
    }
    const value = this.cloudCredentialValue(provider).trim();
    if (!value) {
      this.keyValidationErrors[provider] = 'Enter a key before saving, or use Clear saved key.';
      this.statusText = `Enter a ${providerDisplayLabel(provider)} API key before saving.`;
      return;
    }
    const validation = this.validateCloudCredential(provider, value);
    if (validation) {
      this.keyValidationErrors[provider] = validation;
      this.statusText = validation;
      return;
    }
    this.isSavingCredential = true;
    try {
      const updated = await this.credentialSettingsService.saveProviderCredential(this.settings, provider, value);
      if (this.isDestroyed) return;
      this.settings = updated;
      this.setCloudCredentialValue(provider, '');
      this.structuredProbe = this.unverifiedProbe(updated);
      if (isDynamicCloudProvider(provider)) {
        await this.ensureProviderModelsLoaded(provider, true);
      }
      this.statusText = `${providerDisplayLabel(provider)} key saved. Provider access has not been validated.`;
      this.syncState();
    } catch (error: unknown) {
      this.statusText = this.userFacingErrorService.toUserFacingError(
        error,
        `Could not save the ${providerDisplayLabel(provider)} key right now.`,
      );
    } finally {
      this.isSavingCredential = false;
      this.changeDetectorRef.detectChanges();
    }
  }

  async clearCloudProvider(provider: CloudCredentialProvider): Promise<void> {
    if (!this.settings || this.isSavingCredential || !this.isCloudCredentialConfigured(provider)) {
      return;
    }
    this.isSavingCredential = true;
    try {
      const updated = await this.credentialSettingsService.saveProviderCredential(this.settings, provider, '');
      if (this.isDestroyed) return;
      this.settings = updated;
      this.setCloudCredentialValue(provider, '');
      this.structuredProbe = this.unverifiedProbe(updated);
      if (isDynamicCloudProvider(provider)) {
        this.cloudModels = this.cloudModels.filter((model) => model.provider !== provider);
        this.setDynamicProviderStatus(provider, { ok: false, message: `Add a ${providerDisplayLabel(provider)} API key to load ${providerDisplayLabel(provider)} models.` });
      }
      this.statusText = `${providerDisplayLabel(provider)} key cleared.`;
      this.syncState();
    } catch (error: unknown) {
      this.statusText = this.userFacingErrorService.toUserFacingError(
        error,
        `Could not clear the ${providerDisplayLabel(provider)} key right now.`,
      );
    } finally {
      this.isSavingCredential = false;
      this.changeDetectorRef.detectChanges();
    }
  }

  geoProviders: GeoProviderAccess[] = [];
  providerAccountSetups: GeospatialProviderAccountSetup[] = [];
  isLoadingAccountSetups = false;
  isSavingGeospatialCredential = false;
  selectedProviderAccountSetup?: GeospatialProviderAccountSetup;
  isSignupModalOpen = false;
  signupModalError = '';
  signupKeyInput = '';

  requiresPull(model: ModelCardDescriptor): boolean {
    return model.provider === 'ollama' && !this.isInstalledOllamaModel(model);
  }

  modelDescription(model: ModelCardDescriptor): string {
    return modelDisplayDescription(model);
  }

  isCloudCredentialConfigured(provider: CloudCredentialProvider): boolean {
    return Boolean(this.settings.credentials[provider]?.['api_key']);
  }

  private credentialHealth(provider: CloudCredentialProvider): string | null {
    const configured = Boolean(this.settings.credentials[provider]?.['api_key']);
    if (!configured) {
      return null;
    }
    return this.settings.credential_health?.[provider]?.['api_key'] ?? 'unknown';
  }

  private validateCloudCredential(provider: CloudCredentialProvider, value: string): string | undefined {
    if (provider === 'google' && !/^AIza[A-Za-z0-9_-]{20,}$/.test(value)) {
      return 'Google key must start with "AIza" and include a valid key body.';
    }
    if ((provider === 'openai' || provider === 'deepseek') && !/^sk-[A-Za-z0-9][A-Za-z0-9_-]{10,}$/.test(value)) {
      return `${providerDisplayLabel(provider)} key must start with "sk-" and include a valid key body.`;
    }
    return undefined;
  }

  private unverifiedProbe(settings: ModelSettingsResponse): StructuredProbeResponse {
    return {
      ...this.structuredProbe,
      provider: settings.agent_model_provider,
      model: settings.agent_model_name,
      status: 'not_tested',
      parse_status: 'not_tested',
      duration_ms: null,
      checked_at: null,
      expires_at: null,
      message: 'This model has not been verified against the native route/tool contract.',
    };
  }

  private dynamicProviderForSettings(settings: ModelSettingsResponse): DynamicCloudProvider | null {
    if (isDynamicCloudProvider(this.providerFilter)) {
      return this.providerFilter;
    }
    return isDynamicCloudProvider(settings.agent_model_provider)
      ? settings.agent_model_provider
      : null;
  }

  private async loadProviderAccountSetups(): Promise<void> {
    this.isLoadingAccountSetups = true;
    try {
      const response = await this.apiClient.fetchGeospatialProviderAccountSetups();
      if (this.isDestroyed) return;
      this.providerAccountSetups = response.providers;
      this.geoProviders = response.providers.map((setup) => this.geoProviderFromSetup(setup));
      response.providers.forEach((setup) => {
        this.geoCredentialDrafts[setup.credentialStorageKey] = this.geoCredentialDrafts[setup.credentialStorageKey] ?? '';
      });
    } catch {
      if (!this.isDestroyed) {
        this.statusText = 'Could not load geospatial provider setup metadata.';
      }
    } finally {
      this.isLoadingAccountSetups = false;
      if (!this.isDestroyed) {
        this.changeDetectorRef.detectChanges();
      }
    }
  }

  private async persistGeospatialCredential(provider: string, apiKey: string): Promise<boolean> {
    if (!this.settings) {
      return false;
    }
    const setup = this.geoProviderSetup(provider);
    this.isSavingGeospatialCredential = true;
    try {
      this.settings = await this.credentialSettingsService.saveProviderCredential(this.settings, provider, apiKey);
      this.geoCredentialDrafts[provider] = '';
      this.structuredProbe = this.unverifiedProbe(this.settings);
      this.statusText = apiKey
        ? `${setup?.name ?? provider} key saved. Provider access has not been validated.`
        : `${setup?.name ?? provider} key cleared. Optional capabilities are disabled.`;
      this.syncState();
      return true;
    } catch (error: unknown) {
      this.statusText = this.userFacingErrorService.toUserFacingError(
        error,
        `Could not update ${setup?.name ?? provider} access.`,
      );
      return false;
    } finally {
      this.isSavingGeospatialCredential = false;
      this.changeDetectorRef.detectChanges();
    }
  }

  private geoProviderFromSetup(setup: GeospatialProviderAccountSetup): GeoProviderAccess {
    return {
      id: setup.credentialStorageKey,
      name: setup.name,
      purpose: `${this.supportLabel(setup)} for credential-gated geospatial capabilities.`,
      placeholder: setup.keyFormatHint ?? `${setup.name} API key`,
      docsUrl: setup.automation.docsUrl || setup.docsUrl || setup.automation.developerPortalUrl || '',
      requiresCredentials: setup.requiresCredentials,
      instructions: setup.instructions,
    };
  }

  private async loadData(): Promise<void> {
    this.isLoadingModels = true;
    this.statusText = 'Loading model settings';
    this.syncState();
    try {
      const [nextSettings, baseLibrary] = await Promise.all([
        this.apiClient.fetchChatSettings(),
        this.apiClient.fetchChatModels(),
      ]);
      let nextProbe: StructuredProbeResponse;
      try {
        nextProbe = await this.apiClient.fetchStructuredProbe();
      } catch {
        // Probe health must not make an otherwise selectable model library
        // unavailable. Treat an unavailable health endpoint as unprobed.
        nextProbe = this.unverifiedProbe(nextSettings);
      }
      const dynamicProvider = this.dynamicProviderForSettings(nextSettings);
      let modelLibrary = baseLibrary;
      if (dynamicProvider) {
        const dynamicLibrary = await this.apiClient.fetchChatModels(dynamicProvider);
        modelLibrary = mergeModelLibraries(baseLibrary, dynamicLibrary, dynamicProvider);
      }
      if (this.isDestroyed) {
        return;
      }
      this.settings = nextSettings;
      this.structuredProbe = nextProbe;
      this.ollamaUrlDraft = nextSettings.ollama_url;
      this.applyModelLibrary(modelLibrary);
      const dynamicProviderFailed = dynamicProvider && modelLibrary.sources[dynamicProvider]?.ok === false;
      if (dynamicProviderFailed) {
        this.statusText = modelLibrary.sources[dynamicProvider]?.message || `Could not load ${providerDisplayLabel(dynamicProvider)} models right now.`;
      }
      if (this.statusText === 'Loading model settings' && !dynamicProviderFailed) {
        this.statusText = 'Model settings loaded';
      }
      this.syncQueryState();
      this.syncState();
    } catch (error: unknown) {
      if (this.isDestroyed) {
        return;
      }
      this.statusText = this.userFacingErrorService.toUserFacingError(error, 'Could not load model settings right now.');
      this.syncState();
    } finally {
      if (this.isDestroyed) {
        return;
      }
      this.isLoadingModels = false;
      // Publish the async catalog completion in the Eager change-detection view.
      this.changeDetectorRef.detectChanges();
    }
  }

  private async loadRuntimeSettings(): Promise<void> {
    this.isLoadingRuntimeSettings = true;
    this.runtimeSettingsError = '';
    try {
      const loaded = await this.apiClient.fetchRuntimeSettings();
      if (this.isDestroyed) {
        return;
      }
      this.runtimeSettings = loaded;
      this.runtimeSettingsDraft = cloneRuntimeSettings(loaded);
      this.runtimeRestartRequired = loaded.restart_required;
    } catch (error: unknown) {
      if (this.isDestroyed) {
        return;
      }
      this.runtimeSettingsError = this.userFacingErrorService.toUserFacingError(
        error,
        'Could not load runtime settings right now.',
      );
    } finally {
      if (this.isDestroyed) {
        return;
      }
      this.isLoadingRuntimeSettings = false;
      this.changeDetectorRef.detectChanges();
    }
  }

  async saveRuntimeSettings(): Promise<void> {
    if (this.isSavingRuntimeSettings || this.isLoadingRuntimeSettings) {
      return;
    }
    this.isSavingRuntimeSettings = true;
    this.runtimeSettingsError = '';
    try {
      const saved = await this.apiClient.updateRuntimeSettings(this.runtimeSettingsPatch());
      if (this.isDestroyed) {
        return;
      }
      this.runtimeSettings = saved;
      this.runtimeSettingsDraft = cloneRuntimeSettings(saved);
      this.runtimeRestartRequired = saved.restart_required;
      this.statusText = saved.message ?? 'Runtime settings saved.';
    } catch (error: unknown) {
      if (this.isDestroyed) {
        return;
      }
      this.runtimeSettingsError = this.userFacingErrorService.toUserFacingError(
        error,
        'Could not save runtime settings.',
      );
      this.statusText = this.runtimeSettingsError;
    } finally {
      if (this.isDestroyed) {
        return;
      }
      this.isSavingRuntimeSettings = false;
      this.changeDetectorRef.detectChanges();
    }
  }

  private runtimeSettingsPatch(): RuntimeSettingsUpdateRequest {
    const {
      schema_version: _schemaVersion,
      restart_required: _restartRequired,
      message: _message,
      ...blocks
    } = this.runtimeSettingsDraft;
    return blocks;
  }

  private async ensureProviderModelsLoaded(
    provider: ModelProviderFilter,
    forceRefresh = false,
  ): Promise<void> {
    if (!isDynamicCloudProvider(provider)) {
      return;
    }
    const configured = Boolean(this.settings.credentials[provider]?.['api_key']);
    const label = providerDisplayLabel(provider);
    if (!configured) {
      this.statusText = `Add a ${label} API key to load ${label} models.`;
      this.setDynamicProviderStatus(provider, { ok: false, message: this.statusText });
      this.syncState();
      return;
    }
    if (!forceRefresh && this.cloudModels.some((model) => model.provider === provider)) {
      return;
    }
    this.isLoadingDynamicProviderModels = true;
    this.statusText = `Loading ${label} models`;
    this.syncState();
    try {
      const modelLibrary = await this.apiClient.fetchChatModels(provider);
      if (this.isDestroyed) {
        return;
      }
      this.applyModelLibrary(mergeModelLibraries({
        cloud: this.cloudModels,
        local: this.localModels,
        sources: {
          ...(this.ollamaStatus ? { ollama: this.ollamaStatus } : {}),
          ...(this.deepseekStatus ? { deepseek: this.deepseekStatus } : {}),
          ...(this.opencodeStatus ? { opencode: this.opencodeStatus } : {}),
          ...(this.opencodeGoStatus ? { 'opencode-go': this.opencodeGoStatus } : {}),
        },
      }, modelLibrary, provider));
      this.statusText = modelLibrary.sources[provider]?.ok === false
        ? (modelLibrary.sources[provider].message || `Could not load ${label} models right now.`)
        : `${label} models loaded`;
      this.syncState();
    } catch (error: unknown) {
      if (this.isDestroyed) {
        return;
      }
      this.statusText = this.userFacingErrorService.toUserFacingError(
        error,
        `Could not load ${label} models right now.`,
      );
      this.syncState();
    } finally {
      if (this.isDestroyed) {
        return;
      }
      this.isLoadingDynamicProviderModels = false;
      this.syncState();
      this.changeDetectorRef.detectChanges();
    }
  }

  private isInstalledOllamaModel(model: ModelCardDescriptor): boolean {
    return model.provider === 'ollama' && this.localModelIds.has(model.id);
  }

  private applyModelLibrary(modelLibrary: ModelLibraryResponse): void {
    this.cloudModels = modelLibrary.cloud;
    this.localModels = modelLibrary.local.map((model) => enrichInstalledOllamaModel(model, modelLibrary.cloud));
    this.ollamaStatus = modelLibrary.sources.ollama ?? null;
    this.deepseekStatus = modelLibrary.sources.deepseek ?? null;
    this.opencodeStatus = modelLibrary.sources.opencode ?? null;
    this.opencodeGoStatus = modelLibrary.sources['opencode-go'] ?? null;
  }

  private async reloadOllamaCatalog(): Promise<void> {
    const library = await this.apiClient.fetchChatModels();
    if (this.isDestroyed) {
      return;
    }
    // The unscoped catalog request refreshes only the base/Ollama data. Keep
    // already-loaded dynamic cloud catalogs in memory so an Ollama URL or
    // pull operation cannot invalidate unrelated provider state.
    const dynamicCloudModels = this.cloudModels.filter((model) => isDynamicCloudProvider(model.provider));
    const sources = { ...library.sources };
    if (this.deepseekStatus) sources.deepseek = this.deepseekStatus;
    if (this.opencodeStatus) sources.opencode = this.opencodeStatus;
    if (this.opencodeGoStatus) sources['opencode-go'] = this.opencodeGoStatus;
    this.applyModelLibrary({
      cloud: mergeModelCards(library.cloud, dynamicCloudModels),
      local: library.local,
      sources,
    });
  }

  private setDynamicProviderStatus(
    provider: DynamicCloudProvider,
    status: ModelLibrarySourceStatus,
  ): void {
    if (provider === 'deepseek') this.deepseekStatus = status;
    if (provider === 'opencode') this.opencodeStatus = status;
    if (provider === 'opencode-go') this.opencodeGoStatus = status;
  }

  private syncQueryState(): void {
    if (typeof window === 'undefined') {
      return;
    }
    const currentPath = window.location.pathname;
    if (currentPath !== '/settings') {
      return;
    }

    const params = new URLSearchParams();
    if (this.searchText.trim()) {
      params.set('q', this.searchText);
    } else {
      params.delete('q');
    }
    if (this.activeSection !== 'models') {
      params.set('tab', this.activeSection);
    } else {
      params.delete('tab');
    }

    const queryParams: Record<string, string> = {};
    params.forEach((value, key) => {
      queryParams[key] = value;
    });
    const query = new URLSearchParams(queryParams).toString();
    const nextUrl = query ? `/settings?${query}` : '/settings';
    window.history.replaceState(window.history.state, '', nextUrl);
  }

  private applyUrlState(url: string): void {
    if (typeof window === 'undefined') {
      return;
    }
    const queryStart = url.indexOf('?');
    const query = queryStart >= 0 ? url.slice(queryStart + 1) : '';
    const params = new URLSearchParams(query);
    this.activeSection = normalizeSettingsSection(params.get('tab'));
    this.searchText = params.get('q') ?? '';
    this.syncState();
  }

  private async saveModelSettings(payload: ModelSettingsUpdateRequest): Promise<ModelSettingsResponse> {
    return this.apiClient.updateChatSettings(payload);
  }

  private settingsUpdateBase(): ModelSettingsUpdateRequest {
    return buildSettingsUpdateBase(this.settings);
  }

  private resetModelGridScroll(): void {
    this.state.modelGridScrollTop = 0;
    this.modelGridRef?.nativeElement.scrollTo({ top: 0 });
  }

  private syncState(): void {
    const next: PersistedSettingsPageState = {
      searchText: this.searchText,
      scrollY: this.viewStateSync.captureWindowScroll(),
      modelGridScrollTop: this.viewStateSync.captureElementScroll(
        this.modelGridRef?.nativeElement,
        this.state.modelGridScrollTop,
      ),
    };
    this.appStateStore.updateSettingsPage(next);
  }

  private getOllamaFailureMessage(error: unknown): string {
    return this.userFacingErrorService.toUserFacingError(
      error,
      `Unable to reach Ollama at ${this.settings.ollama_url || this.ollamaUrlDraft}. Check that the service is running and the URL is correct.`,
    );
  }

  private formatOllamaHealthSummary(health: OllamaHealthResponse): string {
    if (health.ok === true) {
      return 'Connection is healthy.';
    }

    const detail = health.detail ?? 'an unknown status';
    if (this.userFacingErrorService.isLowLevelConnectionError(detail)) {
      return `Unable to reach Ollama at ${this.settings.ollama_url || this.ollamaUrlDraft}. Check that the service is running and the URL is correct.`;
    }
    return `Connection check returned ${detail}.`;
  }
}

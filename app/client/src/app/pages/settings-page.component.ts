import { CommonModule } from '@angular/common';
import { AfterViewInit, ChangeDetectorRef, Component, ElementRef, OnDestroy, OnInit, ViewChild } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { Router } from '@angular/router';

import { ModelCardComponent } from '../components/model-card.component';
import { SelectedModelSummaryComponent } from '../components/selected-model-summary.component';
import { SettingsApiKeyFieldComponent } from '../components/settings-api-key-field.component';
import { SettingsIconActionComponent } from '../components/settings-icon-action.component';
import { SettingsModalShellComponent } from '../components/settings-modal-shell.component';
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
  enrichInstalledOllamaModel,
  isSelectedAgentModel,
  mergeModelCards,
  modelDisplayDescription,
  providerDisplayLabel,
  SelectedAgentModelSummary,
} from '../core/model-selection';
import {
  ModelCardDescriptor,
  ModelLibraryResponse,
  ModelLibrarySourceStatus,
  ModelProviderMode,
  ModelSettingsResponse,
  ModelSettingsUpdateRequest,
} from '../core/types';
import { UserFacingErrorService } from '../core/user-facing-error.service';
import { ViewStateSyncService } from '../core/view-state-sync.service';

@Component({
  selector: 'app-settings-page',
  standalone: true,
  imports: [
    CommonModule,
    FormsModule,
    ModelCardComponent,
    SettingsApiKeyFieldComponent,
    SettingsIconActionComponent,
    SettingsModalShellComponent,
    SelectedModelSummaryComponent,
  ],
  templateUrl: './settings-page.component.html',
  styleUrl: './settings-page.component.css',
})
export class SettingsPageComponent implements OnInit, AfterViewInit, OnDestroy {
  @ViewChild('modelGridScroll', { static: false }) modelGridRef?: ElementRef<HTMLDivElement>;

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
  };

  cloudModels: ModelCardDescriptor[] = [];
  localModels: ModelCardDescriptor[] = [];

  providerMode: ModelProviderMode;
  searchText: string;
  statusText: string;
  isLoadingModels = false;
  isRefreshingOllama = false;
  isLoadingDeepSeekModels = false;

  isKeysModalOpen = false;
  isOllamaModalOpen = false;
  openaiKey = '';
  googleKey = '';
  deepseekKey = '';
  ollamaUrlDraft = 'http://127.0.0.1:11434';
  keysModalStatusText = '';
  ollamaModalStatusText = '';
  keyValidationErrors: ApiKeyValidationErrors = {};
  ollamaStatus: ModelLibrarySourceStatus | null = null;
  deepseekStatus: ModelLibrarySourceStatus | null = null;

  providerFilter: ModelProviderFilter = 'all';
  private isDestroyed = false;

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
    const queryMode = query.get('mode');
    this.providerMode = queryMode === 'cloud' || queryMode === 'local' ? queryMode : this.state.providerMode;
    this.statusText = this.state.statusText;
  }

  ngOnInit(): void {
    void this.loadData();
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

    const query = this.searchText.trim().toLowerCase();
    return source.filter((model) => {
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
      mergeModelCards(this.localModels, this.cloudModels),
    );
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

  get visibleOllamaModalStatusText(): string {
    return this.userFacingErrorService.normalizeDisplayText(
      this.ollamaModalStatusText,
      `Unable to reach Ollama at ${this.settings.ollama_url || this.ollamaUrlDraft}. Check that the service is running and the URL is correct.`,
    );
  }

  get deepSeekLoadFailed(): boolean {
    return this.providerFilter === 'deepseek' && this.deepseekStatus !== null && !this.deepseekStatus.ok;
  }

  get deepSeekFailureMessage(): string {
    if (!this.deepSeekLoadFailed) {
      return '';
    }
    return this.deepseekStatus?.message || 'Could not load DeepSeek models right now.';
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
    const previousProviderMode = this.providerMode;
    const nextProviderMode: ModelProviderMode = model.provider === 'ollama' ? 'local' : 'cloud';
    try {
      this.settings = {
        ...this.settings,
        active_provider_mode: nextProviderMode,
        agent_model_provider: model.provider,
        agent_model_name: model.name,
      };
      this.providerMode = nextProviderMode;
      this.statusText = `Selecting ${model.name} as agent model...`;
      this.syncQueryState();
      this.syncState();
      this.changeDetectorRef.detectChanges();
      const updated = await this.saveModelSettings(payload);
      if (this.isDestroyed) {
        return;
      }
      this.settings = updated;
      this.providerMode = updated.active_provider_mode;
      this.statusText = `Selected ${model.name} as agent model`;
      this.syncQueryState();
      this.syncState();
    } catch (error: unknown) {
      if (this.isDestroyed) {
        return;
      }
      this.settings = previousSettings;
      this.providerMode = previousProviderMode;
      this.statusText = this.userFacingErrorService.toUserFacingError(error, `Could not select ${model.name} as agent model.`);
      this.syncQueryState();
      this.syncState();
      this.changeDetectorRef.detectChanges();
    }
  }

  async saveKeys(): Promise<void> {
    this.keyValidationErrors = this.validateKeyInputs();
    if (this.keyValidationErrors.openai || this.keyValidationErrors.google || this.keyValidationErrors.deepseek) {
      this.keysModalStatusText = 'Fix the highlighted API key fields before saving.';
      return;
    }

    try {
      const updated = await this.credentialSettingsService.saveCloudCredentials(this.settings, {
        openai: this.openaiKey,
        google: this.googleKey,
        deepseek: this.deepseekKey,
      });
      this.settings = updated;
      this.openaiKey = '';
      this.googleKey = '';
      this.deepseekKey = '';
      await this.ensureProviderModelsLoaded(
        this.providerFilter === 'deepseek' || this.hasSelectedProvider(updated, 'deepseek')
          ? 'deepseek'
          : 'all',
        true,
      );
      this.statusText = 'API keys saved';
      this.keysModalStatusText = 'API keys saved';
      this.isKeysModalOpen = false;
      this.syncState();
    } catch (error: unknown) {
      const detail = this.userFacingErrorService.toUserFacingError(error, 'Could not save API keys right now.');
      this.statusText = detail;
      this.keysModalStatusText = detail;
    }
  }

  async checkOllamaConnection(): Promise<void> {
    try {
      const health = await this.apiClient.checkOllamaHealth();
      const summary = this.formatOllamaHealthSummary(health);
      this.ollamaModalStatusText = summary;
      this.statusText = `Ollama: ${summary}`;
      this.syncState();
    } catch (error: unknown) {
      const detail = this.getOllamaFailureMessage(error);
      this.statusText = detail;
      this.ollamaModalStatusText = detail;
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
      await this.loadData();
      this.statusText = 'Ollama library refreshed';
      this.ollamaModalStatusText = 'Model library refreshed.';
      this.syncState();
    } catch (error: unknown) {
      const detail = this.getOllamaFailureMessage(error);
      this.statusText = detail;
      this.ollamaModalStatusText = detail;
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
      this.ollamaUrlDraft = updated.ollama_url;
      this.statusText = 'Ollama settings saved';
      this.ollamaModalStatusText = 'Ollama settings saved.';
      this.isOllamaModalOpen = false;
      this.syncState();
    } catch (error: unknown) {
      const detail = this.getOllamaFailureMessage(error);
      this.statusText = detail;
      this.ollamaModalStatusText = detail;
    }
  }

  async pullLocalModel(model: ModelCardDescriptor): Promise<boolean> {
    try {
      await this.apiClient.pullOllamaModel(model.name);
      await this.apiClient.refreshOllamaModels();
      await this.loadData();
      this.statusText = `Pulled ${model.name}`;
      this.syncState();
      return true;
    } catch (error: unknown) {
      this.statusText = this.userFacingErrorService.toUserFacingError(error, `Could not pull ${model.name}.`);
      return false;
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

  closeModal(): void {
    this.isKeysModalOpen = false;
    this.isOllamaModalOpen = false;
    this.keysModalStatusText = '';
    this.ollamaModalStatusText = '';
    this.keyValidationErrors = {};
  }

  onModelGridScroll(event: Event): void {
    this.state.modelGridScrollTop = (event.target as HTMLDivElement).scrollTop;
    this.syncState();
  }

  navigateBack(): void {
    this.syncState();
    void this.router.navigateByUrl('/');
  }

  openAiConfigured(): boolean {
    return Boolean(this.settings.credentials['openai']?.['api_key']);
  }

  googleConfigured(): boolean {
    return Boolean(this.settings.credentials['google']?.['api_key']);
  }

  deepSeekConfigured(): boolean {
    return Boolean(this.settings.credentials['deepseek']?.['api_key']);
  }

  openAiCredentialHealth(): string | null {
    return this.credentialHealth('openai');
  }

  googleCredentialHealth(): string | null {
    return this.credentialHealth('google');
  }

  deepSeekCredentialHealth(): string | null {
    return this.credentialHealth('deepseek');
  }

  requiresPull(model: ModelCardDescriptor): boolean {
    return model.provider === 'ollama' && !this.isInstalledOllamaModel(model);
  }

  modelDescription(model: ModelCardDescriptor): string {
    return modelDisplayDescription(model);
  }

  private credentialHealth(provider: CloudCredentialProvider): string | null {
    const configured = Boolean(this.settings.credentials[provider]?.['api_key']);
    if (!configured) {
      return null;
    }
    return this.settings.credential_health?.[provider]?.['api_key'] ?? 'unknown';
  }

  private validateKeyInputs(): ApiKeyValidationErrors {
    const errors: ApiKeyValidationErrors = {};
    const openAiValue = this.openaiKey.trim();
    const googleValue = this.googleKey.trim();
    const deepSeekValue = this.deepseekKey.trim();
    const openAiPattern = /^sk-[A-Za-z0-9][A-Za-z0-9_-]{10,}$/;
    const googlePattern = /^AIza[A-Za-z0-9_-]{20,}$/;
    const deepSeekPattern = /^sk-[A-Za-z0-9][A-Za-z0-9_-]{10,}$/;

    if (openAiValue && !openAiPattern.test(openAiValue)) {
      errors.openai = 'OpenAI key must start with "sk-" and include a valid key body.';
    }

    if (googleValue && !googlePattern.test(googleValue)) {
      errors.google = 'Google key must start with "AIza" and include a valid key body.';
    }

    if (deepSeekValue && !deepSeekPattern.test(deepSeekValue)) {
      errors.deepseek = 'DeepSeek key must start with "sk-" and include a valid key body.';
    }

    return errors;
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
      const needsDeepSeekLibrary = this.shouldLoadDeepSeekModels(nextSettings);
      let modelLibrary = baseLibrary;
      if (needsDeepSeekLibrary) {
        const deepseekLibrary = await this.apiClient.fetchChatModels('deepseek');
        modelLibrary = this.mergeModelLibraries(baseLibrary, deepseekLibrary);
      }
      if (this.isDestroyed) {
        return;
      }
      this.settings = nextSettings;
      this.providerMode = nextSettings.active_provider_mode;
      this.ollamaUrlDraft = nextSettings.ollama_url;
      this.applyModelLibrary(modelLibrary);
      const deepSeekRequestedButFailed = needsDeepSeekLibrary && modelLibrary.sources.deepseek?.ok === false;
      if (deepSeekRequestedButFailed) {
        this.statusText = modelLibrary.sources.deepseek?.message || 'Could not load DeepSeek models right now.';
      }
      if (this.statusText === 'Loading model settings' && !deepSeekRequestedButFailed) {
        this.statusText = 'Ready';
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
      this.changeDetectorRef.detectChanges();
    }
  }

  private shouldLoadDeepSeekModels(settings: ModelSettingsResponse): boolean {
    return this.providerFilter === 'deepseek'
      || this.hasSelectedProvider(settings, 'deepseek');
  }

  private hasSelectedProvider(settings: ModelSettingsResponse, provider: string): boolean {
    return settings.agent_model_provider === provider;
  }

  private async ensureProviderModelsLoaded(
    provider: ModelProviderFilter,
    forceRefresh = false,
  ): Promise<void> {
    if (provider !== 'deepseek') {
      return;
    }
    if (!this.deepSeekConfigured()) {
      this.statusText = 'Add a DeepSeek API key to load DeepSeek models.';
      this.deepseekStatus = { ok: false, message: 'Add a DeepSeek API key to load DeepSeek models.' };
      this.syncState();
      return;
    }
    if (!forceRefresh && this.cloudModels.some((model) => model.provider === 'deepseek')) {
      return;
    }
    this.isLoadingDeepSeekModels = true;
    this.statusText = 'Loading DeepSeek models';
    this.syncState();
    try {
      const modelLibrary = await this.apiClient.fetchChatModels('deepseek');
      if (this.isDestroyed) {
        return;
      }
      this.applyModelLibrary(this.mergeModelLibraries({
        cloud: this.cloudModels,
        local: this.localModels,
        sources: {
          ...(this.ollamaStatus ? { ollama: this.ollamaStatus } : {}),
          ...(this.deepseekStatus ? { deepseek: this.deepseekStatus } : {}),
        },
      }, modelLibrary));
      this.statusText = modelLibrary.sources.deepseek?.ok === false
        ? (modelLibrary.sources.deepseek.message || 'Could not load DeepSeek models right now.')
        : 'DeepSeek models loaded';
      this.syncState();
    } catch (error: unknown) {
      if (this.isDestroyed) {
        return;
      }
      this.statusText = this.userFacingErrorService.toUserFacingError(
        error,
        'Could not load DeepSeek models right now.',
      );
      this.syncState();
    } finally {
      if (this.isDestroyed) {
        return;
      }
      this.isLoadingDeepSeekModels = false;
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
    if (this.providerFilter === 'deepseek' && this.deepseekStatus && !this.deepseekStatus.ok) {
      this.statusText = this.deepseekStatus.message || 'Could not load DeepSeek models right now.';
    }
  }

  private mergeModelLibraries(
    baseLibrary: ModelLibraryResponse,
    deepseekLibrary: ModelLibraryResponse,
  ): ModelLibraryResponse {
    return {
      cloud: mergeModelCards(
        baseLibrary.cloud.filter((model) => model.provider !== 'deepseek'),
        deepseekLibrary.cloud,
      ),
      local: deepseekLibrary.local.length ? deepseekLibrary.local : baseLibrary.local,
      sources: {
        ...baseLibrary.sources,
        ...deepseekLibrary.sources,
      },
    };
  }

  private syncQueryState(): void {
    const currentPath = window.location.pathname;
    if (currentPath !== '/settings' && window.location.pathname !== '/settings') {
      return;
    }

    const params = new URLSearchParams();
    if (this.searchText.trim()) {
      params.set('q', this.searchText);
    } else {
      params.delete('q');
    }

    if (this.providerMode !== 'local') {
      params.set('mode', this.providerMode);
    } else {
      params.delete('mode');
    }

    const queryParams: Record<string, string> = {};
    params.forEach((value, key) => {
      queryParams[key] = value;
    });
    const query = new URLSearchParams(queryParams).toString();
    const nextUrl = query ? `/settings?${query}` : '/settings';
    window.history.replaceState(window.history.state, '', nextUrl);
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
      providerMode: this.providerMode,
      statusText: this.statusText,
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

  private formatOllamaHealthSummary(health: { ok?: unknown; detail?: unknown }): string {
    if (Boolean(health.ok)) {
      return 'Connection is healthy.';
    }

    const detail = typeof health.detail === 'string' ? health.detail : 'an unknown status';
    if (this.userFacingErrorService.isLowLevelConnectionError(detail)) {
      return `Unable to reach Ollama at ${this.settings.ollama_url || this.ollamaUrlDraft}. Check that the service is running and the URL is correct.`;
    }
    return `Connection check returned ${detail}.`;
  }
}

import { CommonModule } from '@angular/common';
import { AfterViewInit, Component, ElementRef, OnDestroy, OnInit, ViewChild } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { Router } from '@angular/router';

import { ModelRoleActionsComponent } from '../components/model-role-actions.component';
import { SettingsIconActionComponent } from '../components/settings-icon-action.component';
import { SettingsModalShellComponent } from '../components/settings-modal-shell.component';
import { ModelStatsPanelComponent } from '../components/model-stats-panel.component';
import { ApiClientService } from '../core/api-client.service';
import { AppStateStoreService } from '../core/app-state-store.service';
import { PersistedSettingsPageState } from '../core/app-state';
import {
  ModelRole,
  buildModelSelectionPayload,
  buildSelectedModelStats,
} from '../core/model-selection';
import {
  ModelCardDescriptor,
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
    ModelRoleActionsComponent,
    SettingsIconActionComponent,
    SettingsModalShellComponent,
    ModelStatsPanelComponent,
  ],
  templateUrl: './settings-page.component.html',
  styleUrl: './settings-page.component.css',
})
export class SettingsPageComponent implements OnInit, AfterViewInit, OnDestroy {
  @ViewChild('modelGridScroll', { static: false }) modelGridRef?: ElementRef<HTMLDivElement>;

  readonly state: PersistedSettingsPageState;
  settings: ModelSettingsResponse = {
    active_provider_mode: 'local',
    chat_model_provider: 'ollama',
    chat_model_name: '',
    parser_model_provider: 'ollama',
    parser_model_name: '',
    agent_model_provider: 'ollama',
    agent_model_name: '',
    ollama_url: 'http://localhost:11434',
    openai_base_url: null,
    google_base_url: null,
    credentials: {},
    credential_health: {},
  };

  cloudModels: ModelCardDescriptor[] = [];
  localModels: ModelCardDescriptor[] = [];

  providerMode: ModelProviderMode;
  searchText: string;
  statusText: string;
  isLoadingModels = false;

  isKeysModalOpen = false;
  isOllamaModalOpen = false;
  openaiKey = '';
  googleKey = '';
  ollamaUrlDraft = 'http://localhost:11434';
  keysModalStatusText = '';
  ollamaModalStatusText = '';
  keyValidationErrors: { openai?: string; google?: string } = {};

  providerFilter: 'all' | 'ollama' | 'openai' | 'google' = 'all';
  private isDestroyed = false;

  constructor(
    private readonly apiClient: ApiClientService,
    private readonly appStateStore: AppStateStoreService,
    private readonly userFacingErrorService: UserFacingErrorService,
    private readonly viewStateSync: ViewStateSyncService,
    private readonly router: Router,
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
    this.viewStateSync.restoreElementScroll(this.modelGridRef?.nativeElement, this.state.modelGridScrollTop);
  }

  ngOnDestroy(): void {
    this.isDestroyed = true;
    this.syncState();
  }

  get displayedModels(): ModelCardDescriptor[] {
    const localModelIds = new Set(this.localModels.map((item) => item.id));

    const source = (() => {
      if (this.providerFilter === 'all') {
        return this.mergeModelLists(this.localModels, this.cloudModels);
      }
      if (this.providerFilter === 'ollama') {
        return this.mergeModelLists(
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
        ? (this.localModelIds.has(model.id) ? 'ollama-installed' : 'ollama-library')
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
    if (providerKey === 'ollama-installed') {
      return 'ollama · installed';
    }
    if (providerKey === 'ollama-library') {
      return 'ollama · available to pull';
    }
    return providerKey;
  }

  get hasDisplayedModels(): boolean {
    return this.displayedModels.length > 0;
  }

  get localModelIds(): Set<string> {
    return new Set(this.localModels.map((item) => item.id));
  }

  get selectedModelStats(): Array<{ model: string; provider: string; local: boolean; assignedRoles: string[] }> {
    return buildSelectedModelStats(this.settings, this.localModelIds);
  }

  get unavailableAssignedOllamaModels(): string[] {
    const assignedModels = [
      this.settings.parser_model_provider === 'ollama' ? this.settings.parser_model_name : '',
      this.settings.chat_model_provider === 'ollama' ? this.settings.chat_model_name : '',
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

  setSearchText(value: string): void {
    this.searchText = value;
    this.syncQueryState();
    this.syncState();
  }

  setProviderFilter(filter: 'all' | 'ollama' | 'openai' | 'google'): void {
    this.providerFilter = filter;
    this.syncState();
  }

  async applyModelSelection(role: ModelRole, model: ModelCardDescriptor): Promise<void> {
    if (model.provider === 'ollama' && !this.localModelIds.has(model.id)) {
      const pulled = await this.pullLocalModel(model);
      if (!pulled || !this.localModelIds.has(model.id)) {
        return;
      }
    }
    const payload = buildModelSelectionPayload(this.settings, role, model);
    try {
      const updated = await this.saveModelSettings(payload);
      if (this.isDestroyed) {
        return;
      }
      this.settings = updated;
      this.providerMode = updated.active_provider_mode;
      this.statusText = `Selected ${model.name} for ${this.roleLabel(role)}`;
      this.syncQueryState();
      this.syncState();
    } catch (error: unknown) {
      if (this.isDestroyed) {
        return;
      }
      this.statusText = this.userFacingErrorService.toUserFacingError(error, `Could not select ${model.name} for ${role}.`);
    }
  }

  async saveKeys(): Promise<void> {
    this.keyValidationErrors = this.validateKeyInputs();
    if (this.keyValidationErrors.openai || this.keyValidationErrors.google) {
      this.keysModalStatusText = 'Fix the highlighted API key fields before saving.';
      return;
    }

    try {
      const updated = await this.apiClient.updateChatSettings({
        ...this.settingsUpdateBase(),
        credentials: {
          openai: this.openaiKey.trim() ? { api_key: this.openaiKey.trim() } : {},
          google: this.googleKey.trim() ? { api_key: this.googleKey.trim() } : {},
        },
      });
      this.settings = updated;
      this.openaiKey = '';
      this.googleKey = '';
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
    }
  }

  async saveOllamaSettings(): Promise<void> {
    try {
      const updated = await this.apiClient.updateChatSettings({
        ...this.settingsUpdateBase(),
        ollama_url: this.ollamaUrlDraft.trim() || 'http://localhost:11434',
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

  openAiCredentialHealth(): string | null {
    return this.credentialHealth('openai');
  }

  googleCredentialHealth(): string | null {
    return this.credentialHealth('google');
  }

  requiresPull(model: ModelCardDescriptor): boolean {
    return model.provider === 'ollama' && !this.localModelIds.has(model.id);
  }

  private credentialHealth(provider: 'openai' | 'google'): string | null {
    const configured = Boolean(this.settings.credentials[provider]?.['api_key']);
    if (!configured) {
      return null;
    }
    return this.settings.credential_health?.[provider]?.['api_key'] ?? 'unknown';
  }

  private validateKeyInputs(): { openai?: string; google?: string } {
    const errors: { openai?: string; google?: string } = {};
    const openAiValue = this.openaiKey.trim();
    const googleValue = this.googleKey.trim();
    const openAiPattern = /^sk-[A-Za-z0-9][A-Za-z0-9_-]{10,}$/;
    const googlePattern = /^AIza[A-Za-z0-9_-]{20,}$/;

    if (openAiValue && !openAiPattern.test(openAiValue)) {
      errors.openai = 'OpenAI key must start with "sk-" and include a valid key body.';
    }

    if (googleValue && !googlePattern.test(googleValue)) {
      errors.google = 'Google key must start with "AIza" and include a valid key body.';
    }

    return errors;
  }

  private async loadData(): Promise<void> {
    this.isLoadingModels = true;
    this.statusText = 'Loading model settings';
    this.syncState();
    try {
      const [nextSettings, modelLibrary] = await Promise.all([
        this.apiClient.fetchChatSettings(),
        this.apiClient.fetchChatModels(),
      ]);
      if (this.isDestroyed) {
        return;
      }
      this.settings = nextSettings;
      this.providerMode = nextSettings.active_provider_mode;
      this.ollamaUrlDraft = nextSettings.ollama_url;
      this.cloudModels = modelLibrary.cloud;
      this.localModels = modelLibrary.local;
      this.statusText = 'Ready';
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
    }
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

  private mergeModelLists(...groups: ModelCardDescriptor[][]): ModelCardDescriptor[] {
    const models = new Map<string, ModelCardDescriptor>();
    groups.flat().forEach((model) => {
      models.set(`${model.provider}:${model.id}`, model);
    });
    return [...models.values()];
  }

  private settingsUpdateBase(): ModelSettingsUpdateRequest {
    return {
      active_provider_mode: this.settings.active_provider_mode,
      chat_model_provider: this.settings.chat_model_provider,
      chat_model_name: this.settings.chat_model_name,
      parser_model_provider: this.settings.parser_model_provider,
      parser_model_name: this.settings.parser_model_name,
      agent_model_provider: this.settings.agent_model_provider,
      agent_model_name: this.settings.agent_model_name,
      ollama_url: this.settings.ollama_url,
      openai_base_url: this.settings.openai_base_url,
      google_base_url: this.settings.google_base_url,
      credentials: {},
    };
  }

  private roleLabel(role: ModelRole): string {
    if (role === 'parser') {
      return 'parser';
    }
    if (role === 'chat') {
      return 'chat';
    }
    return 'agent';
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

import { CommonModule } from '@angular/common';
import { AfterViewInit, Component, ElementRef, OnDestroy, OnInit, ViewChild } from '@angular/core';
import { Router } from '@angular/router';
import { FormsModule } from '@angular/forms';

import { ModelRoleActionsComponent } from '../components/model-role-actions.component';
import { SettingsModalShellComponent } from '../components/settings-modal-shell.component';
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
import {
  checkOllamaHealth,
  fetchChatModels,
  fetchChatSettings,
  pullOllamaModel,
  refreshOllamaModels,
  updateChatSettings,
} from '../core/api';
import { UserFacingErrorService } from '../core/user-facing-error.service';

@Component({
  selector: 'app-settings-page',
  standalone: true,
  imports: [CommonModule, FormsModule, ModelRoleActionsComponent, SettingsModalShellComponent],
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
  showLocalOnly = false;
  private isDestroyed = false;

  constructor(
    private readonly router: Router,
    private readonly appStateStore: AppStateStoreService,
    private readonly userFacingErrorService: UserFacingErrorService,
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
    window.scrollTo({ top: this.state.scrollY, behavior: 'auto' });
    if (this.modelGridRef?.nativeElement) {
      this.modelGridRef.nativeElement.scrollTop = this.state.modelGridScrollTop;
    }
  }

  ngOnDestroy(): void {
    this.isDestroyed = true;
    this.syncState();
  }

  get displayedModels(): ModelCardDescriptor[] {
    const localModelIds = new Set(this.localModels.map((item) => item.id));

    const source = (() => {
      if (this.providerFilter === 'all') {
        return [...this.cloudModels];
      }
      if (this.providerFilter === 'ollama') {
        return [...this.cloudModels.filter((model) => model.provider === 'ollama')];
      }
      return this.cloudModels.filter((model) => model.provider === this.providerFilter);
    })();

    const query = this.searchText.trim().toLowerCase();
    return source.filter((model) => {
      if (this.providerFilter === 'ollama' && this.showLocalOnly && !localModelIds.has(model.id)) {
        return false;
      }
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
      const key = model.provider.toLowerCase();
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

  get hasDisplayedModels(): boolean {
    return this.displayedModels.length > 0;
  }

  get localModelIds(): Set<string> {
    return new Set(this.localModels.map((item) => item.id));
  }

  get selectedModelStats(): Array<{ model: string; provider: string; local: boolean; assignedRoles: string[] }> {
    return buildSelectedModelStats(this.settings, this.localModelIds);
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
    if (filter !== 'ollama') {
      this.showLocalOnly = false;
    }
    this.syncState();
  }

  setShowLocalOnly(checked: boolean): void {
    this.showLocalOnly = checked;
  }

  onLocalOnlyChange(event: Event): void {
    const target = event.target as HTMLInputElement | null;
    this.setShowLocalOnly(Boolean(target?.checked));
  }

  async applyModelSelection(role: ModelRole, model: ModelCardDescriptor): Promise<void> {
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
      const updated = await updateChatSettings({
        ...this.settings,
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
      const health = await checkOllamaHealth();
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
      await refreshOllamaModels();
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
      const updated = await updateChatSettings({
        ...this.settings,
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

  async pullLocalModel(model: ModelCardDescriptor): Promise<void> {
    try {
      await pullOllamaModel(model.name);
      await refreshOllamaModels();
      await this.loadData();
      this.statusText = `Pulled ${model.name}`;
      this.syncState();
    } catch (error: unknown) {
      this.statusText = this.userFacingErrorService.toUserFacingError(error, `Could not pull ${model.name}.`);
    }
  }

  navigateBack(): void {
    this.syncState();
    this.router.navigateByUrl('/');
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

  openAiConfigured(): boolean {
    return Boolean(this.settings.credentials['openai']?.['api_key']);
  }

  googleConfigured(): boolean {
    return Boolean(this.settings.credentials['google']?.['api_key']);
  }

  private validateKeyInputs(): { openai?: string; google?: string } {
    const errors: { openai?: string; google?: string } = {};
    const openAiValue = this.openaiKey.trim();
    const googleValue = this.googleKey.trim();

    if (openAiValue && !openAiValue.startsWith('sk-')) {
      errors.openai = 'OpenAI key must start with "sk-".';
    }

    if (googleValue && !googleValue.startsWith('AIza')) {
      errors.google = 'Google key must start with "AIza".';
    }

    return errors;
  }

  private async loadData(): Promise<void> {
    this.isLoadingModels = true;
    try {
      const [nextSettings, modelLibrary] = await Promise.all([
        fetchChatSettings(),
        fetchChatModels(),
      ]);
      if (this.isDestroyed) {
        return;
      }
      this.settings = nextSettings;
      this.providerMode = nextSettings.active_provider_mode;
      this.ollamaUrlDraft = nextSettings.ollama_url;
      this.cloudModels = modelLibrary.cloud;
      this.localModels = modelLibrary.local;
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
    const currentPath = this.router.url.split('?')[0];
    if (currentPath !== '/settings') {
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
    const nextUrl = this.router.serializeUrl(this.router.createUrlTree(['/settings'], { queryParams }));
    window.history.replaceState(window.history.state, '', nextUrl);
  }

  private async saveModelSettings(payload: ModelSettingsUpdateRequest): Promise<ModelSettingsResponse> {
    return updateChatSettings(payload);
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
      scrollY: window.scrollY,
      modelGridScrollTop: this.modelGridRef?.nativeElement.scrollTop ?? this.state.modelGridScrollTop,
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

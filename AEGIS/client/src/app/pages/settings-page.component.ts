import { CommonModule } from '@angular/common';
import { AfterViewInit, Component, ElementRef, OnDestroy, ViewChild } from '@angular/core';
import { Router } from '@angular/router';
import { FormsModule } from '@angular/forms';

import { AppStateStoreService } from '../core/app-state-store.service';
import { PersistedSettingsPageState } from '../core/app-state';
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

@Component({
  selector: 'app-settings-page',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './settings-page.component.html',
  styleUrl: './settings-page.component.css',
})
export class SettingsPageComponent implements AfterViewInit, OnDestroy {
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

  isKeysModalOpen = false;
  isOllamaModalOpen = false;
  openaiKey = '';
  googleKey = '';
  ollamaUrlDraft = 'http://localhost:11434';

  providerFilter: 'all' | 'ollama' | 'openai' | 'google' = 'all';
  showLocalOnly = false;

  constructor(
    private readonly router: Router,
    private readonly appStateStore: AppStateStoreService,
  ) {
    this.state = this.appStateStore.getSettingsPage();
    const query = new URLSearchParams(window.location.search);
    this.searchText = query.get('q') ?? this.state.searchText;
    const queryMode = query.get('mode');
    this.providerMode = queryMode === 'cloud' || queryMode === 'local' ? queryMode : this.state.providerMode;
    this.statusText = this.state.statusText;
  }

  ngAfterViewInit(): void {
    window.scrollTo({ top: this.state.scrollY, behavior: 'auto' });
    if (this.modelGridRef?.nativeElement) {
      this.modelGridRef.nativeElement.scrollTop = this.state.modelGridScrollTop;
    }
    this.loadData();
    this.syncState();
  }

  ngOnDestroy(): void {
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

  get localModelIds(): Set<string> {
    return new Set(this.localModels.map((item) => item.id));
  }

  get selectedModelStats(): Array<{ model: string; provider: string; local: boolean; assignedRoles: string[] }> {
    const localModelIds = this.localModelIds;
    const rows = new Map<string, { model: string; provider: string; local: boolean; assignedRoles: string[] }>();
    const assignments = [
      { role: 'Parser', provider: this.settings.parser_model_provider, name: this.settings.parser_model_name },
      { role: 'Chat', provider: this.settings.chat_model_provider, name: this.settings.chat_model_name },
      { role: 'Agent', provider: this.settings.agent_model_provider, name: this.settings.agent_model_name },
    ];

    assignments.forEach(({ role, provider, name }) => {
      const normalizedProvider = provider.trim();
      const normalizedName = name.trim();
      if (!normalizedProvider || !normalizedName) {
        return;
      }
      const key = `${normalizedProvider}:${normalizedName}`;
      const existing = rows.get(key);
      const local = localModelIds.has(normalizedName);
      if (existing) {
        existing.local = existing.local || local;
        if (!existing.assignedRoles.includes(role)) {
          existing.assignedRoles.push(role);
        }
        return;
      }
      rows.set(key, {
        model: normalizedName,
        provider: normalizedProvider,
        local,
        assignedRoles: [role],
      });
    });

    return Array.from(rows.values());
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
  }

  setShowLocalOnly(checked: boolean): void {
    this.showLocalOnly = checked;
  }

  async applyModelSelection(kind: 'parser' | 'agent' | 'chat', model: ModelCardDescriptor): Promise<void> {
    const nextProviderMode: ModelProviderMode = model.provider === 'ollama' ? 'local' : 'cloud';
    const payload: ModelSettingsUpdateRequest = {
      ...this.settings,
      active_provider_mode: nextProviderMode,
      chat_model_provider: kind === 'chat' ? model.provider : this.settings.chat_model_provider,
      chat_model_name: kind === 'chat' ? model.name : this.settings.chat_model_name,
      parser_model_provider: kind === 'parser' ? model.provider : this.settings.parser_model_provider,
      parser_model_name: kind === 'parser' ? model.name : this.settings.parser_model_name,
      agent_model_provider: kind === 'agent' ? model.provider : this.settings.agent_model_provider,
      agent_model_name: kind === 'agent' ? model.name : this.settings.agent_model_name,
    };

    try {
      const updated = await updateChatSettings(payload);
      this.settings = updated;
      this.providerMode = updated.active_provider_mode;
      this.statusText = `Selected ${model.name} for ${kind}`;
      this.syncQueryState();
      this.syncState();
    } catch (error: unknown) {
      this.statusText = this.toErrorText(error);
    }
  }

  async saveKeys(): Promise<void> {
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
      this.isKeysModalOpen = false;
      this.syncState();
    } catch (error: unknown) {
      this.statusText = this.toErrorText(error);
    }
  }

  async checkOllamaConnection(): Promise<void> {
    try {
      const health = await checkOllamaHealth();
      this.statusText = `Ollama: ${String(health.detail ?? health.ok ?? 'unknown')}`;
      this.syncState();
    } catch (error: unknown) {
      this.statusText = this.toErrorText(error);
    }
  }

  async refreshOllamaLibrary(): Promise<void> {
    try {
      await refreshOllamaModels();
      await this.loadData();
      this.statusText = 'Ollama library refreshed';
      this.syncState();
    } catch (error: unknown) {
      this.statusText = this.toErrorText(error);
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
      this.isOllamaModalOpen = false;
      this.syncState();
    } catch (error: unknown) {
      this.statusText = this.toErrorText(error);
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
      this.statusText = this.toErrorText(error);
    }
  }

  isSelectedForParser(model: ModelCardDescriptor): boolean {
    return model.provider === this.settings.parser_model_provider && model.name === this.settings.parser_model_name;
  }

  isSelectedForChat(model: ModelCardDescriptor): boolean {
    return model.provider === this.settings.chat_model_provider && model.name === this.settings.chat_model_name;
  }

  isSelectedForAgent(model: ModelCardDescriptor): boolean {
    return model.provider === this.settings.agent_model_provider && model.name === this.settings.agent_model_name;
  }

  navigateBack(): void {
    this.syncState();
    this.router.navigateByUrl('/');
  }

  closeModal(): void {
    this.isKeysModalOpen = false;
    this.isOllamaModalOpen = false;
  }

  onBackdropClick(event: MouseEvent): void {
    if ((event.target as HTMLElement).classList.contains('settings-modal-backdrop')) {
      this.closeModal();
    }
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

  private async loadData(): Promise<void> {
    try {
      const [nextSettings, modelLibrary] = await Promise.all([
        fetchChatSettings(),
        fetchChatModels(),
      ]);
      this.settings = nextSettings;
      this.providerMode = nextSettings.active_provider_mode;
      this.ollamaUrlDraft = nextSettings.ollama_url;
      this.cloudModels = modelLibrary.cloud;
      this.localModels = modelLibrary.local;
      this.syncQueryState();
      this.syncState();
    } catch (error: unknown) {
      this.statusText = `Load failed: ${this.toErrorText(error)}`;
      this.syncState();
    }
  }

  private syncQueryState(): void {
    const params = new URLSearchParams(window.location.search);
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

    const nextQuery = params.toString();
    const nextUrl = `${window.location.pathname}${nextQuery ? `?${nextQuery}` : ''}`;
    window.history.replaceState(window.history.state, '', nextUrl);
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

  private toErrorText(error: unknown): string {
    return error instanceof Error ? error.message : String(error);
  }
}

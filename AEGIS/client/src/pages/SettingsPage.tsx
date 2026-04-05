import { useEffect, useMemo, useRef, useState } from 'react';

import ConfigurationPanel from '../components/settings/ConfigurationPanel';
import ManifestToolsPanel from '../components/settings/ManifestToolsPanel';
import ModelGrid from '../components/settings/ModelGrid';
import ModelProviderToggle from '../components/settings/ModelProviderToggle';
import ModelSearchBar from '../components/settings/ModelSearchBar';
import {
    checkOllamaHealth,
    fetchChatModels,
    fetchChatSettings,
    pullOllamaModel,
    rebuildVectors,
    refreshOllamaModels,
    updateChatSettings,
} from '../services/api';
import { ModelCardDescriptor, ModelProviderMode, ModelSettingsResponse } from '../types';
import './SettingsPage.css';
import { PersistedSettingsPageState } from '../state/appState';

const defaultSettings: ModelSettingsResponse = {
    active_provider_mode: 'local',
    chat_model_provider: 'ollama',
    chat_model_name: '',
    agent_model_provider: 'ollama',
    agent_model_name: '',
    ollama_url: 'http://localhost:11434',
    openai_base_url: null,
    google_base_url: null,
    credentials: {},
};

interface SettingsPageProps {
    onBack: () => void;
    state: PersistedSettingsPageState;
    onStateChange: (state: PersistedSettingsPageState) => void;
    isActive: boolean;
}

const isProviderMode = (value: string | null): value is ModelProviderMode =>
    value === 'local' || value === 'cloud';

const readSettingsQueryState = (): Pick<PersistedSettingsPageState, 'searchText' | 'providerMode'> => {
    const params = new URLSearchParams(window.location.search);
    const searchText = params.get('q') ?? '';
    const providerMode = isProviderMode(params.get('mode')) ? (params.get('mode') as ModelProviderMode) : 'local';
    return { searchText, providerMode };
};

const writeSettingsQueryState = (searchText: string, providerMode: ModelProviderMode) => {
    const params = new URLSearchParams(window.location.search);
    if (searchText.trim()) {
        params.set('q', searchText);
    } else {
        params.delete('q');
    }
    if (providerMode !== 'local') {
        params.set('mode', providerMode);
    } else {
        params.delete('mode');
    }
    const nextQuery = params.toString();
    const nextUrl = `${window.location.pathname}${nextQuery ? `?${nextQuery}` : ''}`;
    window.history.replaceState(window.history.state, '', nextUrl);
};

function SettingsPage({ onBack, state, onStateChange, isActive }: SettingsPageProps) {
    const queryState = readSettingsQueryState();
    const [settings, setSettings] = useState<ModelSettingsResponse>(defaultSettings);
    const [cloudModels, setCloudModels] = useState<ModelCardDescriptor[]>([]);
    const [localModels, setLocalModels] = useState<ModelCardDescriptor[]>([]);
    const [searchText, setSearchText] = useState(queryState.searchText || state.searchText);
    const [providerMode, setProviderMode] = useState<ModelProviderMode>(queryState.providerMode || state.providerMode);
    const [statusText, setStatusText] = useState(state.statusText);
    const modelGridRef = useRef<HTMLDivElement | null>(null);

    const loadData = async () => {
        const [nextSettings, modelLibrary] = await Promise.all([
            fetchChatSettings(),
            fetchChatModels(),
        ]);
        setSettings(nextSettings);
        setProviderMode(nextSettings.active_provider_mode);
        setCloudModels(modelLibrary.cloud);
        setLocalModels(modelLibrary.local);
    };

    useEffect(() => {
        loadData().catch((error: unknown) => {
            setStatusText(`Load failed: ${String((error as { message?: string })?.message ?? error)}`);
        });
    }, []);

    useEffect(() => {
        if (!isActive) {
            return;
        }
        writeSettingsQueryState(searchText, providerMode);
    }, [searchText, providerMode, isActive]);

    useEffect(() => {
        onStateChange({
            searchText,
            providerMode,
            statusText,
            scrollY: isActive ? window.scrollY : state.scrollY,
            modelGridScrollTop: modelGridRef.current?.scrollTop ?? state.modelGridScrollTop,
        });
    }, [searchText, providerMode, statusText, isActive, state.scrollY, state.modelGridScrollTop, onStateChange]);

    useEffect(() => {
        if (!isActive) {
            return;
        }
        window.scrollTo({ top: state.scrollY, behavior: 'auto' });
        if (modelGridRef.current) {
            modelGridRef.current.scrollTop = state.modelGridScrollTop;
        }
    }, [isActive, state.scrollY, state.modelGridScrollTop]);

    const displayedModels = useMemo(() => {
        const source = providerMode === 'local' ? localModels : cloudModels;
        const query = searchText.trim().toLowerCase();
        return source.filter((model) => {
            if (!query) {
                return true;
            }
            return (
                model.name.toLowerCase().includes(query)
                || model.description.toLowerCase().includes(query)
                || model.provider.toLowerCase().includes(query)
            );
        });
    }, [providerMode, localModels, cloudModels, searchText]);

    const localModelIds = useMemo(() => new Set(localModels.map((item) => item.id)), [localModels]);

    const handleProviderModeChange = async (mode: ModelProviderMode) => {
        setProviderMode(mode);
        try {
            const updated = await updateChatSettings({
                ...settings,
                active_provider_mode: mode,
            });
            setSettings(updated);
            setStatusText(`Provider mode set to ${mode}`);
        } catch (error: unknown) {
            setStatusText(`Provider mode update failed: ${String((error as { message?: string })?.message ?? error)}`);
        }
    };

    const applyModelSelection = async (kind: 'chat' | 'agent', model: ModelCardDescriptor) => {
        const payload = {
            ...settings,
            active_provider_mode: model.provider === 'ollama' ? 'local' : 'cloud',
            chat_model_provider: kind === 'chat' ? model.provider : settings.chat_model_provider,
            chat_model_name: kind === 'chat' ? model.name : settings.chat_model_name,
            agent_model_provider: kind === 'agent' ? model.provider : settings.agent_model_provider,
            agent_model_name: kind === 'agent' ? model.name : settings.agent_model_name,
        };
        const updated = await updateChatSettings(payload);
        setSettings(updated);
        setProviderMode(updated.active_provider_mode);
        setStatusText(`Selected ${model.name} for ${kind}`);
    };

    return (
        <div className="settings-page" hidden={!isActive} aria-hidden={!isActive}>
            <header className="settings-page__header">
                <div className="settings-page__heading">
                    <h1>Model Settings</h1>
                    <p>Configure active providers and assign dedicated chat and agent models.</p>
                </div>
                <button type="button" className="settings-page__back" onClick={onBack}>Back to Chat</button>
            </header>

            <section className="settings-page__controls" aria-label="Settings controls">
                <ModelProviderToggle value={providerMode} onChange={handleProviderModeChange} />
                <ModelSearchBar value={searchText} onChange={setSearchText} />
            </section>

            <ModelGrid
                containerRef={modelGridRef}
                models={displayedModels}
                localModelIds={localModelIds}
                selectedChatModel={{
                    provider: settings.chat_model_provider,
                    name: settings.chat_model_name,
                }}
                selectedAgentModel={{
                    provider: settings.agent_model_provider,
                    name: settings.agent_model_name,
                }}
                onSelectChat={(model) => applyModelSelection('chat', model)}
                onSelectAgent={(model) => applyModelSelection('agent', model)}
                onPull={async (model) => {
                    await pullOllamaModel(model.name);
                    await refreshOllamaModels();
                    await loadData();
                    setStatusText(`Pulled ${model.name}`);
                }}
            />

            <ConfigurationPanel
                providerMode={providerMode}
                settings={settings}
                onSave={async (payload) => {
                    const updated = await updateChatSettings(payload);
                    setSettings(updated);
                    setStatusText('Settings saved');
                }}
                onRefreshOllama={async () => {
                    await refreshOllamaModels();
                    await loadData();
                    setStatusText('Ollama library refreshed');
                }}
                onCheckOllama={async () => {
                    const health = await checkOllamaHealth();
                    setStatusText(`Ollama: ${String(health.detail ?? health.ok ?? 'unknown')}`);
                }}
            />

            <ManifestToolsPanel
                onRebuild={async () => {
                    const response = await rebuildVectors();
                    setStatusText(`Indexed ${response.indexed_documents} manifest entries`);
                }}
            />

            <footer className="settings-page__status">{statusText}</footer>
        </div>
    );
}

export default SettingsPage;

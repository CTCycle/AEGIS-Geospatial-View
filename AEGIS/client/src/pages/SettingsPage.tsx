import { ReactNode, useCallback, useEffect, useMemo, useRef, useState } from 'react';

import ModelGrid from '../components/settings/ModelGrid';
import ModelProviderToggle from '../components/settings/ModelProviderToggle';
import ModelSearchBar from '../components/settings/ModelSearchBar';
import SettingsModal from '../components/settings/SettingsModal';
import {
    checkOllamaHealth,
    fetchChatModels,
    fetchChatSettings,
    pullOllamaModel,
    refreshOllamaModels,
    updateChatSettings
} from '../services/api';
import { ModelCardDescriptor, ModelProviderMode, ModelSettingsResponse, ModelSettingsUpdateRequest } from '../types';
import './SettingsPage.css';
import { PersistedSettingsPageState } from '../state/appState';
import { useActivePagePersistence } from '../hooks/useActivePagePersistence';

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
    const [isKeysModalOpen, setIsKeysModalOpen] = useState(false);
    const [isOllamaModalOpen, setIsOllamaModalOpen] = useState(false);
    const [openaiKey, setOpenaiKey] = useState('');
    const [googleKey, setGoogleKey] = useState('');
    const [ollamaUrlDraft, setOllamaUrlDraft] = useState(defaultSettings.ollama_url);

    const loadData = async () => {
        const [nextSettings, modelLibrary] = await Promise.all([
            fetchChatSettings(),
            fetchChatModels(),
        ]);
        setSettings(nextSettings);
        setProviderMode(nextSettings.active_provider_mode);
        setOllamaUrlDraft(nextSettings.ollama_url);
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

    const buildState = useCallback((scrollY: number): PersistedSettingsPageState => ({
        searchText,
        providerMode,
        statusText,
        scrollY,
        modelGridScrollTop: modelGridRef.current?.scrollTop ?? state.modelGridScrollTop,
    }), [searchText, providerMode, statusText, state.modelGridScrollTop]);

    const restoreState = useCallback(() => {
        window.scrollTo({ top: state.scrollY, behavior: 'auto' });
        if (modelGridRef.current) {
            modelGridRef.current.scrollTop = state.modelGridScrollTop;
        }
    }, [state.scrollY, state.modelGridScrollTop]);

    useActivePagePersistence({
        isActive,
        state,
        onStateChange,
        buildState,
        restoreState,
        syncDeps: [searchText, providerMode, statusText, state.modelGridScrollTop],
    });

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
        const nextProviderMode: ModelProviderMode = model.provider === 'ollama' ? 'local' : 'cloud';
        const payload: ModelSettingsUpdateRequest = {
            ...settings,
            active_provider_mode: nextProviderMode,
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

    const keysFooter: ReactNode = (
        <button
            type="button"
            className="primary-button"
            onClick={async () => {
                const updated = await updateChatSettings({
                    ...settings,
                    credentials: {
                        openai: openaiKey.trim() ? { api_key: openaiKey.trim() } : {},
                        google: googleKey.trim() ? { api_key: googleKey.trim() } : {},
                    },
                });
                setSettings(updated);
                setOpenaiKey('');
                setGoogleKey('');
                setStatusText('API keys saved');
                setIsKeysModalOpen(false);
            }}
        >
            Save keys
        </button>
    );

    const ollamaFooter: ReactNode = (
        <>
            <div className="row-actions">
                <button
                    type="button"
                    onClick={async () => {
                        const health = await checkOllamaHealth();
                        setStatusText(`Ollama: ${String(health.detail ?? health.ok ?? 'unknown')}`);
                    }}
                >
                    Check connection
                </button>
                <button
                    type="button"
                    onClick={async () => {
                        await refreshOllamaModels();
                        await loadData();
                        setStatusText('Ollama library refreshed');
                    }}
                >
                    Refresh models
                </button>
            </div>
            <button
                type="button"
                className="primary-button"
                onClick={async () => {
                    const updated = await updateChatSettings({
                        ...settings,
                        ollama_url: ollamaUrlDraft.trim() || defaultSettings.ollama_url,
                    });
                    setSettings(updated);
                    setOllamaUrlDraft(updated.ollama_url);
                    setStatusText('Ollama settings saved');
                    setIsOllamaModalOpen(false);
                }}
            >
                Save settings
            </button>
        </>
    );

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
                <div className="settings-page__search-with-actions">
                    <div className="settings-page__control-icons">
                        <button
                            type="button"
                            className="settings-icon-button"
                            onClick={() => setIsKeysModalOpen(true)}
                            aria-label="Manage API keys"
                            title="API key settings"
                        >
                            <span className="settings-icon-button__glyph" aria-hidden="true">⌁</span>
                        </button>
                        <button
                            type="button"
                            className="settings-icon-button"
                            onClick={() => setIsOllamaModalOpen(true)}
                            aria-label="Open Ollama settings"
                            title="Ollama settings"
                        >
                            <span className="settings-icon-button__glyph" aria-hidden="true">◉</span>
                        </button>
                    </div>
                    <ModelSearchBar value={searchText} onChange={setSearchText} />
                </div>
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

            {isKeysModalOpen && (
                <SettingsModal
                    title="API keys"
                    ariaLabel="API key management"
                    onClose={() => setIsKeysModalOpen(false)}
                    footer={keysFooter}
                >
                    <label>
                        OpenAI API key {settings.credentials.openai?.api_key ? '(Configured)' : '(Not configured)'}
                        <input
                            type="password"
                            value={openaiKey}
                            onChange={(event) => setOpenaiKey(event.target.value)}
                            placeholder="sk-..."
                        />
                    </label>
                    <label>
                        Google API key {settings.credentials.google?.api_key ? '(Configured)' : '(Not configured)'}
                        <input
                            type="password"
                            value={googleKey}
                            onChange={(event) => setGoogleKey(event.target.value)}
                            placeholder="AIza..."
                        />
                    </label>
                </SettingsModal>
            )}

            {isOllamaModalOpen && (
                <SettingsModal
                    title="Ollama settings"
                    ariaLabel="Ollama settings"
                    onClose={() => setIsOllamaModalOpen(false)}
                    footer={ollamaFooter}
                    footerClassName="settings-modal__footer settings-modal__footer--spread"
                >
                    <label>
                        Ollama server URL
                        <input value={ollamaUrlDraft} onChange={(event) => setOllamaUrlDraft(event.target.value)} />
                    </label>
                </SettingsModal>
            )}

            <footer className="settings-page__status">{statusText}</footer>
        </div>
    );
}

export default SettingsPage;

import { ReactNode, useCallback, useEffect, useMemo, useRef, useState } from 'react';

import ModelGrid from '../components/settings/ModelGrid';
import SettingsIconButton from '../components/settings/SettingsIconButton';
import ModelProviderToggle from '../components/settings/ModelProviderToggle';
import ModelSearchBar from '../components/settings/ModelSearchBar';
import SettingsModal from '../components/settings/SettingsModal';
import { ModelProviderMode } from '../types';
import './SettingsPage.css';
import { PersistedSettingsPageState } from '../state/appState';
import { useActivePagePersistence } from '../hooks/useActivePagePersistence';
import { useSettingsData } from '../hooks/useSettingsData';

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
    const {
        settings,
        cloudModels,
        localModels,
        providerMode,
        statusText,
        ollamaUrlDraft,
        setProviderMode,
        setOllamaUrlDraft,
        handleProviderModeChange,
        applyModelSelection,
        saveKeys,
        checkOllamaConnection,
        refreshOllamaLibrary,
        saveOllamaSettings,
        pullLocalModel,
    } = useSettingsData(state.statusText);
    const [searchText, setSearchText] = useState(queryState.searchText || state.searchText);
    const [providerModeInitialized, setProviderModeInitialized] = useState(false);
    const modelGridRef = useRef<HTMLDivElement | null>(null);
    const [isKeysModalOpen, setIsKeysModalOpen] = useState(false);
    const [isOllamaModalOpen, setIsOllamaModalOpen] = useState(false);
    const [openaiKey, setOpenaiKey] = useState('');
    const [googleKey, setGoogleKey] = useState('');

    useEffect(() => {
        if (providerModeInitialized) {
            return;
        }
        setProviderMode(queryState.providerMode || state.providerMode);
        setProviderModeInitialized(true);
    }, [providerModeInitialized, queryState.providerMode, setProviderMode, state.providerMode]);

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

    const keysFooter: ReactNode = (
        <button
            type="button"
            className="primary-button"
            onClick={async () => {
                await saveKeys(openaiKey, googleKey);
                setOpenaiKey('');
                setGoogleKey('');
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
                        await checkOllamaConnection();
                    }}
                >
                    Check connection
                </button>
                <button
                    type="button"
                    onClick={async () => {
                        await refreshOllamaLibrary();
                    }}
                >
                    Refresh models
                </button>
            </div>
            <button
                type="button"
                className="primary-button"
                onClick={async () => {
                    await saveOllamaSettings();
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
                    <p>Configure active providers and assign dedicated parser, agent, and chat models.</p>
                </div>
                <button type="button" className="settings-page__back" onClick={onBack}>Back to Chat</button>
            </header>

            <section className="settings-page__controls" aria-label="Settings controls">
                <ModelProviderToggle value={providerMode} onChange={handleProviderModeChange} />
                <div className="settings-page__search-with-actions">
                    <div className="settings-page__control-icons">
                        <SettingsIconButton
                            onClick={() => setIsKeysModalOpen(true)}
                            ariaLabel="Manage API keys"
                            title="API key settings"
                            glyph="⌁"
                        />
                        <SettingsIconButton
                            onClick={() => setIsOllamaModalOpen(true)}
                            ariaLabel="Open Ollama settings"
                            title="Ollama settings"
                            glyph="◉"
                        />
                    </div>
                    <ModelSearchBar value={searchText} onChange={setSearchText} />
                </div>
            </section>

            <ModelGrid
                containerRef={modelGridRef}
                models={displayedModels}
                localModelIds={localModelIds}
                selectedParserModel={{
                    provider: settings.parser_model_provider,
                    name: settings.parser_model_name,
                }}
                selectedChatModel={{
                    provider: settings.chat_model_provider,
                    name: settings.chat_model_name,
                }}
                selectedAgentModel={{
                    provider: settings.agent_model_provider,
                    name: settings.agent_model_name,
                }}
                onSelectParser={(model) => applyModelSelection('parser', model)}
                onSelectChat={(model) => applyModelSelection('chat', model)}
                onSelectAgent={(model) => applyModelSelection('agent', model)}
                onPull={async (model) => {
                    await pullLocalModel(model);
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

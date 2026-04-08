import { ReactNode, useCallback, useEffect, useMemo, useRef, useState } from 'react';

import ModelGrid from '../components/settings/ModelGrid';
import CredentialField from '../components/settings/CredentialField';
import SettingsIconButton from '../components/settings/SettingsIconButton';
import ModelProviderToggle from '../components/settings/ModelProviderToggle';
import ModelSearchBar from '../components/settings/ModelSearchBar';
import SettingsModal from '../components/settings/SettingsModal';
import './SettingsPage.css';
import { PersistedSettingsPageState } from '../state/appState';
import { useActivePagePersistence } from '../hooks/useActivePagePersistence';
import { useSettingsData } from '../hooks/useSettingsData';
import { useSettingsQueryState } from '../hooks/useSettingsQueryState';

interface SettingsPageProps {
    onBack: () => void;
    state: PersistedSettingsPageState;
    onStateChange: (state: PersistedSettingsPageState) => void;
    isActive: boolean;
}

function SettingsPage({ onBack, state, onStateChange, isActive }: SettingsPageProps) {
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
    const [providerModeInitialized, setProviderModeInitialized] = useState(false);
    const { searchText, setSearchText, initialProviderMode } = useSettingsQueryState({
        initialSearchText: state.searchText,
        providerMode,
        isActive,
    });
    const modelGridRef = useRef<HTMLDivElement | null>(null);
    const [isKeysModalOpen, setIsKeysModalOpen] = useState(false);
    const [isOllamaModalOpen, setIsOllamaModalOpen] = useState(false);
    const [openaiKey, setOpenaiKey] = useState('');
    const [googleKey, setGoogleKey] = useState('');
    const [cloudProviderFilter, setCloudProviderFilter] = useState('all');
    const [showLocalOnly, setShowLocalOnly] = useState(false);

    useEffect(() => {
        if (providerModeInitialized) {
            return;
        }
        setProviderMode(initialProviderMode || state.providerMode);
        setProviderModeInitialized(true);
    }, [providerModeInitialized, initialProviderMode, setProviderMode, state.providerMode]);

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

    const localModelIds = useMemo(() => new Set(localModels.map((item) => item.id)), [localModels]);

    const cloudProviderOptions = useMemo(() => {
        const providers = Array.from(new Set(cloudModels.map((model) => model.provider))).sort((left, right) => left.localeCompare(right));
        return [{ value: 'all', label: 'All providers' }, ...providers.map((provider) => ({ value: provider, label: provider }))];
    }, [cloudModels]);

    const displayedModels = useMemo(() => {
        const source = providerMode === 'local' ? localModels : cloudModels;
        const query = searchText.trim().toLowerCase();
        return source.filter((model) => {
            if (providerMode === 'cloud' && cloudProviderFilter !== 'all' && model.provider !== cloudProviderFilter) {
                return false;
            }
            if (showLocalOnly && !localModelIds.has(model.id)) {
                return false;
            }
            if (!query) {
                return true;
            }
            return (
                model.name.toLowerCase().includes(query)
                || model.description.toLowerCase().includes(query)
                || model.provider.toLowerCase().includes(query)
            );
        });
    }, [providerMode, localModels, cloudModels, searchText, cloudProviderFilter, localModelIds, showLocalOnly]);

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
                <button type="button" className="settings-page__back" onClick={onBack}>
                    <span className="settings-page__back-icon" aria-hidden="true">←</span>
                    <span>Back to Chat</span>
                </button>
            </header>

            <div className="settings-page__content">
                <div className="settings-page__layout">
                    <section className="settings-page__left-column">
                        <section className="settings-page__controls settings-page__controls--navbar" aria-label="Settings controls">
                            <div className="settings-page__controls-left">
                                <ModelProviderToggle value={providerMode} onChange={handleProviderModeChange} />
                                <label className="settings-page__cloud-filter">
                                    <span>Cloud provider</span>
                                    <select
                                        value={cloudProviderFilter}
                                        onChange={(event) => setCloudProviderFilter(event.target.value)}
                                        disabled={providerMode !== 'cloud'}
                                    >
                                        {cloudProviderOptions.map((option) => (
                                            <option key={option.value} value={option.value}>
                                                {option.label}
                                            </option>
                                        ))}
                                    </select>
                                </label>
                                <label className="settings-page__local-filter">
                                    <input
                                        type="checkbox"
                                        checked={showLocalOnly}
                                        onChange={(event) => setShowLocalOnly(event.target.checked)}
                                    />
                                    <span>Locally available</span>
                                </label>
                            </div>
                            <div className="settings-page__controls-spacer" aria-hidden="true" />
                            <div className="settings-page__controls-right">
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
                    </section>

                    <aside className="settings-page__right-column" aria-label="Model statistics">
                        <h2>Model Stats</h2>
                        <div className="settings-page__stats-table-wrap">
                            <table className="settings-page__stats-table">
                                <thead>
                                    <tr>
                                        <th scope="col">Model</th>
                                        <th scope="col">Provider</th>
                                        <th scope="col">Local</th>
                                        <th scope="col">Assigned</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    {displayedModels.length === 0 && (
                                        <tr>
                                            <td colSpan={4}>No models match the current filters.</td>
                                        </tr>
                                    )}
                                    {displayedModels.map((model) => {
                                        const assignedRoles: string[] = [];
                                        if (model.provider === settings.parser_model_provider && model.name === settings.parser_model_name) {
                                            assignedRoles.push('Parser');
                                        }
                                        if (model.provider === settings.chat_model_provider && model.name === settings.chat_model_name) {
                                            assignedRoles.push('Chat');
                                        }
                                        if (model.provider === settings.agent_model_provider && model.name === settings.agent_model_name) {
                                            assignedRoles.push('Agent');
                                        }
                                        return (
                                            <tr key={`stats:${model.provider}:${model.id}`}>
                                                <td>{model.name}</td>
                                                <td>{model.provider}</td>
                                                <td>{localModelIds.has(model.id) ? 'Yes' : 'No'}</td>
                                                <td>{assignedRoles.length > 0 ? assignedRoles.join(', ') : '—'}</td>
                                            </tr>
                                        );
                                    })}
                                </tbody>
                            </table>
                        </div>
                    </aside>
                </div>
                <footer className="settings-page__status">{statusText}</footer>
            </div>

            {isKeysModalOpen && (
                <SettingsModal
                    title="API keys"
                    ariaLabel="API key management"
                    onClose={() => setIsKeysModalOpen(false)}
                    footer={keysFooter}
                >
                    <CredentialField
                        label="OpenAI API key"
                        configured={Boolean(settings.credentials.openai?.api_key)}
                        placeholder="sk-..."
                        value={openaiKey}
                        onChange={setOpenaiKey}
                    />
                    <CredentialField
                        label="Google API key"
                        configured={Boolean(settings.credentials.google?.api_key)}
                        placeholder="AIza..."
                        value={googleKey}
                        onChange={setGoogleKey}
                    />
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
        </div>
    );
}

export default SettingsPage;

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
    const [providerFilter, setProviderFilter] = useState<'all' | 'ollama' | 'openai' | 'google'>('all');
    const [showLocalOnly, setShowLocalOnly] = useState(false);

    useEffect(() => {
        if (providerModeInitialized) {
            return;
        }
        setProviderMode(initialProviderMode || state.providerMode);
        setProviderModeInitialized(true);
    }, [providerModeInitialized, initialProviderMode, setProviderMode, state.providerMode]);

    useEffect(() => {
        if (providerFilter !== 'ollama' && showLocalOnly) {
            setShowLocalOnly(false);
        }
    }, [providerFilter, showLocalOnly]);

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
    const selectedModelStats = useMemo(() => {
        const rows = new Map<string, { model: string; provider: string; local: boolean; assignedRoles: string[] }>();
        const assignments = [
            { role: 'Parser', provider: settings.parser_model_provider, name: settings.parser_model_name },
            { role: 'Chat', provider: settings.chat_model_provider, name: settings.chat_model_name },
            { role: 'Agent', provider: settings.agent_model_provider, name: settings.agent_model_name },
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
    }, [
        settings.parser_model_provider,
        settings.parser_model_name,
        settings.chat_model_provider,
        settings.chat_model_name,
        settings.agent_model_provider,
        settings.agent_model_name,
        localModelIds,
    ]);

    const displayedModels = useMemo(() => {
        const source = (() => {
            if (providerFilter === 'all') {
                return [...cloudModels];
            }
            if (providerFilter === 'ollama') {
                return [...cloudModels.filter((model) => model.provider === 'ollama')];
            }
            return cloudModels.filter((model) => model.provider === providerFilter);
        })();
        const query = searchText.trim().toLowerCase();
        return source.filter((model) => {
            if (providerFilter === 'ollama' && showLocalOnly && !localModelIds.has(model.id)) {
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
    }, [providerFilter, cloudModels, searchText, localModelIds, showLocalOnly]);

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
                <div className="settings-page__header-actions">
                    <SettingsIconButton
                        onClick={() => setIsOllamaModalOpen(true)}
                        ariaLabel="Open Ollama settings"
                        title="Ollama settings"
                        icon={(
                            <svg viewBox="0 0 24 24" width="15" height="15" focusable="false">
                                <path d="M5 4h14a1 1 0 0 1 1 1v11a4 4 0 0 1-4 4H8a4 4 0 0 1-4-4V5a1 1 0 0 1 1-1zm1 2v10a2 2 0 0 0 2 2h8a2 2 0 0 0 2-2V6H6zm4 2h4a1 1 0 1 1 0 2h-4a1 1 0 1 1 0-2z" fill="currentColor" />
                            </svg>
                        )}
                    />
                    <SettingsIconButton
                        onClick={() => setIsKeysModalOpen(true)}
                        ariaLabel="Manage API keys"
                        title="API key settings"
                        icon={(
                            <svg viewBox="0 0 24 24" width="15" height="15" focusable="false">
                                <path d="M14 3a7 7 0 1 0 5.5 11.3L23 17.8V21h-3v-2h-2v-2h-2.2A7 7 0 0 0 14 3zm0 2a5 5 0 1 1 0 10 5 5 0 0 1 0-10z" fill="currentColor" />
                            </svg>
                        )}
                    />
                    <button type="button" className="settings-page__back" onClick={onBack} aria-label="Back to chat" title="Back to chat">
                        <span className="settings-page__back-icon" aria-hidden="true">←</span>
                    </button>
                </div>
            </header>

            <div className="settings-page__content">
                <div className="settings-page__layout">
                    <section className="settings-page__left-column">
                        <section className="settings-page__controls settings-page__controls--navbar" aria-label="Settings controls">
                            <div className="settings-page__controls-left">
                                <ModelProviderToggle value={providerFilter} onChange={setProviderFilter} />
                                {providerFilter === 'ollama' && (
                                    <label className="settings-page__local-filter">
                                        <input
                                            type="checkbox"
                                            checked={showLocalOnly}
                                            onChange={(event) => setShowLocalOnly(event.target.checked)}
                                        />
                                        <span>Select all available</span>
                                    </label>
                                )}
                            </div>
                            <div className="settings-page__controls-spacer" aria-hidden="true" />
                            <div className="settings-page__controls-right">
                                <button
                                    type="button"
                                    className="settings-page__refresh"
                                    onClick={refreshOllamaLibrary}
                                    aria-label="Refresh from Ollama API"
                                    title="Refresh from Ollama API"
                                >
                                    <svg viewBox="0 0 24 24" width="15" height="15" aria-hidden="true" focusable="false">
                                        <path
                                            d="M12 4V1L8 5l4 4V6a6 6 0 0 1 6 6 6 6 0 0 1-6 6 6 6 0 0 1-6-6H4a8 8 0 0 0 8 8 8 8 0 0 0 8-8 8 8 0 0 0-8-8z"
                                            fill="currentColor"
                                        />
                                    </svg>
                                </button>
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
                                    {selectedModelStats.length === 0 && (
                                        <tr>
                                            <td colSpan={4}>No models selected yet.</td>
                                        </tr>
                                    )}
                                    {selectedModelStats.map((row) => {
                                        return (
                                            <tr key={`stats:${row.provider}:${row.model}`}>
                                                <td>{row.model}</td>
                                                <td>{row.provider}</td>
                                                <td>{row.local ? 'Yes' : 'No'}</td>
                                                <td>{row.assignedRoles.join(', ')}</td>
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

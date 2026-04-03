import React, { useEffect, useState } from 'react';

import { ModelProviderMode, ModelSettingsResponse } from '../../types';

interface ConfigurationPanelProps {
    providerMode: ModelProviderMode;
    settings: ModelSettingsResponse;
    onSave: (payload: Record<string, unknown>) => void;
    onRefreshOllama: () => void;
    onCheckOllama: () => void;
}

const ConfigurationPanel: React.FC<ConfigurationPanelProps> = ({
    providerMode,
    settings,
    onSave,
    onRefreshOllama,
    onCheckOllama,
}) => {
    const [ollamaUrl, setOllamaUrl] = useState(settings.ollama_url);
    const [openaiBaseUrl, setOpenaiBaseUrl] = useState(settings.openai_base_url ?? '');
    const [googleBaseUrl, setGoogleBaseUrl] = useState(settings.google_base_url ?? '');
    const [openaiKey, setOpenaiKey] = useState('');
    const [googleKey, setGoogleKey] = useState('');

    useEffect(() => {
        setOllamaUrl(settings.ollama_url);
        setOpenaiBaseUrl(settings.openai_base_url ?? '');
        setGoogleBaseUrl(settings.google_base_url ?? '');
    }, [settings]);

    return (
        <section className="configuration-panel">
            {providerMode === 'local' ? (
                <div>
                    <h3>Ollama</h3>
                    <label>
                        Ollama URL
                        <input value={ollamaUrl} onChange={(event) => setOllamaUrl(event.target.value)} />
                    </label>
                    <div className="row-actions">
                        <button type="button" onClick={onCheckOllama}>Check connection</button>
                        <button type="button" onClick={onRefreshOllama}>Refresh models</button>
                    </div>
                </div>
            ) : (
                <div className="configuration-panel__cloud">
                    <h3>Cloud Providers</h3>
                    <label>
                        OpenAI Base URL
                        <input value={openaiBaseUrl} onChange={(event) => setOpenaiBaseUrl(event.target.value)} />
                    </label>
                    <label>
                        OpenAI API Key
                        <input type="password" value={openaiKey} onChange={(event) => setOpenaiKey(event.target.value)} />
                    </label>
                    <label>
                        Google Base URL
                        <input value={googleBaseUrl} onChange={(event) => setGoogleBaseUrl(event.target.value)} />
                    </label>
                    <label>
                        Google API Key
                        <input type="password" value={googleKey} onChange={(event) => setGoogleKey(event.target.value)} />
                    </label>
                </div>
            )}
            <button
                type="button"
                className="primary-button"
                onClick={() =>
                    onSave({
                        ...settings,
                        ollama_url: ollamaUrl,
                        openai_base_url: openaiBaseUrl || null,
                        google_base_url: googleBaseUrl || null,
                        credentials: {
                            openai: { api_key: openaiKey },
                            google: { api_key: googleKey },
                        },
                    })
                }
            >
                Save Settings
            </button>
        </section>
    );
};

export default ConfigurationPanel;

import { useCallback, useEffect, useState } from 'react';

import {
    checkOllamaHealth,
    fetchChatModels,
    fetchChatSettings,
    pullOllamaModel,
    refreshOllamaModels,
    updateChatSettings
} from '../services/api';
import {
    ModelCardDescriptor,
    ModelProviderMode,
    ModelSettingsResponse,
    ModelSettingsUpdateRequest
} from '../types';

const defaultSettings: ModelSettingsResponse = {
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

export interface UseSettingsDataState {
    settings: ModelSettingsResponse;
    cloudModels: ModelCardDescriptor[];
    localModels: ModelCardDescriptor[];
    providerMode: ModelProviderMode;
    statusText: string;
    ollamaUrlDraft: string;
    setStatusText: (value: string) => void;
    setProviderMode: (value: ModelProviderMode) => void;
    setOllamaUrlDraft: (value: string) => void;
    loadData: () => Promise<void>;
    handleProviderModeChange: (mode: ModelProviderMode) => Promise<void>;
    applyModelSelection: (kind: 'parser' | 'agent' | 'chat', model: ModelCardDescriptor) => Promise<void>;
    saveKeys: (openaiKey: string, googleKey: string) => Promise<void>;
    checkOllamaConnection: () => Promise<void>;
    refreshOllamaLibrary: () => Promise<void>;
    saveOllamaSettings: () => Promise<void>;
    pullLocalModel: (model: ModelCardDescriptor) => Promise<void>;
}

const toErrorText = (error: unknown): string =>
    error instanceof Error ? error.message : String(error);

export const useSettingsData = (initialStatusText: string): UseSettingsDataState => {
    const [settings, setSettings] = useState<ModelSettingsResponse>(defaultSettings);
    const [cloudModels, setCloudModels] = useState<ModelCardDescriptor[]>([]);
    const [localModels, setLocalModels] = useState<ModelCardDescriptor[]>([]);
    const [providerMode, setProviderMode] = useState<ModelProviderMode>(defaultSettings.active_provider_mode);
    const [statusText, setStatusText] = useState(initialStatusText);
    const [ollamaUrlDraft, setOllamaUrlDraft] = useState(defaultSettings.ollama_url);

    const loadData = useCallback(async () => {
        const [nextSettings, modelLibrary] = await Promise.all([
            fetchChatSettings(),
            fetchChatModels(),
        ]);
        setSettings(nextSettings);
        setProviderMode(nextSettings.active_provider_mode);
        setOllamaUrlDraft(nextSettings.ollama_url);
        setCloudModels(modelLibrary.cloud);
        setLocalModels(modelLibrary.local);
    }, []);

    useEffect(() => {
        loadData().catch((error: unknown) => {
            setStatusText(`Load failed: ${toErrorText(error)}`);
        });
    }, [loadData]);

    const handleProviderModeChange = useCallback(async (mode: ModelProviderMode) => {
        setProviderMode(mode);
        try {
            const updated = await updateChatSettings({
                ...settings,
                active_provider_mode: mode,
            });
            setSettings(updated);
            setStatusText(`Provider mode set to ${mode}`);
        } catch (error: unknown) {
            setStatusText(`Provider mode update failed: ${toErrorText(error)}`);
        }
    }, [settings]);

    const applyModelSelection = useCallback(async (kind: 'parser' | 'agent' | 'chat', model: ModelCardDescriptor) => {
        const nextProviderMode: ModelProviderMode = model.provider === 'ollama' ? 'local' : 'cloud';
        const payload: ModelSettingsUpdateRequest = {
            ...settings,
            active_provider_mode: nextProviderMode,
            chat_model_provider: kind === 'chat' ? model.provider : settings.chat_model_provider,
            chat_model_name: kind === 'chat' ? model.name : settings.chat_model_name,
            parser_model_provider: kind === 'parser' ? model.provider : settings.parser_model_provider,
            parser_model_name: kind === 'parser' ? model.name : settings.parser_model_name,
            agent_model_provider: kind === 'agent' ? model.provider : settings.agent_model_provider,
            agent_model_name: kind === 'agent' ? model.name : settings.agent_model_name,
        };
        const updated = await updateChatSettings(payload);
        setSettings(updated);
        setProviderMode(updated.active_provider_mode);
        setStatusText(`Selected ${model.name} for ${kind}`);
    }, [settings]);

    const saveKeys = useCallback(async (openaiKey: string, googleKey: string) => {
        const updated = await updateChatSettings({
            ...settings,
            credentials: {
                openai: openaiKey.trim() ? { api_key: openaiKey.trim() } : {},
                google: googleKey.trim() ? { api_key: googleKey.trim() } : {},
            },
        });
        setSettings(updated);
        setStatusText('API keys saved');
    }, [settings]);

    const checkOllamaConnection = useCallback(async () => {
        const health = await checkOllamaHealth();
        setStatusText(`Ollama: ${String(health.detail ?? health.ok ?? 'unknown')}`);
    }, []);

    const refreshOllamaLibrary = useCallback(async () => {
        await refreshOllamaModels();
        await loadData();
        setStatusText('Ollama library refreshed');
    }, [loadData]);

    const saveOllamaSettings = useCallback(async () => {
        const updated = await updateChatSettings({
            ...settings,
            ollama_url: ollamaUrlDraft.trim() || defaultSettings.ollama_url,
        });
        setSettings(updated);
        setOllamaUrlDraft(updated.ollama_url);
        setStatusText('Ollama settings saved');
    }, [ollamaUrlDraft, settings]);

    const pullLocalModel = useCallback(async (model: ModelCardDescriptor) => {
        await pullOllamaModel(model.name);
        await refreshOllamaModels();
        await loadData();
        setStatusText(`Pulled ${model.name}`);
    }, [loadData]);

    return {
        settings,
        cloudModels,
        localModels,
        providerMode,
        statusText,
        ollamaUrlDraft,
        setStatusText,
        setProviderMode,
        setOllamaUrlDraft,
        loadData,
        handleProviderModeChange,
        applyModelSelection,
        saveKeys,
        checkOllamaConnection,
        refreshOllamaLibrary,
        saveOllamaSettings,
        pullLocalModel,
    };
};

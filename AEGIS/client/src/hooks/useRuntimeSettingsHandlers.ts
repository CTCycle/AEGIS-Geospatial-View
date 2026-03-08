import { useCallback } from 'react';

import { AGENT_MODEL_CHOICES, CLOUD_MODEL_CHOICES, CLOUD_PROVIDERS } from '../constants';
import { RuntimeSettings } from '../types';

interface UseRuntimeSettingsHandlersParams {
    settings: RuntimeSettings;
    onSettingsChange: (next: RuntimeSettings) => void;
}

const isKnownCloudProvider = (value: string): boolean => CLOUD_PROVIDERS.includes(value);

const useRuntimeSettingsHandlers = ({
    settings,
    onSettingsChange,
}: UseRuntimeSettingsHandlersParams) => {
    const handleUseCloudServicesChange = useCallback((value: boolean) => {
        onSettingsChange({ ...settings, useCloudServices: value });
    }, [settings, onSettingsChange]);

    const handleProviderChange = useCallback((value: string) => {
        if (!isKnownCloudProvider(value)) {
            return;
        }
        const availableModels = CLOUD_MODEL_CHOICES[value] || [];
        onSettingsChange({
            ...settings,
            provider: value,
            cloudModel: availableModels[0] || '',
        });
    }, [settings, onSettingsChange]);

    const handleCloudModelChange = useCallback((value: string) => {
        const availableModels = CLOUD_MODEL_CHOICES[settings.provider] || [];
        if (!availableModels.includes(value)) {
            return;
        }
        onSettingsChange({ ...settings, cloudModel: value });
    }, [settings, onSettingsChange]);

    const handleAgentModelChange = useCallback((value: string) => {
        if (!AGENT_MODEL_CHOICES.includes(value)) {
            return;
        }
        onSettingsChange({ ...settings, agentModel: value });
    }, [settings, onSettingsChange]);

    return {
        handleUseCloudServicesChange,
        handleProviderChange,
        handleCloudModelChange,
        handleAgentModelChange,
    };
};

export default useRuntimeSettingsHandlers;

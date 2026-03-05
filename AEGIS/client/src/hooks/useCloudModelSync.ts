import { useEffect } from 'react';

import { CLOUD_MODEL_CHOICES } from '../constants';
import { RuntimeSettings } from '../types';

interface UseCloudModelSyncParams {
    settings: RuntimeSettings;
    onSettingsChange: (next: RuntimeSettings) => void;
}

const useCloudModelSync = ({ settings, onSettingsChange }: UseCloudModelSyncParams): void => {
    useEffect(() => {
        const models = CLOUD_MODEL_CHOICES[settings.provider] || [];
        if (!models.includes(settings.cloudModel) && models.length > 0) {
            onSettingsChange({ ...settings, cloudModel: models[0] });
        }
    }, [settings.provider, settings.cloudModel, settings, onSettingsChange]);
};

export default useCloudModelSync;

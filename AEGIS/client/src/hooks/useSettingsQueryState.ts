import { useEffect, useMemo, useState } from 'react';

import { ModelProviderMode } from '../types';

interface SettingsQueryState {
    searchText: string;
    providerMode: ModelProviderMode;
}

interface UseSettingsQueryStateParams {
    initialSearchText: string;
    providerMode: ModelProviderMode;
    isActive: boolean;
}

const isProviderMode = (value: string | null): value is ModelProviderMode =>
    value === 'local' || value === 'cloud';

const readQueryState = (): SettingsQueryState => {
    const params = new URLSearchParams(window.location.search);
    const searchText = params.get('q') ?? '';
    const mode = params.get('mode');
    return {
        searchText,
        providerMode: isProviderMode(mode) ? mode : 'local',
    };
};

const writeQueryState = (searchText: string, providerMode: ModelProviderMode): void => {
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

export const useSettingsQueryState = ({
    initialSearchText,
    providerMode,
    isActive,
}: UseSettingsQueryStateParams) => {
    const initialQueryState = useMemo(readQueryState, []);
    const [searchText, setSearchText] = useState(initialQueryState.searchText || initialSearchText);

    useEffect(() => {
        if (!isActive) {
            return;
        }
        writeQueryState(searchText, providerMode);
    }, [searchText, providerMode, isActive]);

    return {
        searchText,
        setSearchText,
        initialProviderMode: initialQueryState.providerMode,
    };
};

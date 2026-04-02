import React, { useMemo, useState } from 'react';

import { DEFAULT_AOI_RADIUS_M, DEFAULT_BASEMAP_ID } from '../constants';
import { CatalogResponse, LocationSearchRequest } from '../types';
import PanelHeader from './PanelHeader';
import './LocationSearch.css';

interface LocationSearchProps {
    onSearch: (request: LocationSearchRequest) => void;
    isLoading: boolean;
    catalog: CatalogResponse;
    isCatalogLoading: boolean;
}

type SearchMode = 'address' | 'coordinates';

const LocationSearch: React.FC<LocationSearchProps> = ({
    onSearch,
    isLoading,
    catalog,
    isCatalogLoading,
}) => {
    const [mode, setMode] = useState<SearchMode>('address');
    const [address, setAddress] = useState('');
    const [latitude, setLatitude] = useState('');
    const [longitude, setLongitude] = useState('');
    const [radiusM, setRadiusM] = useState(String(DEFAULT_AOI_RADIUS_M));
    const [selectedProvider, setSelectedProvider] = useState('all');
    const [selectedBasemapId, setSelectedBasemapId] = useState<string>(DEFAULT_BASEMAP_ID);
    const [selectedOverlayIds, setSelectedOverlayIds] = useState<string[]>([]);
    const [errors, setErrors] = useState<{ address?: string; latitude?: string; longitude?: string }>({});

    const providers = useMemo(() => {
        return [{ id: 'all', name: 'All providers', docs_url: '', commercial_notes: 'Show all providers', warning_level: 'low' }, ...catalog.providers];
    }, [catalog.providers]);

    const filteredOverlays = useMemo(() => {
        if (selectedProvider === 'all') {
            return catalog.overlays;
        }
        return catalog.overlays.filter((item) => item.provider === selectedProvider);
    }, [catalog.overlays, selectedProvider]);

    const currentProviderDescription = useMemo(() => {
        const provider = catalog.providers.find((p) => p.id === selectedProvider);
        return provider?.commercial_notes || '';
    }, [catalog.providers, selectedProvider]);

    const resetErrors = () => setErrors({});

    const validateCoordinates = () => {
        const newErrors: { latitude?: string; longitude?: string } = {};
        const parsedLat = Number.parseFloat(latitude);
        const parsedLon = Number.parseFloat(longitude);

        if (!latitude.trim()) {
            newErrors.latitude = 'Latitude is required in coordinate mode.';
        } else if (Number.isNaN(parsedLat)) {
            newErrors.latitude = 'Latitude must be numeric.';
        } else if (parsedLat < -90 || parsedLat > 90) {
            newErrors.latitude = 'Latitude must be between -90 and 90.';
        }

        if (!longitude.trim()) {
            newErrors.longitude = 'Longitude is required in coordinate mode.';
        } else if (Number.isNaN(parsedLon)) {
            newErrors.longitude = 'Longitude must be numeric.';
        } else if (parsedLon < -180 || parsedLon > 180) {
            newErrors.longitude = 'Longitude must be between -180 and 180.';
        }

        return { newErrors, parsedLat, parsedLon };
    };

    const validateAddress = () => {
        if (!address.trim()) {
            return 'Enter an address (e.g., "Via Tesserete 29, Tesserete, Svizzera").';
        }
        return '';
    };

    const getSelectedLegacyFilters = (): string[] => {
        return selectedOverlayIds
            .filter((id) => id.startsWith('GIBS_'))
            .map((id) => id.replace(/^GIBS_/, ''));
    };

    const handleSubmit = (event: React.FormEvent) => {
        event.preventDefault();
        resetErrors();
        const radiusValue = Number.parseFloat(radiusM);
        const normalizedRadius = Number.isFinite(radiusValue) && radiusValue > 0 ? radiusValue : DEFAULT_AOI_RADIUS_M;

        if (mode === 'address') {
            const addressError = validateAddress();
            if (addressError) {
                setErrors({ address: addressError });
                return;
            }
        }

        if (mode === 'coordinates') {
            const { newErrors, parsedLat, parsedLon } = validateCoordinates();
            if (newErrors.latitude || newErrors.longitude) {
                setErrors(newErrors);
                return;
            }
            const request: LocationSearchRequest = {
                datetime: new Date().toISOString(),
                use_coordinates: true,
                latitude: parsedLat,
                longitude: parsedLon,
                radius_m: normalizedRadius,
                filters: getSelectedLegacyFilters(),
                overlay_ids: selectedOverlayIds,
                basemap_id: selectedBasemapId,
                aoi: { mode: 'radius', radius_m: normalizedRadius },
            };
            onSearch(request);
            return;
        }

        const request: LocationSearchRequest = {
            datetime: new Date().toISOString(),
            use_coordinates: false,
            address: address.trim(),
            radius_m: normalizedRadius,
            filters: getSelectedLegacyFilters(),
            overlay_ids: selectedOverlayIds,
            basemap_id: selectedBasemapId,
            aoi: { mode: 'radius', radius_m: normalizedRadius },
        };
        onSearch(request);
    };

    const toggleOverlay = (overlayId: string) => {
        setSelectedOverlayIds((current) => (
            current.includes(overlayId)
                ? current.filter((item) => item !== overlayId)
                : [...current, overlayId]
        ));
    };

    return (
        <form className="location-container" onSubmit={handleSubmit}>
            <div className="header-row">
                <PanelHeader
                    title="Location search"
                    description="Specify where to focus the map."
                />
                <fieldset className="mode-switch">
                    <legend className="mode-switch-label">Search mode</legend>
                    <button
                        type="button"
                        className={`mode-tab ${mode === 'address' ? 'active' : ''}`}
                        onClick={() => setMode('address')}
                        aria-pressed={mode === 'address'}
                    >
                        Address
                    </button>
                    <button
                        type="button"
                        className={`mode-tab ${mode === 'coordinates' ? 'active' : ''}`}
                        onClick={() => setMode('coordinates')}
                        aria-pressed={mode === 'coordinates'}
                    >
                        Coordinates
                    </button>
                </fieldset>
            </div>

            {mode === 'address' && (
                <div className="form-group full-width">
                    <label htmlFor="address">Full Address</label>
                    <input
                        id="address"
                        type="text"
                        placeholder="e.g., Via Tesserete 29, Tesserete, Svizzera"
                        value={address}
                        onChange={(e) => setAddress(e.target.value)}
                    />
                    {errors.address && <p className="error-text">{errors.address}</p>}
                </div>
            )}
            {mode === 'coordinates' && (
                <div className="field-grid">
                    <div className="form-group">
                        <label htmlFor="latitude">Latitude</label>
                        <input
                            id="latitude"
                            type="number"
                            step="0.000001"
                            value={latitude}
                            onChange={(e) => setLatitude(e.target.value)}
                        />
                        {errors.latitude && <p className="error-text">{errors.latitude}</p>}
                    </div>
                    <div className="form-group">
                        <label htmlFor="longitude">Longitude</label>
                        <input
                            id="longitude"
                            type="number"
                            step="0.000001"
                            value={longitude}
                            onChange={(e) => setLongitude(e.target.value)}
                        />
                        {errors.longitude && <p className="error-text">{errors.longitude}</p>}
                    </div>
                </div>
            )}

            <div className="field-grid">
                <div className="form-group">
                    <label htmlFor="radius-m">AOI Radius (m)</label>
                    <input
                        id="radius-m"
                        type="number"
                        min={100}
                        step={100}
                        value={radiusM}
                        onChange={(e) => setRadiusM(e.target.value)}
                    />
                </div>
                <div className="form-group">
                    <label htmlFor="basemap">Basemap</label>
                    <select
                        id="basemap"
                        value={selectedBasemapId}
                        onChange={(e) => setSelectedBasemapId(e.target.value)}
                        disabled={isCatalogLoading}
                    >
                        {catalog.basemaps.map((basemap) => (
                            <option key={basemap.id} value={basemap.id}>
                                {basemap.label}
                            </option>
                        ))}
                    </select>
                </div>
            </div>

            <div className="field-grid">
                <div className="form-group">
                    <label htmlFor="data-provider">Data provider</label>
                    <select
                        id="data-provider"
                        value={selectedProvider}
                        onChange={(e) => setSelectedProvider(e.target.value)}
                    >
                        {providers.map((provider) => (
                            <option key={provider.id} value={provider.id}>
                                {provider.name || provider.id}
                            </option>
                        ))}
                    </select>
                    {currentProviderDescription && (
                        <p className="provider-description">{currentProviderDescription}</p>
                    )}
                </div>
            </div>

            <div className="form-group full-width">
                <label>Overlay layers</label>
                <div className="chip-container">
                    {filteredOverlays.map((overlay) => (
                        <button
                            key={overlay.id}
                            type="button"
                            className={`chip ${selectedOverlayIds.includes(overlay.id) ? 'chip--selected' : ''}`}
                            onClick={() => toggleOverlay(overlay.id)}
                            aria-pressed={selectedOverlayIds.includes(overlay.id)}
                        >
                            {overlay.label}
                        </button>
                    ))}
                    {filteredOverlays.length === 0 && (
                        <span className="no-filters">No overlays available for provider.</span>
                    )}
                </div>
            </div>

            <div className="actions">
                <button className="primary-button" type="submit" disabled={isLoading || isCatalogLoading}>
                    {isLoading ? 'Searching...' : 'Search'}
                </button>
            </div>
        </form>
    );
};

export default LocationSearch;

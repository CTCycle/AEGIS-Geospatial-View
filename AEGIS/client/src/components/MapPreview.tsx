import React, { useEffect, useMemo, useRef, useState } from 'react';
import maplibregl, { LngLatBoundsLike, Map, StyleSpecification } from 'maplibre-gl';

import { MapSession, SearchResponsePayload } from '../types';
import './MapPreview.css';

interface MapPreviewProps {
    payload?: SearchResponsePayload;
    isLoading: boolean;
    emptyMessage?: string;
}

const buildStyle = (mapSession?: MapSession): StyleSpecification => {
    const basemap = mapSession?.basemap;
    const baseTileUrl = basemap?.tile_url || 'https://tile.openstreetmap.org/{z}/{x}/{y}.png';
    return {
        version: 8,
        sources: {
            basemap: {
                type: 'raster',
                tiles: [baseTileUrl],
                tileSize: 256,
                attribution: basemap?.attribution || '© OpenStreetMap contributors',
            },
        },
        layers: [
            {
                id: 'basemap',
                type: 'raster',
                source: 'basemap',
                minzoom: 0,
                maxzoom: 22,
            },
        ],
    };
};

const addOverlayLayers = (map: Map, mapSession?: MapSession) => {
    const overlays = mapSession?.overlays || [];
    overlays.forEach((overlay, index) => {
        const sourceId = `overlay-source-${overlay.id}`;
        const layerId = `overlay-layer-${overlay.id}`;
        const opacity = typeof overlay.default_opacity === 'number' ? overlay.default_opacity : 0.65;

        if (overlay.type === 'tile' && overlay.url) {
            map.addSource(sourceId, {
                type: 'raster',
                tiles: [overlay.url],
                tileSize: 256,
            });
            map.addLayer({
                id: layerId,
                source: sourceId,
                type: 'raster',
                paint: { 'raster-opacity': opacity },
            });
            return;
        }

        if ((overlay.type === 'wms' || overlay.type === 'wmts') && overlay.url) {
            const wmsTiles = `${overlay.url}?service=WMS&request=GetMap&layers=${overlay.layers || '0'}&styles=&format=image/png&transparent=true&version=1.1.1&srs=EPSG:3857&bbox={bbox-epsg-3857}&width=256&height=256`;
            map.addSource(sourceId, {
                type: 'raster',
                tiles: [wmsTiles],
                tileSize: 256,
            });
            map.addLayer({
                id: layerId,
                source: sourceId,
                type: 'raster',
                paint: { 'raster-opacity': opacity },
            });
            return;
        }

        if (overlay.type === 'point-insight') {
            const center = mapSession?.center;
            if (typeof center?.longitude !== 'number' || typeof center?.latitude !== 'number') {
                return;
            }
            map.addSource(sourceId, {
                type: 'geojson',
                data: {
                    type: 'FeatureCollection',
                    features: [
                        {
                            type: 'Feature',
                            properties: { label: overlay.label },
                            geometry: {
                                type: 'Point',
                                coordinates: [center.longitude, center.latitude],
                            },
                        },
                    ],
                },
            });
            map.addLayer({
                id: layerId,
                source: sourceId,
                type: 'circle',
                paint: {
                    'circle-radius': 8 + index,
                    'circle-color': '#ef4444',
                    'circle-opacity': opacity,
                    'circle-stroke-width': 1,
                    'circle-stroke-color': '#111827',
                },
            });
        }
    });
};

const normalizeBounds = (bounds?: number[]): LngLatBoundsLike | null => {
    if (!Array.isArray(bounds) || bounds.length !== 4) {
        return null;
    }
    const [minx, miny, maxx, maxy] = bounds;
    return [[minx, miny], [maxx, maxy]];
};

const MapPreview: React.FC<MapPreviewProps> = ({
    payload,
    isLoading,
    emptyMessage = 'Run a search to display the map.',
}) => {
    const mapContainerRef = useRef<HTMLDivElement | null>(null);
    const mapRef = useRef<Map | null>(null);
    const mapSession = payload?.map_session;
    const [overlayVisibility, setOverlayVisibility] = useState<Record<string, boolean>>({});
    const [overlayOpacity, setOverlayOpacity] = useState<Record<string, number>>({});
    const hasCenter = useMemo(() => {
        return typeof mapSession?.center?.latitude === 'number' && typeof mapSession?.center?.longitude === 'number';
    }, [mapSession]);

    useEffect(() => {
        const overlays = mapSession?.overlays || [];
        const visibility: Record<string, boolean> = {};
        const opacity: Record<string, number> = {};
        overlays.forEach((overlay) => {
            visibility[overlay.id] = true;
            opacity[overlay.id] = typeof overlay.default_opacity === 'number' ? overlay.default_opacity : 0.65;
        });
        setOverlayVisibility(visibility);
        setOverlayOpacity(opacity);
    }, [mapSession]);

    useEffect(() => {
        if (!mapContainerRef.current || !hasCenter || !mapSession?.center) {
            return;
        }
        if (mapRef.current) {
            mapRef.current.remove();
            mapRef.current = null;
        }
        const map = new maplibregl.Map({
            container: mapContainerRef.current,
            style: buildStyle(mapSession),
            center: [mapSession.center.longitude!, mapSession.center.latitude!],
            zoom: 12,
        });
        map.addControl(new maplibregl.NavigationControl({ showCompass: true }), 'top-right');
        map.on('load', () => {
            addOverlayLayers(map, mapSession);
            const bounds = normalizeBounds(mapSession.bounds);
            if (bounds) {
                map.fitBounds(bounds, { padding: 30, duration: 0 });
            }
        });
        mapRef.current = map;
        return () => {
            map.remove();
            mapRef.current = null;
        };
    }, [mapSession, hasCenter]);

    useEffect(() => {
        const map = mapRef.current;
        if (!map || !mapSession?.overlays?.length) {
            return;
        }
        mapSession.overlays.forEach((overlay) => {
            const layerId = `overlay-layer-${overlay.id}`;
            if (!map.getLayer(layerId)) {
                return;
            }
            const visible = overlayVisibility[overlay.id] ?? true;
            map.setLayoutProperty(layerId, 'visibility', visible ? 'visible' : 'none');
            const opacityValue = overlayOpacity[overlay.id] ?? overlay.default_opacity ?? 0.65;
            if (overlay.type === 'point-insight') {
                map.setPaintProperty(layerId, 'circle-opacity', opacityValue);
            } else {
                map.setPaintProperty(layerId, 'raster-opacity', opacityValue);
            }
        });
    }, [mapSession, overlayVisibility, overlayOpacity]);

    const renderContent = () => {
        if (isLoading) {
            return (
                <div className="spinner-container">
                    <div className="animate-spin rounded-full h-12 w-12 border-4 border-primary/20 border-t-primary"></div>
                    <p className="loading-text">Rendering map...</p>
                </div>
            );
        }
        if (!payload || !payload.satellite_imagery) {
            return <div className="empty-state">{emptyMessage}</div>;
        }
        if (!hasCenter) {
            return <div className="empty-state">Map center unavailable for interactive rendering.</div>;
        }
        return (
            <div className="maplibre-wrap">
                <div ref={mapContainerRef} className="maplibre-container" />
                {!!mapSession?.overlays?.length && (
                    <div className="overlay-controls">
                        {mapSession.overlays.map((overlay) => (
                            <div key={overlay.id} className="overlay-control-row">
                                <label>
                                    <input
                                        type="checkbox"
                                        checked={overlayVisibility[overlay.id] ?? true}
                                        onChange={(event) => {
                                            setOverlayVisibility((current) => ({
                                                ...current,
                                                [overlay.id]: event.target.checked,
                                            }));
                                        }}
                                    />
                                    {overlay.label}
                                </label>
                                <input
                                    type="range"
                                    min={0}
                                    max={100}
                                    value={Math.round((overlayOpacity[overlay.id] ?? overlay.default_opacity ?? 0.65) * 100)}
                                    onChange={(event) => {
                                        const value = Number(event.target.value) / 100;
                                        setOverlayOpacity((current) => ({
                                            ...current,
                                            [overlay.id]: value,
                                        }));
                                    }}
                                />
                            </div>
                        ))}
                    </div>
                )}
                {!!mapSession?.compliance_warnings?.length && (
                    <div className="compliance-panel">
                        {mapSession.compliance_warnings.map((warning) => (
                            <p key={warning}>{warning}</p>
                        ))}
                    </div>
                )}
            </div>
        );
    };

    return (
        <div className="map-canvas">
            <div className="map-content">
                {renderContent()}
            </div>
        </div>
    );
};

export default MapPreview;

import React, { useEffect, useMemo, useRef, useState } from 'react';
import maplibregl, { LngLatBoundsLike, Map, StyleSpecification } from 'maplibre-gl';

import {
    DEFAULT_BASE_ATTRIBUTION,
    DEFAULT_BASE_TILE_URL,
    DEFAULT_OVERLAY_OPACITY,
    DEFAULT_WMS_EXCEPTIONS,
    DEFAULT_WMS_LAYER_ID,
    DEFAULT_WMS_VERSION,
    DEFAULT_WMTS_FORMAT,
    DEFAULT_WMTS_MATRIX_SET,
} from '../constants';
import { MapSession, SearchResponsePayload } from '../types';
import './MapPreview.css';

interface MapPreviewProps {
    payload?: SearchResponsePayload;
    isLoading: boolean;
    emptyMessage?: string;
    initialOverlayVisibility?: Record<string, boolean>;
    initialOverlayOpacity?: Record<string, number>;
    onOverlayStateChange?: (state: {
        overlayVisibility: Record<string, boolean>;
        overlayOpacity: Record<string, number>;
    }) => void;
}

type OverlayEntry = NonNullable<MapSession['overlays']>[number];

const recordBooleanEqual = (a: Record<string, boolean>, b: Record<string, boolean>): boolean => {
    const aKeys = Object.keys(a);
    const bKeys = Object.keys(b);
    if (aKeys.length !== bKeys.length) {
        return false;
    }
    return aKeys.every((key) => a[key] === b[key]);
};

const recordNumberEqual = (a: Record<string, number>, b: Record<string, number>): boolean => {
    const aKeys = Object.keys(a);
    const bKeys = Object.keys(b);
    if (aKeys.length !== bKeys.length) {
        return false;
    }
    return aKeys.every((key) => a[key] === b[key]);
};

const appendQuery = (baseUrl: string, query: string): string => {
    const separator = baseUrl.includes('?') ? '&' : '?';
    return `${baseUrl}${separator}${query}`;
};

const normalizeOverlayBounds = (
    bounds?: [number, number, number, number],
): [number, number, number, number] | undefined => {
    if (!Array.isArray(bounds) || bounds.length !== 4) {
        return undefined;
    }
    const [minLon, minLat, maxLon, maxLat] = bounds;
    return [minLon, minLat, maxLon, maxLat];
};

const buildWmsTileUrl = (overlay: OverlayEntry): string | null => {
    if (!overlay.url) {
        return null;
    }
    const layers = overlay.layers || DEFAULT_WMS_LAYER_ID;
    const version = overlay.wms_version || DEFAULT_WMS_VERSION;
    const exceptions = overlay.wms_exceptions || DEFAULT_WMS_EXCEPTIONS;
    const query = [
        'service=WMS',
        'request=GetMap',
        `layers=${encodeURIComponent(layers)}`,
        'styles=',
        'format=image/png',
        'transparent=true',
        `version=${encodeURIComponent(version)}`,
        'srs=EPSG:3857',
        `exceptions=${encodeURIComponent(exceptions)}`,
        'bbox={bbox-epsg-3857}',
        'width=256',
        'height=256',
    ].join('&');
    return appendQuery(overlay.url, query);
};

const buildWmtsTileUrl = (overlay: OverlayEntry): string | null => {
    if (!overlay.url) {
        return null;
    }
    const layerId = overlay.layer_id || overlay.layers || DEFAULT_WMS_LAYER_ID;
    const matrixSet = overlay.tile_matrix_set || DEFAULT_WMTS_MATRIX_SET;
    const format = overlay.wmts_format || DEFAULT_WMTS_FORMAT;
    const style = overlay.wmts_style ?? '';
    const query = [
        'service=WMTS',
        'request=GetTile',
        'version=1.0.0',
        `layer=${encodeURIComponent(layerId)}`,
        `style=${encodeURIComponent(style)}`,
        `tilematrixset=${encodeURIComponent(matrixSet)}`,
        `tilematrix=${matrixSet}:{z}`,
        'tilerow={y}',
        'tilecol={x}',
        `format=${encodeURIComponent(format)}`,
    ].join('&');
    return appendQuery(overlay.url, query);
};

const buildStyle = (mapSession?: MapSession): StyleSpecification => {
    const basemap = mapSession?.basemap;
    const baseTileUrl = basemap?.tile_url || DEFAULT_BASE_TILE_URL;
    return {
        version: 8,
        sources: {
            basemap: {
                type: 'raster',
                tiles: [baseTileUrl],
                tileSize: 256,
                attribution: basemap?.attribution || DEFAULT_BASE_ATTRIBUTION,
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
        const opacity = typeof overlay.default_opacity === 'number' ? overlay.default_opacity : DEFAULT_OVERLAY_OPACITY;
        const sourceBounds = normalizeOverlayBounds(overlay.bounds);

        if (overlay.type === 'tile' && overlay.url) {
            const rasterSource: {
                type: 'raster';
                tiles: string[];
                tileSize: number;
                bounds?: [number, number, number, number];
            } = {
                type: 'raster',
                tiles: [overlay.url],
                tileSize: 256,
            };
            if (sourceBounds) {
                rasterSource.bounds = sourceBounds;
            }
            map.addSource(sourceId, rasterSource);
            map.addLayer({
                id: layerId,
                source: sourceId,
                type: 'raster',
                paint: { 'raster-opacity': opacity },
            });
            return;
        }

        if (overlay.type === 'wms' && overlay.url) {
            const wmsTiles = buildWmsTileUrl(overlay);
            if (!wmsTiles) {
                return;
            }
            const rasterSource: {
                type: 'raster';
                tiles: string[];
                tileSize: number;
                bounds?: [number, number, number, number];
            } = {
                type: 'raster',
                tiles: [wmsTiles],
                tileSize: 256,
            };
            if (sourceBounds) {
                rasterSource.bounds = sourceBounds;
            }
            map.addSource(sourceId, rasterSource);
            map.addLayer({
                id: layerId,
                source: sourceId,
                type: 'raster',
                paint: { 'raster-opacity': opacity },
            });
            return;
        }

        if (overlay.type === 'wmts' && overlay.url) {
            const wmtsTiles = buildWmtsTileUrl(overlay);
            if (!wmtsTiles) {
                return;
            }
            const rasterSource: {
                type: 'raster';
                tiles: string[];
                tileSize: number;
                bounds?: [number, number, number, number];
            } = {
                type: 'raster',
                tiles: [wmtsTiles],
                tileSize: 256,
            };
            if (sourceBounds) {
                rasterSource.bounds = sourceBounds;
            }
            map.addSource(sourceId, rasterSource);
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
    initialOverlayVisibility = {},
    initialOverlayOpacity = {},
    onOverlayStateChange,
}) => {
    const mapContainerRef = useRef<HTMLDivElement | null>(null);
    const mapRef = useRef<Map | null>(null);
    const mapSession = payload?.map_session;
    const [overlayVisibility, setOverlayVisibility] = useState<Record<string, boolean>>(initialOverlayVisibility);
    const [overlayOpacity, setOverlayOpacity] = useState<Record<string, number>>(initialOverlayOpacity);
    const [restoreNotice, setRestoreNotice] = useState('');
    const hasCenter = useMemo(() => {
        return typeof mapSession?.center?.latitude === 'number' && typeof mapSession?.center?.longitude === 'number';
    }, [mapSession]);

    useEffect(() => {
        const overlays = mapSession?.overlays || [];
        const overlayIds = new Set(overlays.map((overlay) => overlay.id));
        const staleVisibilityKeys = Object.keys(initialOverlayVisibility).filter((key) => !overlayIds.has(key));
        const staleOpacityKeys = Object.keys(initialOverlayOpacity).filter((key) => !overlayIds.has(key));
        const staleIds = new Set([...staleVisibilityKeys, ...staleOpacityKeys]);
        if (staleIds.size > 0) {
            setRestoreNotice(
                `Some saved overlay preferences could not be restored (${staleIds.size} removed or unknown overlay id${staleIds.size === 1 ? '' : 's'}).`,
            );
        } else {
            setRestoreNotice('');
        }
        setOverlayVisibility((current) => {
            const next: Record<string, boolean> = {};
            overlays.forEach((overlay) => {
                next[overlay.id] = current[overlay.id] ?? initialOverlayVisibility[overlay.id] ?? true;
            });
            return recordBooleanEqual(current, next) ? current : next;
        });
        setOverlayOpacity((current) => {
            const next: Record<string, number> = {};
            overlays.forEach((overlay) => {
                const fallback = typeof overlay.default_opacity === 'number' ? overlay.default_opacity : DEFAULT_OVERLAY_OPACITY;
                next[overlay.id] = current[overlay.id] ?? initialOverlayOpacity[overlay.id] ?? fallback;
            });
            return recordNumberEqual(current, next) ? current : next;
        });
    }, [mapSession, initialOverlayVisibility, initialOverlayOpacity]);

    useEffect(() => {
        if (!onOverlayStateChange) {
            return;
        }
        onOverlayStateChange({ overlayVisibility, overlayOpacity });
    }, [overlayVisibility, overlayOpacity, onOverlayStateChange]);

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
            const opacityValue = overlayOpacity[overlay.id] ?? overlay.default_opacity ?? DEFAULT_OVERLAY_OPACITY;
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
        if (!payload || (!payload.satellite_imagery && !payload.map_session)) {
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
                                    value={Math.round((overlayOpacity[overlay.id] ?? overlay.default_opacity ?? DEFAULT_OVERLAY_OPACITY) * 100)}
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
                {!!restoreNotice && (
                    <div className="compliance-panel" role="status" aria-live="polite">
                        <p>{restoreNotice}</p>
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

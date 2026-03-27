import React from 'react';
import './MapPreview.css';
import { SearchResponsePayload } from '../types';

interface MapPreviewProps {
    payload?: SearchResponsePayload;
    isLoading: boolean;
    emptyMessage?: string;
}

const MapPreview: React.FC<MapPreviewProps> = ({
    payload,
    isLoading,
    emptyMessage = 'Run a search to display the map.',
}) => {
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

        const imagery = payload.satellite_imagery;

        if (imagery.map_html) {
            return (
                <iframe
                    title="Map Preview"
                    className="map-iframe"
                    srcDoc={imagery.map_html}
                    scrolling="no"
                />
            );
        }

        let imageSource = '';
        if (imagery.image_base64) {
            const mime = imagery.mime || imagery.format || 'image/png';
            const normalizedMime = mime.trim().toLowerCase().startsWith('image/')
                ? mime.trim().toLowerCase()
                : `image/${mime.trim().split('/').pop()}`;
            const normalizedPayload = imagery.image_base64.replace(/[\n\r]/g, '');
            imageSource = `data:${normalizedMime};base64,${normalizedPayload}`;
        } else if (imagery.image_url || imagery.wms_url) {
            imageSource = imagery.image_url || imagery.wms_url || '';
        }

        if (imageSource) {
            return <img src={imageSource} alt="Map Preview" className="map-image" />;
        }

        return <div className="empty-state">Unable to render map</div>;
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

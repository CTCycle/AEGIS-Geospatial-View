import React from 'react';
import { SearchResponsePayload } from '../types';
import './MapPreview.css';

interface MapPreviewProps {
    payload?: SearchResponsePayload;
    isLoading: boolean;
}

const MapPreview: React.FC<MapPreviewProps> = ({ payload, isLoading }) => {
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
            return <div className="empty-state">No map data available</div>;
        }

        const imagery = payload.satellite_imagery;

        // Check for HTML content (iframe)
        if (imagery.map_html) {
            return (
                <iframe
                    title="Map Preview"
                    className="map-iframe"
                    srcDoc={imagery.map_html}
                    style={{ border: 0 }}
                />
            );
        }

        // Check for Image content (Base64 or URL)
        let imageSource = '';
        if (imagery.image_base64) {
            const mime = imagery.mime || imagery.format || 'image/png';
            // Ensure mime type is valid
            const normalizedMime = mime.trim().toLowerCase().startsWith('image/')
                ? mime.trim().toLowerCase()
                : `image/${mime.trim().split('/').pop()}`;

            // Clean base64 string
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
        <div className="card map-preview-card">
            <div className="card-content">
                <h4 className="section-title">Map Preview</h4>
                <div className="map-canvas">
                    {renderContent()}
                </div>
            </div>
        </div>
    );
};

export default MapPreview;

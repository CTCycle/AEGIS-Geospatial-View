import React from 'react';

interface ManifestToolsPanelProps {
    onRebuild: () => void;
}

const ManifestToolsPanel: React.FC<ManifestToolsPanelProps> = ({ onRebuild }) => (
    <section className="manifest-tools-panel">
        <h3>Manifest Tools</h3>
        <button type="button" onClick={onRebuild}>Vectorize all available manifests</button>
        <p>Manifest explorer is read-only in this iteration.</p>
    </section>
);

export default ManifestToolsPanel;

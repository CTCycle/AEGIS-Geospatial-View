import React from 'react';

interface PanelHeaderProps {
    title: string;
    description: string;
}

const PanelHeader: React.FC<PanelHeaderProps> = ({ title, description }) => {
    return (
        <div>
            <h3 className="panel-title">{title}</h3>
            <p className="panel-description">{description}</p>
        </div>
    );
};

export default PanelHeader;

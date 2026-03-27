import React from 'react';

interface PanelHeaderProps {
    title: string;
    description: string;
    headingLevel?: 2 | 3;
}

const PanelHeader: React.FC<PanelHeaderProps> = ({ title, description, headingLevel = 3 }) => {
    const HeadingTag = headingLevel === 2 ? 'h2' : 'h3';

    return (
        <div>
            <HeadingTag className="panel-title">{title}</HeadingTag>
            <p className="panel-description">{description}</p>
        </div>
    );
};

export default PanelHeader;

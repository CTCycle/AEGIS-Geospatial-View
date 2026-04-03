import React from 'react';

interface ModelSearchBarProps {
    value: string;
    onChange: (value: string) => void;
}

const ModelSearchBar: React.FC<ModelSearchBarProps> = ({ value, onChange }) => (
    <input
        className="model-search-bar"
        placeholder="Search models"
        value={value}
        onChange={(event) => onChange(event.target.value)}
    />
);

export default ModelSearchBar;

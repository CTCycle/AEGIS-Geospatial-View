import React from 'react';

interface ModelFilterBarProps {
    providerFilter: string;
    providerOptions: Array<{ value: string; label: string }>;
    onProviderFilter: (value: string) => void;
}

const ModelFilterBar: React.FC<ModelFilterBarProps> = ({ providerFilter, providerOptions, onProviderFilter }) => (
    <select className="model-filter-bar" value={providerFilter} onChange={(event) => onProviderFilter(event.target.value)}>
        {providerOptions.map((option) => (
            <option key={option.value} value={option.value}>
                {option.label}
            </option>
        ))}
    </select>
);

export default ModelFilterBar;

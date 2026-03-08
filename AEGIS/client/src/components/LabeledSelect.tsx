import React from 'react';

interface SelectOption {
    value: string;
    label: string;
}

interface LabeledSelectProps {
    id: string;
    label: string;
    value: string;
    options: ReadonlyArray<SelectOption>;
    onChange: (value: string) => void;
    disabled?: boolean;
    wrapperClassName?: string;
    selectClassName?: string;
    helperText?: string;
}

const LabeledSelect: React.FC<LabeledSelectProps> = ({
    id,
    label,
    value,
    options,
    onChange,
    disabled = false,
    wrapperClassName = 'form-group',
    selectClassName,
    helperText,
}) => (
    <div className={wrapperClassName}>
        <label htmlFor={id}>{label}</label>
        <select
            id={id}
            value={value}
            onChange={(event) => onChange(event.target.value)}
            disabled={disabled}
            className={selectClassName}
        >
            {options.map((option) => (
                <option key={option.value} value={option.value}>
                    {option.label}
                </option>
            ))}
        </select>
        {helperText && <p className="helper-text">{helperText}</p>}
    </div>
);

export default LabeledSelect;

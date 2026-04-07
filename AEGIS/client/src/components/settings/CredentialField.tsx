interface CredentialFieldProps {
    label: string;
    configured: boolean;
    placeholder: string;
    value: string;
    onChange: (value: string) => void;
}

function CredentialField({ label, configured, placeholder, value, onChange }: CredentialFieldProps) {
    return (
        <label>
            {label} {configured ? '(Configured)' : '(Not configured)'}
            <input
                type="password"
                value={value}
                onChange={(event) => onChange(event.target.value)}
                placeholder={placeholder}
            />
        </label>
    );
}

export default CredentialField;

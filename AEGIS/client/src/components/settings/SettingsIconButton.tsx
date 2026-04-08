import { ReactNode } from 'react';

interface SettingsIconButtonProps {
    ariaLabel: string;
    title: string;
    icon: ReactNode;
    onClick: () => void;
}

function SettingsIconButton({ ariaLabel, title, icon, onClick }: SettingsIconButtonProps) {
    return (
        <button
            type="button"
            className="settings-icon-button"
            onClick={onClick}
            aria-label={ariaLabel}
            title={title}
        >
            <span className="settings-icon-button__glyph" aria-hidden="true">{icon}</span>
        </button>
    );
}

export default SettingsIconButton;

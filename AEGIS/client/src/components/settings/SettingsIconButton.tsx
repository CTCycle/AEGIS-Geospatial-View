interface SettingsIconButtonProps {
    ariaLabel: string;
    title: string;
    glyph: string;
    onClick: () => void;
}

function SettingsIconButton({ ariaLabel, title, glyph, onClick }: SettingsIconButtonProps) {
    return (
        <button
            type="button"
            className="settings-icon-button"
            onClick={onClick}
            aria-label={ariaLabel}
            title={title}
        >
            <span className="settings-icon-button__glyph" aria-hidden="true">{glyph}</span>
        </button>
    );
}

export default SettingsIconButton;

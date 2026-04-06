import { ReactNode } from 'react';

interface SettingsModalProps {
    title: string;
    ariaLabel: string;
    onClose: () => void;
    footer?: ReactNode;
    footerClassName?: string;
    children: ReactNode;
}

function SettingsModal({ title, ariaLabel, onClose, footer, footerClassName, children }: SettingsModalProps) {
    return (
        <div className="settings-modal-backdrop" role="presentation" onClick={onClose}>
            <section
                className="settings-modal"
                role="dialog"
                aria-modal="true"
                aria-label={ariaLabel}
                onClick={(event) => event.stopPropagation()}
            >
                <header className="settings-modal__header">
                    <h2>{title}</h2>
                    <button type="button" className="settings-modal__close" onClick={onClose}>Close</button>
                </header>
                <div className="settings-modal__body">{children}</div>
                {footer && (
                    <footer className={footerClassName ?? 'settings-modal__footer'}>
                        {footer}
                    </footer>
                )}
            </section>
        </div>
    );
}

export default SettingsModal;

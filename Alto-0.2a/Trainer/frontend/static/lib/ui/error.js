// lib/ui/error.js - Custom error modal that does NOT close parent modals
import { modal } from './modal.js';
import { dom } from '../core/dom.js';

let currentErrorModalId = null;

export const error = {
    /**
     * Show an error modal that does NOT close any existing modals.
     * @param {string} message - The error message.
     * @param {Object} options - Optional: { title }
     */
    alert(message, options = {}) {
        console.error('[Error Alert]', message);
        
        // Close any previous error modal to avoid stacking
        if (currentErrorModalId) {
            modal.close(currentErrorModalId);
            currentErrorModalId = null;
        }

        const title = options.title || 'Error';
        const content = dom.createElement('div', { class: 'error-alert-content' }, [
            dom.createElement('p', {}, [message])
        ]);

        const errorModalId = modal.show({
            title: title,
            content: content,
            actions: [
                {
                    label: 'OK',
                    variant: 'save',
                    close: false,   // Do NOT auto‑close – we'll close manually
                    onClick: () => {
                        if (currentErrorModalId) {
                            modal.close(currentErrorModalId);
                            currentErrorModalId = null;
                        }
                    }
                }
            ],
            size: 'small',
            closable: false,       // No X button
            modalClass: 'error-modal'
        });
        currentErrorModalId = errorModalId;
    },

    installGlobalHandler() {
        window.addEventListener('unhandledrejection', (event) => {
            const message = event.reason?.message || String(event.reason);
            this.alert(`Unhandled error: ${message}`);
            event.preventDefault();
        });
    }
};
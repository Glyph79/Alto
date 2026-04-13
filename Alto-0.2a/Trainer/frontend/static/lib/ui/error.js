// lib/ui/error.js - Custom error modal that does NOT close parent modals
import { modal } from './modal.js';
import { dom } from '../core/dom.js';

let currentErrorModalId = null;

export const error = {
    /**
     * Show an error modal that does NOT close any existing modals.
     * @param {string} message - The error message.
     * @param {Object} options - Optional: { title }
     * @returns {Promise<void>} Resolves when the error modal is closed.
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

        return new Promise((resolve) => {
            let okButton = null;
            const errorModalId = modal.show({
                title: title,
                content: content,
                actions: [
                    {
                        label: 'OK',
                        variant: 'save',
                        close: false,
                        onClick: () => {
                            if (currentErrorModalId) {
                                modal.close(currentErrorModalId);
                                currentErrorModalId = null;
                            }
                            resolve();
                        }
                    }
                ],
                size: 'small',
                closable: false,
                modalClass: 'error-modal'
            });
            currentErrorModalId = errorModalId;
            
            // After modal is rendered, focus the OK button and add Enter key handler
            setTimeout(() => {
                const modalEl = document.getElementById(errorModalId);
                if (modalEl) {
                    okButton = modalEl.querySelector('.modal-actions .save');
                    if (okButton) {
                        okButton.focus();
                        // Add keydown listener to the modal content to catch Enter
                        const modalContent = modalEl.querySelector('.modal-content');
                        if (modalContent) {
                            modalContent.addEventListener('keydown', (e) => {
                                if (e.key === 'Enter') {
                                    e.preventDefault();
                                    if (okButton && !okButton.disabled) okButton.click();
                                }
                            });
                        }
                    }
                }
            }, 50);
        });
    },

    installGlobalHandler() {
        window.addEventListener('unhandledrejection', (event) => {
            const message = event.reason?.message || String(event.reason);
            this.alert(`Unhandled error: ${message}`);
            event.preventDefault();
        });
    }
};
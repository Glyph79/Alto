// lib/ui/loading.js - Loading indicators
import { dom } from '../core/dom.js';

export const loading = {
    inline(container, text = 'Loading', delayMs = 300) {
        let timeout = null;
        let loadingElement = null;
        const clear = () => {
            if (timeout) clearTimeout(timeout);
            if (loadingElement && loadingElement.parentNode) loadingElement.remove();
        };
        timeout = setTimeout(() => {
            loadingElement = dom.createElement('div', { class: 'inline-loading' }, [
                dom.createElement('div', { class: 'inline-spinner' }, []),
                dom.createElement('span', {}, [`${text}...`]),
            ]);
            container.appendChild(loadingElement);
        }, delayMs);
        return { clear };
    },

    overlay(container, text = 'Loading') {
        const overlay = dom.createElement('div', { class: 'loading-overlay' }, [
            dom.createElement('div', { class: 'loading-spinner' }, []),
            dom.createElement('div', { class: 'loading-text' }, [text]),
        ]);
        container.style.position = 'relative';
        container.appendChild(overlay);
        return {
            clear: () => {
                if (overlay.parentNode) overlay.remove();
                container.style.position = '';
            },
        };
    },

    button(buttonElement, text = 'Saving...') {
        const originalText = buttonElement.textContent;
        const originalDisabled = buttonElement.disabled;
        buttonElement.disabled = true;
        buttonElement.textContent = text;
        return {
            restore: () => {
                buttonElement.disabled = originalDisabled;
                buttonElement.textContent = originalText;
            },
        };
    },
};
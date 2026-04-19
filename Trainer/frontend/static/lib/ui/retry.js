// lib/ui/retry.js - Retry UI components and operation retry
import { dom } from '../core/dom.js';

export const RETRY_CONFIG = {
    maxAttempts: 3,
    baseDelayMs: 200,
    backoffFactor: 2,
};

export async function retryOperation(operation, options = {}) {
    const config = { ...RETRY_CONFIG, ...options };
    let lastError;
    for (let attempt = 1; attempt <= config.maxAttempts; attempt++) {
        try {
            return await operation();
        } catch (err) {
            lastError = err;
            if (attempt === config.maxAttempts) break;
            const delay = config.baseDelayMs * Math.pow(config.backoffFactor, attempt - 1);
            await new Promise(resolve => setTimeout(resolve, delay));
        }
    }
    throw lastError;
}

export const retryUI = {
    show(container, message, onRetry, options = {}) {
        this.clear(container);
        const wrapper = dom.createElement('div', { class: 'retry-error' }, [
            dom.createElement('div', { class: 'error-icon' }, ['⚠️']),
            dom.createElement('div', { class: 'error-message' }, [message]),
            dom.createElement('button', { class: 'retry-btn' }, ['Retry']),
        ]);
        const btn = wrapper.querySelector('.retry-btn');
        btn.addEventListener('click', async () => {
            btn.disabled = true;
            btn.textContent = 'Retrying...';
            try {
                await onRetry();
                wrapper.remove();
            } catch (err) {
                btn.disabled = false;
                btn.textContent = 'Retry';
                const msgDiv = wrapper.querySelector('.error-message');
                msgDiv.textContent = `Failed: ${err.message}`;
            }
        });
        container.appendChild(wrapper);
        return wrapper;
    },

    showInline(listElement, itemType, onRetry) {
        listElement.innerHTML = '';
        const li = dom.createElement('li', { class: 'retry-list-item' }, [
            dom.createElement('span', { style: 'color:#ffaa66;' }, [`⚠️ Failed to load ${itemType}.`]),
            dom.createElement('button', { class: 'retry-list-btn' }, ['Retry']),
        ]);
        const btn = li.querySelector('.retry-list-btn');
        btn.addEventListener('click', async () => {
            btn.disabled = true;
            btn.textContent = '...';
            try {
                await onRetry();
            } catch (err) {
                btn.disabled = false;
                btn.textContent = 'Retry';
                const span = li.querySelector('span');
                span.textContent = `⚠️ Failed: ${err.message}`;
            }
        });
        listElement.appendChild(li);
    },

    clear(container) {
        const existing = container.querySelector('.retry-error, .simple-retry, .retry-list-item');
        if (existing) existing.remove();
    },
};
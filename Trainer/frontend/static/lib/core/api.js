// lib/core/api.js - Unified API client with retry logic
import { retryOperation } from '../ui/retry.js';

const DEFAULT_RETRY_OPTIONS = { maxAttempts: 3, baseDelayMs: 200 };

async function request(url, options = {}, retryOpts = DEFAULT_RETRY_OPTIONS) {
    const fetchWithRetry = async () => {
        const response = await fetch(url, options);
        if (!response.ok) {
            let errorMessage;
            try {
                const err = await response.json();
                errorMessage = err.error || `HTTP ${response.status}`;
            } catch {
                errorMessage = `HTTP ${response.status}`;
            }
            throw new Error(errorMessage);
        }
        return response.json();
    };
    return retryOperation(fetchWithRetry, retryOpts);
}

export const api = {
    get(url, options) {
        return request(url, { method: 'GET', ...options });
    },
    post(url, data, options) {
        return request(url, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data),
            ...options,
        });
    },
    put(url, data, options) {
        return request(url, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data),
            ...options,
        });
    },
    delete(url, options) {
        return request(url, { method: 'DELETE', ...options });
    },
};
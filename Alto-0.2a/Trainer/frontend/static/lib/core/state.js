// lib/core/state.js - Reactive state with subscriptions
import { events } from './events.js';

const store = {
    currentModel: null,
    groups: [],
    sections: [],
    topics: [],
    variants: [],
    fallbacks: [],
};

const subscribers = new Map();

export const state = {
    get(key) {
        return store[key];
    },

    set(key, value) {
        const oldValue = store[key];
        store[key] = value;
        if (subscribers.has(key)) {
            subscribers.get(key).forEach(cb => cb(value, oldValue));
        }
        events.emit(`state:${key}:changed`, { newValue: value, oldValue });
        events.emit('state:changed', { key, newValue: value, oldValue });
    },

    subscribe(key, callback) {
        if (!subscribers.has(key)) subscribers.set(key, []);
        subscribers.get(key).push(callback);
        return () => {
            const arr = subscribers.get(key);
            if (arr) {
                const idx = arr.indexOf(callback);
                if (idx !== -1) arr.splice(idx, 1);
            }
        };
    },

    async setCurrentModel(modelName) {
        if (this.get('currentModel') === modelName) return;
        this.set('currentModel', modelName);
        if (modelName) {
            await Promise.all([
                window.managers?.groups?.load(),
                window.managers?.sections?.load(),
                window.managers?.topics?.load(),
                window.managers?.variants?.load(),
                window.managers?.fallbacks?.load(),
            ]);
        }
    },
};
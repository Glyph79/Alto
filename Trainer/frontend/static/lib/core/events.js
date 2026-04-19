// lib/core/events.js - Simple pub/sub event bus
const listeners = new Map();

export const events = {
    on(event, callback) {
        if (!listeners.has(event)) listeners.set(event, []);
        listeners.get(event).push(callback);
    },

    off(event, callback) {
        if (!listeners.has(event)) return;
        const callbacks = listeners.get(event);
        const index = callbacks.indexOf(callback);
        if (index !== -1) callbacks.splice(index, 1);
        if (callbacks.length === 0) listeners.delete(event);
    },

    emit(event, data) {
        if (!listeners.has(event)) return;
        listeners.get(event).forEach(cb => cb(data));
    },

    once(event, callback) {
        const wrapper = (data) => {
            callback(data);
            this.off(event, wrapper);
        };
        this.on(event, wrapper);
    },
};

// Default export for compatibility
export default events;
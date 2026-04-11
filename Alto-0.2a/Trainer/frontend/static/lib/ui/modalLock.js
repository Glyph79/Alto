// lib/ui/modalLock.js - Prevent duplicate modals of the same type
const locks = new Map();

export const modalLock = {
    /**
     * Attempt to acquire a lock for a modal type.
     * @param {string} type - Unique identifier for the modal (e.g., 'groupModal', 'topicModal')
     * @returns {boolean} - True if lock was acquired, false if already locked.
     */
    lock(type) {
        if (locks.has(type) && locks.get(type) === true) {
            return false;
        }
        locks.set(type, true);
        return true;
    },

    /**
     * Release the lock for a modal type.
     * @param {string} type
     */
    unlock(type) {
        locks.delete(type);
    },

    /**
     * Check if a modal type is currently locked.
     * @param {string} type
     * @returns {boolean}
     */
    isLocked(type) {
        return locks.has(type) && locks.get(type) === true;
    },

    /**
     * Execute a function with a lock, automatically releasing it afterward.
     * @param {string} type
     * @param {Function} fn - Async function to execute
     * @returns {Promise<any>} - Result of fn, or throws if already locked.
     */
    async runWithLock(type, fn) {
        if (!this.lock(type)) {
            // Silently ignore duplicate open
            return null;
        }
        try {
            return await fn();
        } finally {
            this.unlock(type);
        }
    }
};
// Unified search, filter, and sort manager for all tabs.
window.SearchManager = class SearchManager {
    constructor(options) {
        this.container = document.getElementById(options.containerId);
        this.grid = this.container.querySelector('.grid') || this.container;
        this.cardArray = options.cardArray || [];
        this.searchInput = options.searchInputId ? document.getElementById(options.searchInputId) : null;
        this.searchFields = options.searchFields || [];
        this.customSearchFn = options.customSearchFn || null;
        this.filterSelectors = options.filterSelectors || {};
        this.sortSelectors = options.sortSelectors || {};
        this.defaultSort = options.defaultSort || null;
        this.onUpdate = options.onUpdate || null;
        this.debounceTimer = null;
        this.debounceDelay = 300;

        this.currentFilters = {};
        this.currentSort = this.defaultSort;

        // Store bound event handlers for cleanup
        this._boundInputHandler = null;
        this._boundChangeHandlers = {};

        this._init();
    }

    _init() {
        for (let [id, filterFn] of Object.entries(this.filterSelectors)) {
            const el = document.getElementById(id);
            if (el) {
                this.currentFilters[id] = el.value;
                const handler = () => {
                    this.currentFilters[id] = el.value;
                    this.update();
                };
                el.addEventListener('change', handler);
                this._boundChangeHandlers[id] = handler;
            } else {
                console.warn(`Filter element with id "${id}" not found.`);
            }
        }

        if (this.searchInput) {
            this._boundInputHandler = () => {
                if (this.debounceTimer) clearTimeout(this.debounceTimer);
                this.debounceTimer = setTimeout(() => this.update(), this.debounceDelay);
            };
            this.searchInput.addEventListener('input', this._boundInputHandler);
        }

        for (let [id, sortFn] of Object.entries(this.sortSelectors)) {
            const el = document.getElementById(id);
            if (el) {
                this.currentSort = el.value;
                const handler = () => {
                    this.currentSort = el.value;
                    this.update();
                };
                el.addEventListener('change', handler);
                this._boundChangeHandlers[id] = handler;
                break;
            }
        }

        this.update();
    }

    update() {
        const searchTerm = this.searchInput ? this.searchInput.value.toLowerCase() : '';

        const filterFn = (item) => {
            if (searchTerm) {
                if (this.customSearchFn) {
                    if (!this.customSearchFn(item, searchTerm)) return false;
                } else {
                    let found = false;
                    for (let field of this.searchFields) {
                        const val = item[field];
                        if (val && String(val).toLowerCase().includes(searchTerm)) {
                            found = true;
                            break;
                        }
                    }
                    if (!found) return false;
                }
            }

            for (let [id, filterFn] of Object.entries(this.filterSelectors)) {
                const value = this.currentFilters[id];
                if (!filterFn(item, value)) return false;
            }
            return true;
        };

        let sortFn = null;
        if (this.currentSort && this.sortSelectors[this.currentSort]) {
            sortFn = this.sortSelectors[this.currentSort];
        }

        window.filterCards(this.cardArray, filterFn, sortFn, this.grid);

        if (this.onUpdate) this.onUpdate();
    }

    setCardArray(newCardArray) {
        this.cardArray = newCardArray;
        this.update();
    }

    refresh() {
        this.update();
    }

    destroy() {
        // Remove event listeners
        if (this.searchInput && this._boundInputHandler) {
            this.searchInput.removeEventListener('input', this._boundInputHandler);
        }
        for (let [id, handler] of Object.entries(this._boundChangeHandlers)) {
            const el = document.getElementById(id);
            if (el) {
                el.removeEventListener('change', handler);
            }
        }
        // Clear references
        this.cardArray = [];
        this.grid = null;
        this.searchInput = null;
        this.container = null;
    }
};
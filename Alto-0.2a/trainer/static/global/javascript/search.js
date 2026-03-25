// Unified search, filter, and sort manager for all tabs.
window.SearchManager = class SearchManager {
    /**
     * @param {Object} options
     * @param {string} options.containerId - ID of the container that holds the grid.
     * @param {Array} options.cardArray - Array of { element, item }.
     * @param {string} options.searchInputId - ID of the search input.
     * @param {Array} options.searchFields - Fields of item to search (used if no customSearchFn).
     * @param {Function} options.customSearchFn - Optional custom search function (item, term) => boolean.
     * @param {Object} options.filterSelectors - Map of select element ID -> filter function (item, value) => boolean.
     * @param {Object} options.sortSelectors - Map of sort value -> compare function (a, b) => number.
     * @param {string} options.defaultSort - Initial sort value.
     * @param {Function} options.onUpdate - Optional callback after update.
     */
    constructor(options) {
        this.container = document.getElementById(options.containerId);
        // The grid inside container is expected to have class "grid"
        this.grid = this.container.querySelector('.grid') || this.container;
        this.cardArray = options.cardArray || [];
        this.searchInput = options.searchInputId ? document.getElementById(options.searchInputId) : null;
        this.searchFields = options.searchFields || [];
        this.customSearchFn = options.customSearchFn || null;
        this.filterSelectors = options.filterSelectors || {};
        this.sortSelectors = options.sortSelectors || {};
        this.defaultSort = options.defaultSort || null;
        this.onUpdate = options.onUpdate || null;

        this.currentFilters = {};
        this.currentSort = this.defaultSort;

        this._init();
    }

    _init() {
        // Read initial values from filter dropdowns and attach listeners
        for (let [id, filterFn] of Object.entries(this.filterSelectors)) {
            const el = document.getElementById(id);
            if (el) {
                this.currentFilters[id] = el.value;
                el.addEventListener('change', () => {
                    this.currentFilters[id] = el.value;
                    this.update();
                });
            } else {
                console.warn(`Filter element with id "${id}" not found.`);
            }
        }

        // Search input listener
        if (this.searchInput) {
            this.searchInput.addEventListener('input', () => this.update());
        }

        // Sort dropdown listener (assume only one)
        for (let [id, sortFn] of Object.entries(this.sortSelectors)) {
            const el = document.getElementById(id);
            if (el) {
                this.currentSort = el.value;
                el.addEventListener('change', () => {
                    this.currentSort = el.value;
                    this.update();
                });
                break; // only one sort dropdown per manager
            }
        }

        this.update();
    }

    /**
     * Update the card display based on current filters and sort.
     */
    update() {
        const searchTerm = this.searchInput ? this.searchInput.value.toLowerCase() : '';

        // Combined filter function
        const filterFn = (item) => {
            // Search
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

            // Apply each filter selector
            for (let [id, filterFn] of Object.entries(this.filterSelectors)) {
                const value = this.currentFilters[id];
                if (!filterFn(item, value)) return false;
            }
            return true;
        };

        // Sort function
        let sortFn = null;
        if (this.currentSort && this.sortSelectors[this.currentSort]) {
            sortFn = this.sortSelectors[this.currentSort];
        }

        // Use the global filterCards utility (from ui.js) to reorder and hide
        window.filterCards(this.cardArray, filterFn, sortFn, this.grid);

        if (this.onUpdate) this.onUpdate();
    }

    /**
     * Replace the card array (e.g., after loading new data) and refresh.
     * @param {Array} newCardArray
     */
    setCardArray(newCardArray) {
        this.cardArray = newCardArray;
        this.update();
    }

    /**
     * Manually trigger an update (e.g., after external changes to items).
     */
    refresh() {
        this.update();
    }
};
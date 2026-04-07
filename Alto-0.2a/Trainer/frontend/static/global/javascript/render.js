// render.js - Universal Grid Renderer for Alto Trainer
// Handles: rendering cards, search, filter, sort, empty states, event delegation.

class GridRenderer {
    /**
     * @param {Object} config
     * @param {string} config.containerId - ID of the grid container element
     * @param {Array} config.items - Array of data items
     * @param {function} config.renderItem - (item, index) => HTML string for one card
     * @param {Object} config.options
     * @param {string} [config.options.searchInputId] - ID of search input
     * @param {string[]} [config.options.searchFields] - Item fields to search against
     * @param {Object} [config.options.filterSelectors] - Map of select ID -> filter function (item, value) => bool
     * @param {Object} [config.options.sortSelectors] - Map of select ID -> sort function (a, b) => number
     * @param {string} [config.options.defaultSort] - Default sort selector ID
     * @param {string} [config.options.gridClass] - CSS class for grid wrapper (default 'grid')
     * @param {string} [config.options.emptyStateHtml] - HTML for empty state (optional)
     * @param {function} [config.options.onCardClick] - (item, index, event) => void
     * @param {function} [config.options.onCardEdit] - (item, index, event) => void
     * @param {function} [config.options.onCardDelete] - (item, index, event) => void
     */
    constructor(config) {
        this.container = document.getElementById(config.containerId);
        if (!this.container) throw new Error(`Container #${config.containerId} not found`);
        this.items = config.items || [];
        this.renderItem = config.renderItem;
        this.options = config.options || {};
        this.gridClass = this.options.gridClass || 'grid';
        this.emptyStateHtml = this.options.emptyStateHtml || '<div class="empty-state">No items to display.</div>';
        this.onCardClick = this.options.onCardClick || null;
        this.onCardEdit = this.options.onCardEdit || null;
        this.onCardDelete = this.options.onCardDelete || null;

        // Search
        this.searchInput = this.options.searchInputId ? document.getElementById(this.options.searchInputId) : null;
        this.searchFields = this.options.searchFields || [];
        this._searchTerm = '';

        // Filters
        this.filterSelectors = this.options.filterSelectors || {};
        this._currentFilters = {};
        for (let id in this.filterSelectors) {
            const el = document.getElementById(id);
            if (el) this._currentFilters[id] = el.value;
        }

        // Sorting
        this.sortSelectors = this.options.sortSelectors || {};
        this.defaultSort = this.options.defaultSort;
        this._currentSort = this.defaultSort;

        // State
        this._debounceTimer = null;
        this._boundHandlers = {};
        this._cardClickHandler = null;

        this._init();
    }

    _init() {
        // Bind filter change handlers
        for (let id in this.filterSelectors) {
            const el = document.getElementById(id);
            if (el) {
                const handler = () => {
                    this._currentFilters[id] = el.value;
                    this._update();
                };
                el.addEventListener('change', handler);
                this._boundHandlers[`filter_${id}`] = handler;
            }
        }

        // Bind sort change handlers
        for (let id in this.sortSelectors) {
            const el = document.getElementById(id);
            if (el) {
                const handler = () => {
                    this._currentSort = el.value;
                    this._update();
                };
                el.addEventListener('change', handler);
                this._boundHandlers[`sort_${id}`] = handler;
            }
        }

        // Bind search input
        if (this.searchInput) {
            const handler = () => {
                if (this._debounceTimer) clearTimeout(this._debounceTimer);
                this._debounceTimer = setTimeout(() => {
                    this._searchTerm = this.searchInput.value.toLowerCase();
                    this._update();
                }, 300);
            };
            this.searchInput.addEventListener('input', handler);
            this._boundHandlers.search = handler;
        }

        // Initial render
        this._update();
    }

    setItems(newItems) {
        this.items = newItems;
        this._update();
    }

    refresh() {
        this._update();
    }

    _filterItem(item) {
        // Search
        if (this._searchTerm) {
            let found = false;
            for (let field of this.searchFields) {
                const val = item[field];
                if (val && String(val).toLowerCase().includes(this._searchTerm)) {
                    found = true;
                    break;
                }
            }
            if (!found) return false;
        }

        // Custom filters
        for (let id in this.filterSelectors) {
            const filterFn = this.filterSelectors[id];
            const value = this._currentFilters[id];
            if (!filterFn(item, value)) return false;
        }
        return true;
    }

    _sortItems(items) {
        if (!this._currentSort || !this.sortSelectors[this._currentSort]) return items;
        const sortFn = this.sortSelectors[this._currentSort];
        return [...items].sort(sortFn);
    }

    _update() {
        // Filter
        let filtered = this.items.filter(item => this._filterItem(item));
        // Sort
        filtered = this._sortItems(filtered);

        // Build HTML
        if (filtered.length === 0) {
            this.container.innerHTML = this.emptyStateHtml;
            return;
        }

        let gridHtml = `<div class="${this.gridClass}">`;
        filtered.forEach((item, idx) => {
            gridHtml += this.renderItem(item, idx);
        });
        gridHtml += '</div>';
        this.container.innerHTML = gridHtml;

        // Attach event delegation
        const gridDiv = this.container.querySelector(`.${this.gridClass}`);
        if (!gridDiv) return;

        if (this._cardClickHandler) {
            gridDiv.removeEventListener('click', this._cardClickHandler);
        }
        this._cardClickHandler = (e) => {
            const card = e.target.closest('[data-card-index]');
            if (!card) return;
            const index = parseInt(card.dataset.cardIndex, 10);
            const item = filtered[index];
            if (!item) return;

            if (e.target.closest('.card-edit') && this.onCardEdit) {
                this.onCardEdit(item, index, e);
            } else if (e.target.closest('.card-delete') && this.onCardDelete) {
                this.onCardDelete(item, index, e);
            } else if (this.onCardClick) {
                this.onCardClick(item, index, e);
            }
        };
        gridDiv.addEventListener('click', this._cardClickHandler);
    }

    destroy() {
        // Remove all event listeners
        for (let id in this._boundHandlers) {
            if (id.startsWith('filter_')) {
                const elId = id.replace('filter_', '');
                const el = document.getElementById(elId);
                if (el) el.removeEventListener('change', this._boundHandlers[id]);
            } else if (id.startsWith('sort_')) {
                const elId = id.replace('sort_', '');
                const el = document.getElementById(elId);
                if (el) el.removeEventListener('change', this._boundHandlers[id]);
            } else if (id === 'search' && this.searchInput) {
                this.searchInput.removeEventListener('input', this._boundHandlers[id]);
            }
        }
        if (this._cardClickHandler && this.container.querySelector(`.${this.gridClass}`)) {
            this.container.querySelector(`.${this.gridClass}`).removeEventListener('click', this._cardClickHandler);
        }
        this.container.innerHTML = '';
    }
}

// Make it globally available
window.GridRenderer = GridRenderer;
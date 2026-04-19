// GridRenderer.js - Universal Grid Renderer
class GridRenderer {
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

        this.searchInput = this.options.searchInputId ? document.getElementById(this.options.searchInputId) : null;
        this.searchFields = this.options.searchFields || [];
        this._searchTerm = '';

        this.filterSelectors = this.options.filterSelectors || {};
        this._currentFilters = {};
        for (let id in this.filterSelectors) {
            const el = document.getElementById(id);
            if (el) this._currentFilters[id] = el.value;
        }

        this.sortSelectors = this.options.sortSelectors || {};
        this.defaultSort = this.options.defaultSort;
        this._currentSort = this.defaultSort;

        this._debounceTimer = null;
        this._boundHandlers = {};
        this._cardClickHandler = null;

        this._init();
    }

    _init() {
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
        let filtered = this.items.filter(item => this._filterItem(item));
        filtered = this._sortItems(filtered);

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

export default GridRenderer;
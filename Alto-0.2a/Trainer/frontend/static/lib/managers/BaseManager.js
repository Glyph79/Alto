// lib/managers/BaseManager.js - Abstract base with pagination and 100-item cap
import { state } from '../core/state.js';
import events from '../core/events.js';
import { api } from '../core/api.js';
import { modal } from '../ui/modal.js';
import { dom } from '../core/dom.js';
import { error } from '../ui/error.js';
import { loading } from '../ui/loading.js';

export class BaseManager {
    constructor(featureName, config) {
        this.feature = featureName;
        this.config = config;
        this.grid = null;
        this.originalData = [];      // all items loaded so far (capped at 100)
        this.displayData = [];
        this.isLoaded = false;
        
        // Pagination state
        this.totalCount = 0;
        this.hasMore = true;
        this.limit = 20;
        this.offset = 0;
        this.maxItems = 100;
        this.isLoadingMore = false;
        
        // Search/sort/filter
        this._searchTerm = '';
        this._sortKey = config.defaultSort || Object.keys(config.sortSelectors)[0];
        
        events.on('state:currentModel:changed', async ({ newValue }) => {
            if (newValue) await this.load(true);
            else this.clear();
        });
    }
    
    getItems() { throw new Error('getItems() must be implemented'); }
    renderItem(item, index) { throw new Error('renderItem() must be implemented'); }
    
    // Override to return the correct API endpoint
    getApiPath() {
        const path = this.config.apiPath;
        return typeof path === 'function' ? path() : path;
    }
    
    // Override to specify the key in the response that holds the array
    get itemsKey() { return this.config.itemsKey || this.feature; }
    
    async fetchPage(offset, limit) {
        const url = `${this.getApiPath()}?limit=${limit}&offset=${offset}`;
        const response = await api.get(url);
        return {
            items: response[this.itemsKey],
            total: response.total
        };
    }
    
    async load(reset = true) {
        if (reset) {
            this.originalData = [];
            this.offset = 0;
            this.hasMore = true;
            this.totalCount = 0;
        }
        if (!state.get('currentModel')) {
            this.clear();
            return;
        }
        
        const container = document.getElementById(this.config.gridContainerId);
        if (!container) return;
        
        if (reset) this.showLoadingIndicator(container);
        
        try {
            const { items, total } = await this.fetchPage(this.offset, this.limit);
            this.totalCount = total;
            
            if (reset) {
                this.originalData = items;
            } else {
                this.originalData.push(...items);
            }
            
            // Enforce 100-item cap: remove oldest if exceeded
            if (this.originalData.length > this.maxItems) {
                const removeCount = this.originalData.length - this.maxItems;
                this.originalData.splice(0, removeCount);
                // Adjust offset to reflect new start? For simplicity, we keep offset as is,
                // but the user might lose the ability to load more exactly. However, they
                // can still load more up to total count, but the client cache stays within limit.
                // We'll keep hasMore based on server total and client count.
            }
            
            this.offset += items.length;
            this.hasMore = this.offset < this.totalCount && this.originalData.length < this.maxItems;
            
            this._applyFiltersAndSort();
            
            if (!this.grid) {
                this.initGrid(this.config.gridContainerId);
            } else {
                this.grid.setItems(this.displayData);
            }
            this.enableControls(true);
            this._updateEmptyState();
            this.updateLoadMoreButton();
        } catch (err) {
            // Suppress old schema error popup
            if (err.message && err.message.includes("uses an old schema that is no longer supported")) {
                console.warn("Skipping error popup for unsupported model schema:", err.message);
                this.enableControls(false);
            } else {
                error.alert(`Failed to load ${this.feature}: ${err.message}`);
                this.enableControls(false);
            }
        } finally {
            if (reset) this.hideLoadingIndicator();
        }
    }
    
    async loadMore() {
        if (this.isLoadingMore || !this.hasMore) return;
        this.isLoadingMore = true;
        this.showLoadMoreLoading();
        await this.load(false);
        this.isLoadingMore = false;
        this.hideLoadMoreLoading();
    }
    
    updateLoadMoreButton() {
        const container = document.getElementById(this.config.gridContainerId);
        if (!container) return;
        let loadMoreBtn = container.querySelector('.load-more-btn');
        if (this.hasMore && this.originalData.length < this.maxItems) {
            if (!loadMoreBtn) {
                loadMoreBtn = dom.createElement('button', { class: 'load-more-btn' }, ['Load More']);
                loadMoreBtn.addEventListener('click', () => this.loadMore());
                container.appendChild(loadMoreBtn);
            }
        } else if (loadMoreBtn) {
            loadMoreBtn.remove();
        }
        let maxMsg = container.querySelector('.max-items-msg');
        if (this.originalData.length >= this.maxItems && this.hasMore) {
            if (!maxMsg) {
                maxMsg = dom.createElement('div', { class: 'max-items-msg' }, 
                    [`Showing first ${this.maxItems} items. Refine search to see more.`]);
                container.appendChild(maxMsg);
            }
        } else if (maxMsg) {
            maxMsg.remove();
        }
    }
    
    showLoadMoreLoading() {
        const container = document.getElementById(this.config.gridContainerId);
        if (!container) return;
        let loader = container.querySelector('.load-more-loader');
        if (!loader) {
            loader = dom.createElement('div', { class: 'load-more-loader' }, ['Loading more...']);
            container.appendChild(loader);
        }
    }
    
    hideLoadMoreLoading() {
        const container = document.getElementById(this.config.gridContainerId);
        if (container) {
            const loader = container.querySelector('.load-more-loader');
            if (loader) loader.remove();
        }
    }
    
    showLoadingIndicator(container) {
        // Already handled by grid or we can add a global loader
        const existing = container.querySelector('.global-loading');
        if (!existing) {
            const loader = dom.createElement('div', { class: 'global-loading' }, ['Loading...']);
            container.appendChild(loader);
        }
    }
    
    hideLoadingIndicator() {
        const container = document.getElementById(this.config.gridContainerId);
        if (container) {
            const loader = container.querySelector('.global-loading');
            if (loader) loader.remove();
        }
    }
    
    _applyFiltersAndSort() {
        if (!this.originalData.length) {
            this.displayData = [];
            return;
        }
        
        let filtered = [...this.originalData];
        
        if (this._searchTerm) {
            const searchFields = this.config.searchFields || [];
            filtered = filtered.filter(item => {
                return searchFields.some(field => {
                    const val = item[field];
                    return val && String(val).toLowerCase().includes(this._searchTerm);
                });
            });
        }
        
        filtered = this._applyCustomFilters(filtered);
        
        if (this._sortKey && this.config.sortSelectors[this._sortKey]) {
            filtered.sort(this.config.sortSelectors[this._sortKey]);
        }
        
        this.displayData = filtered;
        if (this.grid) this.grid.setItems(this.displayData);
    }
    
    _applyCustomFilters(items) { return items; }
    
    initGrid(containerId, customOptions = {}) {
        if (this.grid) this.grid.destroy();
        this.grid = new window.GridRenderer({
            containerId,
            items: this.displayData,
            renderItem: (item, idx) => this.renderItem(item, idx),
            options: {
                searchInputId: null,
                searchFields: [],
                sortSelectors: {},
                defaultSort: null,
                emptyStateHtml: `<div class="empty-state">No ${this.feature} found.</div>`,
                onCardClick: (item, idx) => this.openEditModal(item, idx),
                onCardEdit: (item, idx) => this.openEditModal(item, idx),
                onCardDelete: (item, idx) => this.confirmDelete(item[this.config.nameField], () => this.performDelete(item, idx)),
                ...customOptions,
            },
        });
    }
    
    setSearchTerm(term) {
        this._searchTerm = term.toLowerCase();
        this._applyFiltersAndSort();
    }
    
    setSort(sortKey) {
        this._sortKey = sortKey;
        this._applyFiltersAndSort();
    }
    
    async openCreateModal() {
        const name = await modal.prompt(`Create ${this.feature}`, '', { placeholder: `${this.feature} name` });
        if (name) await this.create({ [this.config.nameField]: name });
    }
    
    async openEditModal(item, index) {
        const newName = await modal.prompt(`Edit ${this.feature}`, item[this.config.nameField], { placeholder: `${this.feature} name` });
        if (newName && newName !== item[this.config.nameField]) {
            await this.update(item.id, { [this.config.nameField]: newName });
        }
    }
    
    async performDelete(item, index) {
        await this.delete(item.id);
    }
    
    async create(data) {
        const result = await api.post(this.getApiPath(), data);
        await this.load(true);
        return result;
    }
    
    async update(id, data) {
        const result = await api.put(`${this.getApiPath()}/${id}`, data);
        await this.load(true);
        return result;
    }
    
    async delete(id) {
        await api.delete(`${this.getApiPath()}/${id}`);
        await this.load(true);
    }
    
    async confirmDelete(name, onConfirm) {
        const confirmed = await modal.confirm(`Delete ${this.feature} "${name}"?`);
        if (confirmed) await onConfirm();
    }
    
    refresh() {
        this._applyFiltersAndSort();
    }
    
    clear() {
        if (this.grid) {
            this.grid.destroy();
            this.grid = null;
        }
        this.originalData = [];
        this.displayData = [];
        this.offset = 0;
        this.hasMore = true;
        this.totalCount = 0;
        this.isLoaded = false;
        const container = document.getElementById(this.config.gridContainerId);
        if (container) container.innerHTML = '';
        this.enableControls(false);
        this._updateEmptyState();
        this.updateLoadMoreButton();
    }
    
    enableControls(enabled) {
        const addBtn = document.getElementById(`add${this.feature.charAt(0).toUpperCase() + this.feature.slice(1)}Btn`);
        if (addBtn) addBtn.disabled = !enabled;
    }
    
    resetFilters() {
        this._searchTerm = '';
        this._sortKey = this.config.defaultSort || Object.keys(this.config.sortSelectors)[0];
        this._applyFiltersAndSort();
    }
    
    _updateEmptyState() {
        const gridContainer = document.getElementById(this.config.gridContainerId);
        const emptyDiv = document.getElementById(this.config.emptyStateDivId);
        if (!gridContainer || !emptyDiv) return;

        const hasModel = !!state.get('currentModel');
        const hasItems = this.originalData && this.originalData.length > 0;

        if (hasModel && !hasItems && this.offset >= this.totalCount && this.totalCount === 0) {
            gridContainer.style.display = 'none';
            emptyDiv.style.display = 'flex';
        } else {
            gridContainer.style.display = '';
            emptyDiv.style.display = 'none';
        }
    }
}
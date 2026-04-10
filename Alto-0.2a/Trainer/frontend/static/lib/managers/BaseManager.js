// lib/managers/BaseManager.js - Abstract base for all feature managers
import { state } from '../core/state.js';
import events from '../core/events.js';
import { api } from '../core/api.js';
import { modal } from '../ui/modal.js';
import { dom } from '../core/dom.js';
import { error } from '../ui/error.js';

export class BaseManager {
    constructor(featureName, config) {
        this.feature = featureName;
        this.config = config;
        this.grid = null;
        this.originalData = [];
        this.displayData = [];
        this.isLoaded = false;
        
        this._searchTerm = '';
        this._sortKey = null;
        
        events.on('state:currentModel:changed', async ({ newValue }) => {
            if (newValue) await this.load();
            else this.clear();
        });
    }
    
    getItems() {
        throw new Error('getItems() must be implemented by subclass');
    }
    
    renderItem(item, index) {
        throw new Error('renderItem() must be implemented by subclass');
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
    
    getApiPath() {
        const path = this.config.apiPath;
        return typeof path === 'function' ? path() : path;
    }
    
    async create(data) {
        const result = await api.post(this.getApiPath(), data);
        await this.load();
        return result;
    }
    
    async update(id, data) {
        const result = await api.put(`${this.getApiPath()}/${id}`, data);
        await this.load();
        return result;
    }
    
    async delete(id) {
        await api.delete(`${this.getApiPath()}/${id}`);
        await this.load();
    }
    
    async confirmDelete(name, onConfirm) {
        const confirmed = await modal.confirm(`Delete ${this.feature} "${name}"?`);
        if (confirmed) await onConfirm();
    }
    
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
    
    _applyFiltersAndSort() {
        if (!this.originalData.length) return;
        
        let filtered = [...this.originalData];
        
        if (this._searchTerm) {
            filtered = filtered.filter(item => {
                const searchFields = this.config.searchFields || [];
                return searchFields.some(field => {
                    const val = item[field];
                    return val && String(val).toLowerCase().includes(this._searchTerm);
                });
            });
        }
        
        filtered = this._applyCustomFilters(filtered);
        
        if (this._sortKey) {
            const sortFn = this.config.sortSelectors[this._sortKey];
            if (sortFn) filtered.sort(sortFn);
        }
        
        this.displayData = filtered;
        if (this.grid) this.grid.setItems(this.displayData);
    }
    
    _applyCustomFilters(items) {
        return items;
    }
    
    async load() {
        if (!state.get('currentModel')) {
            this.clear();
            return;
        }
        const container = document.getElementById(this.config.gridContainerId);
        if (!container) return;
        
        try {
            const rawData = await this.fetchData();
            this.originalData = this.transformData(rawData);
            this._applyFiltersAndSort();
            this.isLoaded = true;
            
            if (!this.grid) {
                this.initGrid(this.config.gridContainerId);
            } else {
                this.grid.setItems(this.displayData);
            }
            this.enableControls(true);
            this._updateEmptyState();
        } catch (err) {
            error.alert(`Failed to load ${this.feature}: ${err.message}`);
            this.enableControls(false);
        }
    }
    
    async fetchData() {
        return await api.get(this.getApiPath());
    }
    
    transformData(raw) {
        return raw;
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
        this.isLoaded = false;
        const container = document.getElementById(this.config.gridContainerId);
        if (container) container.innerHTML = '';
        this.enableControls(false);
        this._updateEmptyState();
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

        if (hasModel && !hasItems) {
            gridContainer.style.display = 'none';
            emptyDiv.style.display = 'flex';
        } else {
            gridContainer.style.display = '';
            emptyDiv.style.display = 'none';
        }
    }
}
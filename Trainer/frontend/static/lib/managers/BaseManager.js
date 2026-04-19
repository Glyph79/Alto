// lib/managers/BaseManager.js - Abstract base with bidirectional pagination, sliding window, and scroll preservation
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
        this.allItems = [];
        this.displayData = [];
        this.isLoaded = false;
        
        // Pagination state
        this.startOffset = 0;
        this.endOffset = 0;
        this.totalCount = 0;
        this.limit = 20;
        this.maxItems = 100;
        this.isLoadingMore = false;
        this.isLoadingPrevious = false;
        
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
    
    // Optional hook to transform raw API data before storing
    transformData(rawItems) {
        return rawItems;
    }
    
    getApiPath() {
        const path = this.config.apiPath;
        return typeof path === 'function' ? path() : path;
    }
    
    get itemsKey() { return this.config.itemsKey || this.feature; }
    
    async fetchPage(offset, limit) {
        const url = `${this.getApiPath()}?limit=${limit}&offset=${offset}`;
        const response = await api.get(url);
        return {
            items: response[this.itemsKey],
            total: response.total
        };
    }
    
    getScrollContainer() {
        const container = document.getElementById(this.config.gridContainerId);
        if (!container) return window;
        let el = container.parentElement;
        while (el && el !== document.body) {
            const style = window.getComputedStyle(el);
            if (style.overflowY === 'auto' || style.overflowY === 'scroll') {
                return el;
            }
            el = el.parentElement;
        }
        return window;
    }
    
    saveScrollPosition() {
        const scrollContainer = this.getScrollContainer();
        if (scrollContainer === window) {
            return { type: 'window', scrollY: window.scrollY };
        }
        const container = document.getElementById(this.config.gridContainerId);
        const firstCard = container?.querySelector('.group-card, .topic-card, .variant-card, .fallback-card');
        if (!firstCard) {
            return { type: 'element', scrollTop: scrollContainer.scrollTop };
        }
        const containerRect = scrollContainer.getBoundingClientRect();
        const cardRect = firstCard.getBoundingClientRect();
        const offset = cardRect.top - containerRect.top;
        return { type: 'element', scrollTop: scrollContainer.scrollTop, offsetToCard: offset, card: firstCard };
    }
    
    restoreScrollPosition(saved) {
        if (!saved) return;
        const scrollContainer = this.getScrollContainer();
        if (saved.type === 'window') {
            window.scrollTo(0, saved.scrollY);
        } else if (saved.type === 'element' && saved.card && saved.card.isConnected) {
            const newCardRect = saved.card.getBoundingClientRect();
            const containerRect = scrollContainer.getBoundingClientRect();
            const newOffset = newCardRect.top - containerRect.top;
            const delta = saved.offsetToCard - newOffset;
            scrollContainer.scrollTop += delta;
        } else if (saved.type === 'element') {
            scrollContainer.scrollTop = saved.scrollTop;
        }
    }
    
    async load(reset = true) {
        if (reset) {
            this.allItems = [];
            this.startOffset = 0;
            this.endOffset = 0;
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
            if (reset) {
                const { items, total } = await this.fetchPage(0, this.limit);
                this.totalCount = total;
                this.allItems = this.transformData(items);
                this.startOffset = 0;
                this.endOffset = items.length;
            }
            
            this._applyFiltersAndSort();
            
            if (!this.grid) {
                this.initGrid(this.config.gridContainerId);
            } else {
                this.grid.setItems(this.displayData);
            }
            this.enableControls(true);
            this._updateEmptyState();
            this.updateNavButtons();
        } catch (err) {
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
        if (this.isLoadingMore || this.endOffset >= this.totalCount) return;
        this.isLoadingMore = true;
        this.showLoadMoreLoading();
        
        const savedScroll = this.saveScrollPosition();
        
        try {
            const { items, total } = await this.fetchPage(this.endOffset, this.limit);
            this.totalCount = total;
            const transformed = this.transformData(items);
            this.allItems.push(...transformed);
            let removedCount = 0;
            if (this.allItems.length > this.maxItems) {
                const removeCount = this.allItems.length - this.maxItems;
                this.allItems.splice(0, removeCount);
                this.startOffset += removeCount;
                removedCount = removeCount;
            }
            this.endOffset += items.length;
            
            this._applyFiltersAndSort();
            this.grid.setItems(this.displayData);
            this.updateNavButtons();
            
            setTimeout(() => this.restoreScrollPosition(savedScroll), 0);
        } catch (err) {
            error.alert(`Failed to load more: ${err.message}`);
        } finally {
            this.isLoadingMore = false;
            this.hideLoadMoreLoading();
        }
    }
    
    async loadPrevious() {
        if (this.isLoadingPrevious || this.startOffset <= 0) return;
        this.isLoadingPrevious = true;
        this.showLoadPreviousLoading();
        
        const savedScroll = this.saveScrollPosition();
        
        const newStart = Math.max(0, this.startOffset - this.limit);
        const newLimit = this.startOffset - newStart;
        if (newLimit <= 0) return;
        
        try {
            const { items, total } = await this.fetchPage(newStart, newLimit);
            this.totalCount = total;
            const transformed = this.transformData(items);
            this.allItems.unshift(...transformed);
            let removedCount = 0;
            if (this.allItems.length > this.maxItems) {
                const removeCount = this.allItems.length - this.maxItems;
                this.allItems.splice(-removeCount, removeCount);
                this.endOffset -= removeCount;
                removedCount = removeCount;
            }
            this.startOffset = newStart;
            
            this._applyFiltersAndSort();
            this.grid.setItems(this.displayData);
            this.updateNavButtons();
            
            setTimeout(() => this.restoreScrollPosition(savedScroll), 0);
        } catch (err) {
            error.alert(`Failed to load previous: ${err.message}`);
        } finally {
            this.isLoadingPrevious = false;
            this.hideLoadPreviousLoading();
        }
    }
    
    updateNavButtons() {
        const container = document.getElementById(this.config.gridContainerId);
        if (!container) return;
        
        const existingPrev = container.querySelector('.load-prev-btn');
        if (existingPrev) existingPrev.remove();
        const existingNext = container.querySelector('.load-more-btn');
        if (existingNext) existingNext.remove();
        const existingPrevLoader = container.querySelector('.load-prev-loader');
        if (existingPrevLoader) existingPrevLoader.remove();
        const existingNextLoader = container.querySelector('.load-more-loader');
        if (existingNextLoader) existingNextLoader.remove();
        
        if (this.startOffset > 0) {
            const prevBtn = dom.createElement('button', { class: 'load-prev-btn' }, ['← Load Previous']);
            prevBtn.addEventListener('click', () => this.loadPrevious());
            container.insertBefore(prevBtn, container.firstChild);
        }
        
        if (this.endOffset < this.totalCount) {
            const nextBtn = dom.createElement('button', { class: 'load-more-btn' }, ['Load More →']);
            nextBtn.addEventListener('click', () => this.loadMore());
            container.appendChild(nextBtn);
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
    
    showLoadPreviousLoading() {
        const container = document.getElementById(this.config.gridContainerId);
        if (!container) return;
        let loader = container.querySelector('.load-prev-loader');
        if (!loader) {
            loader = dom.createElement('div', { class: 'load-prev-loader' }, ['Loading previous...']);
            container.insertBefore(loader, container.firstChild);
        }
    }
    
    hideLoadPreviousLoading() {
        const container = document.getElementById(this.config.gridContainerId);
        if (container) {
            const loader = container.querySelector('.load-prev-loader');
            if (loader) loader.remove();
        }
    }
    
    showLoadingIndicator(container) {
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
        if (!this.allItems.length) {
            this.displayData = [];
            if (this.grid) this.grid.setItems(this.displayData);
            this.updateNavButtons();
            return;
        }
        
        let filtered = [...this.allItems];
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
        this.updateNavButtons();
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
        this.allItems = [];
        this.displayData = [];
        this.startOffset = 0;
        this.endOffset = 0;
        this.totalCount = 0;
        this.isLoaded = false;
        const container = document.getElementById(this.config.gridContainerId);
        if (container) container.innerHTML = '';
        this.enableControls(false);
        this._updateEmptyState();
        this.updateNavButtons();
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
        const hasItems = this.allItems && this.allItems.length > 0;
        if (hasModel && !hasItems && this.totalCount === 0) {
            gridContainer.style.display = 'none';
            emptyDiv.style.display = 'flex';
        } else {
            gridContainer.style.display = '';
            emptyDiv.style.display = 'none';
        }
    }
}

export function naturalCompare(a, b) {
    const collator = new Intl.Collator(undefined, { numeric: true, sensitivity: 'base' });
    return collator.compare(a, b);
}
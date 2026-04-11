import { BaseManager } from './BaseManager.js';
import { state } from '../core/state.js';
import { api } from '../core/api.js';
import { modal } from '../ui/modal.js';
import { dom } from '../core/dom.js';
import { ListEditor } from '../../components/ListEditor.js';
import { error } from '../ui/error.js';
import { modalLock } from '../ui/modalLock.js';

export class VariantManager extends BaseManager {
    constructor() {
        super('variants', {
            apiPath: () => `/api/models/${state.get('currentModel')}/variants`,
            itemsKey: 'variants',
            nameField: 'name',
            searchFields: ['name', 'words'],
            sortSelectors: {
                'name-asc': (a, b) => (a.name || '').localeCompare(b.name || ''),
                'name-desc': (a, b) => (b.name || '').localeCompare(a.name || ''),
                'words-desc': (a, b) => b.words.length - a.words.length,
                'words-asc': (a, b) => a.words.length - b.words.length,
            },
            defaultSort: 'name-asc',
            gridContainerId: 'variantsGridContainer',
            emptyStateDivId: 'noVariantsEmptyState',
        });
        this.currentVariantId = null;
        this.wordEditor = null;
    }
    
    async fetchPage(offset, limit) {
        const url = `${this.getApiPath()}?limit=${limit}&offset=${offset}`;
        const response = await api.get(url);
        return {
            items: response.variants,
            total: response.total
        };
    }
    
    renderItem(variant, idx) {
        return `
            <div class="variant-card" data-card-index="${idx}" data-variant-id="${variant.id}">
                <div class="header">
                    <div class="card-actions">
                        <button class="card-edit" data-variant-id="${variant.id}" title="Edit">✎</button>
                        <button class="card-delete" data-variant-id="${variant.id}" title="Delete">🗑</button>
                    </div>
                </div>
                <h4 class="variant-name">${dom.escapeHtml(variant.name || 'Unnamed')}</h4>
                <div class="stats">
                    <span>📝 ${variant.words.length} word${variant.words.length !== 1 ? 's' : ''}</span>
                </div>
            </div>
        `;
    }
    
    async openCreateModal() {
        await this.openVariantModal(null);
    }
    
    async openEditModal(variant) {
        await this.openVariantModal(variant.id);
    }
    
    async openVariantModal(id) {
        if (!modalLock.lock('variantModal')) return;
        try {
            let variant = null;
            if (id !== null) {
                variant = this.originalData.find(v => v.id === id);
                if (!variant) return;
            }
            const isNew = (id === null);
            const modalId = modal.show({
                title: isNew ? 'Add Variant' : 'Edit Variant',
                content: this.buildVariantModalContent(variant),
                actions: [
                    { label: 'Cancel', variant: 'cancel', onClick: () => { modal.close(modalId); modalLock.unlock('variantModal'); }, close: false },
                    { label: 'Save', variant: 'save', close: false, onClick: () => this.saveVariant(id, modalId) },
                ],
                size: 'medium',
                closable: false,
            });
            this.currentVariantId = id;
            this.initWordEditor(variant?.words || []);
        } catch (err) {
            modalLock.unlock('variantModal');
            throw err;
        }
    }
    
    buildVariantModalContent(variant) {
        const div = dom.createElement('div', {});
        div.innerHTML = `
            <div class="form-row">
                <label>Name (optional)</label>
                <input type="text" id="variantName" value="${dom.escapeHtml(variant?.name || '')}" placeholder="e.g., Weather synonyms">
            </div>
            <div class="qa-section">
                <h3>Words <span style="color:#ffaa66;">(at least one)</span></h3>
                <div id="variantWordsContainer"></div>
            </div>
        `;
        return div;
    }
    
    initWordEditor(words) {
        const container = document.getElementById('variantWordsContainer');
        if (this.wordEditor) this.wordEditor.destroy();
        this.wordEditor = new ListEditor({
            container,
            items: words || [],
            placeholder: 'Word',
            onAdd: (val) => { this.wordEditor.items.push(val); this.wordEditor.render(); },
            onEdit: (idx, old, newVal) => { this.wordEditor.items[idx] = newVal; this.wordEditor.render(); },
            onDelete: (idx) => { this.wordEditor.items.splice(idx, 1); this.wordEditor.render(); },
        });
    }
    
    async saveVariant(id, modalId) {
        const modalEl = document.getElementById(modalId);
        if (!modalEl) return;
        let name = modalEl.querySelector('#variantName').value.trim();
        if (!name) name = 'Unnamed Variant';
        const words = this.wordEditor.getItems();
        
        if (words.length === 0) {
            error.alert('At least one word is required.');
            modalLock.unlock('variantModal');
            return;
        }
        const data = { name, words };
        try {
            if (id === null) {
                await api.post(this.getApiPath(), data);
            } else {
                await api.put(`${this.getApiPath()}/${id}`, data);
            }
            await this.load(true);
            modal.close(modalId);
            modalLock.unlock('variantModal');
        } catch (err) {
            error.alert(err.message);
            modalLock.unlock('variantModal');
        }
    }
    
    async performDelete(item) {
        await api.delete(`${this.getApiPath()}/${item.id}`);
        await this.load(true);
    }
}
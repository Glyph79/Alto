// lib/managers/VariantManager.js
import { BaseManager } from './BaseManager.js';
import { state } from '../core/state.js';
import { api } from '../core/api.js';
import { modal } from '../ui/modal.js';
import { dom } from '../core/dom.js';
import { ListEditor } from '../../components/ListEditor.js';
import events from '../core/events.js';

export class VariantManager extends BaseManager {
    constructor() {
        super('variants', {
            apiPath: () => `/api/models/${state.get('currentModel')}/variants`,
            nameField: 'name',
            searchFields: ['name', 'words'],
            sortSelectors: {
                'name-asc': (a, b) => (a.name || '').localeCompare(b.name || ''),
                'name-desc': (a, b) => (b.name || '').localeCompare(a.name || ''),
                'section-asc': (a, b) => (a.section || '').localeCompare(b.section || ''),
                'section-desc': (a, b) => (b.section || '').localeCompare(a.section || ''),
                'words-desc': (a, b) => b.words.length - a.words.length,
                'words-asc': (a, b) => a.words.length - b.words.length,
            },
            defaultSort: 'name-asc',
            gridContainerId: 'variantsGridContainer',
        });
        this.currentVariantId = null;
        this.wordEditor = null;
        events.on('sections:updated', () => this.refresh());
    }
    
    async fetchData() {
        return await api.get(this.getApiPath());
    }
    
    transformData(raw) {
        return raw;
    }
    
    renderItem(variant, idx) {
        return `
            <div class="variant-card" data-card-index="${idx}" data-variant-id="${variant.id}">
                <div class="header">
                    <span class="section-badge">${dom.escapeHtml(variant.section || 'Uncategorized')}</span>
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
                { label: 'Cancel', variant: 'cancel', onClick: () => modal.close(modalId) },
                { label: 'Save', variant: 'save', onClick: () => this.saveVariant(id, modalId) },
            ],
            size: 'medium',
            closable: false,
        });
        this.currentVariantId = id;
        this.initWordEditor(variant?.words || []);
        this.populateVariantSectionSelect(variant?.section);
    }
    
    buildVariantModalContent(variant) {
        const div = dom.createElement('div', {});
        div.innerHTML = `
            <div class="form-row">
                <label>Name</label>
                <input type="text" id="variantName" value="${dom.escapeHtml(variant?.name || '')}" placeholder="e.g., Weather synonyms">
            </div>
            <div class="form-row">
                <label>Section</label>
                <select id="variantSectionSelect">
                    <option value="">(Uncategorized)</option>
                </select>
            </div>
            <div class="qa-section">
                <h3>Words</h3>
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
    
    populateVariantSectionSelect(selectedSection) {
        const select = document.getElementById('variantSectionSelect');
        if (!select) return;
        let options = '<option value="">(Uncategorized)</option>';
        (state.get('sections') || []).forEach(s => {
            options += `<option value="${dom.escapeHtml(s)}" ${s === selectedSection ? 'selected' : ''}>${dom.escapeHtml(s)}</option>`;
        });
        select.innerHTML = options;
    }
    
    async saveVariant(id, modalId) {
        const name = document.getElementById('variantName').value.trim();
        if (!name) {
            modal.show({ title: 'Error', content: 'Variant name is required.', actions: [{ label: 'OK' }], size: 'small' });
            return;
        }
        const section = document.getElementById('variantSectionSelect').value || null;
        const words = this.wordEditor.getItems();
        if (words.length === 0) {
            modal.show({ title: 'Error', content: 'At least one word is required.', actions: [{ label: 'OK' }], size: 'small' });
            return;
        }
        const data = { name, words, section };
        try {
            if (id === null) {
                await api.post(this.getApiPath(), data);
            } else {
                await api.put(`${this.getApiPath()}/${id}`, data);
            }
            await this.load();
            modal.close(modalId);
        } catch (err) {
            modal.show({ title: 'Error', content: err.message, actions: [{ label: 'OK' }], size: 'small' });
        }
    }
    
    async performDelete(item) {
        await api.delete(`${this.getApiPath()}/${item.id}`);
        await this.load();
    }
}
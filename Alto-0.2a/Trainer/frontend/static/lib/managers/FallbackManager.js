// lib/managers/FallbackManager.js
import { BaseManager } from './BaseManager.js';
import { state } from '../core/state.js';
import { api } from '../core/api.js';
import { modal } from '../ui/modal.js';
import { dom } from '../core/dom.js';
import { ListEditor } from '../../components/ListEditor.js';
import events from '../core/events.js';

export class FallbackManager extends BaseManager {
    constructor() {
        super('fallbacks', {
            apiPath: () => `/api/models/${state.get('currentModel')}/fallbacks`,
            nameField: 'name',
            searchFields: ['name', 'description'],
            sortSelectors: {
                'name-asc': (a, b) => (a.name || '').localeCompare(b.name || ''),
                'name-desc': (a, b) => (b.name || '').localeCompare(a.name || ''),
                'usage-desc': (a, b) => (b.usage_count || 0) - (a.usage_count || 0),
                'usage-asc': (a, b) => (a.usage_count || 0) - (b.usage_count || 0),
                'answers-desc': (a, b) => (b.answer_count || 0) - (a.answer_count || 0),
                'answers-asc': (a, b) => (a.answer_count || 0) - (b.answer_count || 0),
            },
            defaultSort: 'name-asc',
            gridContainerId: 'fallbacksGridContainer',
            emptyStateDivId: 'noFallbacksEmptyState',
        });
        this.currentFallbackId = null;
        this.answerEditor = null;
        events.on('fallbacks:updated', () => this.refresh());
    }
    
    async fetchData() {
        return await api.get(this.getApiPath());
    }
    
    transformData(raw) {
        return raw;
    }
    
    renderItem(fb, idx) {
        return `
            <div class="fallback-card" data-card-index="${idx}" data-fallback-id="${fb.id}">
                <div class="header">
                    <div style="display: flex; align-items: center; gap: 4px;">
                        <span class="fallback-name">${dom.escapeHtml(fb.name)}</span>
                    </div>
                    <div class="card-actions">
                        <button class="card-edit" data-fallback-id="${fb.id}" title="Edit">✎</button>
                        <button class="card-delete" data-fallback-id="${fb.id}" title="Delete">🗑</button>
                    </div>
                </div>
                <div class="description">${dom.escapeHtml(fb.description || '')}</div>
                <div class="stats">
                    <span>📝 ${fb.answer_count} answer${fb.answer_count !== 1 ? 's' : ''}</span>
                    <span>🔗 ${fb.usage_count} group${fb.usage_count !== 1 ? 's' : ''}</span>
                </div>
            </div>
        `;
    }
    
    async openCreateModal() {
        await this.openFallbackModal(null);
    }
    
    async openEditModal(item) {
        const full = await api.get(`${this.getApiPath()}/${item.id}`);
        await this.openFallbackModal(full);
    }
    
    async openFallbackModal(fallback) {
        const isNew = !fallback;
        const modalId = modal.show({
            title: isNew ? 'Add Fallback' : 'Edit Fallback',
            content: this.buildFallbackModalContent(fallback),
            actions: [
                { label: 'Cancel', variant: 'cancel', onClick: () => modal.close(modalId) },
                { label: 'Save', variant: 'save', onClick: () => this.saveFallback(fallback?.id, modalId) },
            ],
            size: 'medium',
            closable: false,
        });
        this.initAnswerEditor(fallback?.answers || []);
        if (fallback) {
            document.getElementById('fallbackName').value = fallback.name || '';
            document.getElementById('fallbackDescription').value = fallback.description || '';
        } else {
            document.getElementById('fallbackName').value = '';
            document.getElementById('fallbackDescription').value = '';
        }
    }
    
    buildFallbackModalContent(fallback) {
        const div = dom.createElement('div', {});
        div.innerHTML = `
            <div class="form-row">
                <label>Name</label>
                <input type="text" id="fallbackName" placeholder="e.g., Default apology">
            </div>
            <div class="form-row">
                <label>Description</label>
                <input type="text" id="fallbackDescription" placeholder="Optional description">
            </div>
            <div class="qa-section">
                <h3>Answers</h3>
                <div id="fallbackAnswersContainer"></div>
            </div>
        `;
        return div;
    }
    
    initAnswerEditor(answers) {
        const container = document.getElementById('fallbackAnswersContainer');
        if (this.answerEditor) this.answerEditor.destroy();
        this.answerEditor = new ListEditor({
            container,
            items: answers || [],
            placeholder: 'Answer',
            onAdd: (val) => { this.answerEditor.items.push(val); this.answerEditor.render(); },
            onEdit: (idx, old, newVal) => { this.answerEditor.items[idx] = newVal; this.answerEditor.render(); },
            onDelete: (idx) => { this.answerEditor.items.splice(idx, 1); this.answerEditor.render(); },
        });
    }
    
    async saveFallback(id, modalId) {
        const name = document.getElementById('fallbackName').value.trim();
        if (!name) {
            modal.show({ title: 'Error', content: 'Fallback name is required.', actions: [{ label: 'OK' }], size: 'small' });
            return;
        }
        const description = document.getElementById('fallbackDescription').value.trim();
        const answers = this.answerEditor.getItems();
        if (answers.length === 0) {
            modal.show({ title: 'Error', content: 'At least one answer is required.', actions: [{ label: 'OK' }], size: 'small' });
            return;
        }
        const data = { name, description, answers };
        try {
            if (id === null) {
                await api.post(this.getApiPath(), data);
            } else {
                await api.put(`${this.getApiPath()}/${id}`, data);
            }
            await this.load();
            modal.close(modalId);
            events.emit('fallbacks:updated');
        } catch (err) {
            modal.show({ title: 'Error', content: err.message, actions: [{ label: 'OK' }], size: 'small' });
        }
    }
    
    async performDelete(item) {
        await api.delete(`${this.getApiPath()}/${item.id}`);
        await this.load();
        events.emit('fallbacks:updated');
    }
}
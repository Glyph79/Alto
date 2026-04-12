import { BaseManager, naturalCompare } from './BaseManager.js';
import { state } from '../core/state.js';
import { api } from '../core/api.js';
import { modal } from '../ui/modal.js';
import { dom } from '../core/dom.js';
import { ListEditor } from '../../components/ListEditor.js';
import events from '../core/events.js';
import { error } from '../ui/error.js';
import { modalLock } from '../ui/modalLock.js';

export class FallbackManager extends BaseManager {
    constructor() {
        super('fallbacks', {
            apiPath: () => `/api/models/${state.get('currentModel')}/fallbacks`,
            itemsKey: 'fallbacks',
            nameField: 'name',
            searchFields: ['name', 'description'],
            sortSelectors: {
                'name-asc': (a, b) => naturalCompare(a.name || '', b.name || ''),
                'name-desc': (a, b) => naturalCompare(b.name || '', a.name || ''),
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
    
    async fetchPage(offset, limit) {
        const url = `${this.getApiPath()}?limit=${limit}&offset=${offset}`;
        const response = await api.get(url);
        return {
            items: response.fallbacks,
            total: response.total
        };
    }
    
    // CHANGED: update global state after loading
    async load(reset = true) {
        await super.load(reset);
        state.set('fallbacks', this.allItems);
    }
    
    renderItem(fb, idx) {
        return `
            <div class="fallback-card" data-card-index="${idx}" data-fallback-id="${fb.id}">
                <div class="header">
                    <div style="display: flex; align-items: center; gap: 4px;">
                        <span class="fallback-name">${dom.escapeHtml(fb.name || 'Unnamed')}</span>
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
        if (!modalLock.lock('fallbackModal')) return;
        try {
            const isNew = (fallback === null);
            const modalId = modal.show({
                title: isNew ? 'Add Fallback' : 'Edit Fallback',
                content: this.buildFallbackModalContent(fallback),
                actions: [
                    { label: 'Cancel', variant: 'cancel', onClick: () => { modal.close(modalId); modalLock.unlock('fallbackModal'); }, close: false },
                    { label: 'Save', variant: 'save', close: false, onClick: () => this.saveFallback(isNew ? null : fallback.id, modalId) },
                ],
                size: 'medium',
                closable: false,
            });
            this.initAnswerEditor(fallback?.answers || [], modalId);
            const modalEl = document.getElementById(modalId);
            if (modalEl) {
                if (fallback) {
                    modalEl.querySelector('#fallbackName').value = fallback.name || '';
                    modalEl.querySelector('#fallbackDescription').value = fallback.description || '';
                } else {
                    modalEl.querySelector('#fallbackName').value = '';
                    modalEl.querySelector('#fallbackDescription').value = '';
                }
            }
        } catch (err) {
            modalLock.unlock('fallbackModal');
            throw err;
        }
    }
    
    buildFallbackModalContent(fallback) {
        const div = dom.createElement('div', {});
        div.innerHTML = `
            <div class="form-row">
                <label>Name (optional – will be auto‑generated if empty)</label>
                <input type="text" id="fallbackName" placeholder="e.g., Default apology">
            </div>
            <div class="form-row">
                <label>Description (optional)</label>
                <input type="text" id="fallbackDescription" placeholder="Optional description">
            </div>
            <div class="qa-section">
                <h3>Answers</h3>
                <div id="fallbackAnswersContainer"></div>
            </div>
        `;
        return div;
    }
    
    initAnswerEditor(answers, modalId) {
        const modalEl = document.getElementById(modalId);
        if (!modalEl) return;
        const container = modalEl.querySelector('#fallbackAnswersContainer');
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
        const modalEl = document.getElementById(modalId);
        if (!modalEl) return;
        const name = modalEl.querySelector('#fallbackName').value.trim();
        const description = modalEl.querySelector('#fallbackDescription').value.trim();
        const answers = this.answerEditor.getItems();
        
        if (answers.length === 0) {
            error.alert('At least one answer is required.');
            modalLock.unlock('fallbackModal');
            return;
        }
        const data = { name, description, answers };
        try {
            if (id === null) {
                await api.post(this.getApiPath(), data);
            } else {
                await api.put(`${this.getApiPath()}/${id}`, data);
            }
            await this.load(true);
            modal.close(modalId);
            modalLock.unlock('fallbackModal');
            events.emit('fallbacks:updated');
        } catch (err) {
            error.alert(err.message);
            modalLock.unlock('fallbackModal');
        }
    }
    
    async performDelete(item) {
        await api.delete(`${this.getApiPath()}/${item.id}`);
        await this.load(true);
        events.emit('fallbacks:updated');
    }
    
    // CHANGED: clear global state when model is unloaded
    clear() {
        super.clear();
        state.set('fallbacks', []);
    }
}
// lib/managers/SectionManager.js
import { BaseManager } from './BaseManager.js';
import { state } from '../core/state.js';
import { api } from '../core/api.js';
import { modal } from '../ui/modal.js';
import { dom } from '../core/dom.js';

export class SectionManager extends BaseManager {
    constructor() {
        super('sections', {
            apiPath: () => `/api/models/${state.get('currentModel')}/sections`,
            nameField: 'section',
            searchFields: ['section'],
            sortSelectors: {
                'name-asc': (a, b) => a.section.localeCompare(b.section),
                'name-desc': (a, b) => b.section.localeCompare(a.section),
                'groups-desc': (a, b) => b.count - a.count,
                'groups-asc': (a, b) => a.count - b.count,
            },
            defaultSort: 'name-asc',
            gridContainerId: 'sectionsGridContainer',
        });
    }
    
    async fetchData() {
        if (state.get('sections').length === 0) {
            const model = state.get('currentModel');
            if (model) {
                const info = await api.get(`/api/models/${model}`);
                state.set('sections', info.sections || []);
            }
        }
        const groups = state.get('groups');
        const counts = {};
        groups.forEach(g => {
            const section = g.section || 'Uncategorized';
            counts[section] = (counts[section] || 0) + 1;
        });
        const sections = [...state.get('sections'), 'Uncategorized'];
        return sections.map(section => ({ section, count: counts[section] || 0, isUncategorized: section === 'Uncategorized' }));
    }
    
    transformData(raw) {
        return raw;
    }
    
    renderItem(item, idx) {
        const hue = (item.section.split('').reduce((acc, char) => acc + char.charCodeAt(0), 0) * 7) % 360;
        return `
            <div class="section-card" data-card-index="${idx}" data-section="${dom.escapeHtml(item.section)}">
                <div class="header">
                    <div style="display: flex; align-items: center; gap: 4px;">
                        <span class="section-color-dot" style="background-color: hsl(${hue}, 70%, 60%);"></span>
                        <span class="section-name">${dom.escapeHtml(item.section)}</span>
                    </div>
                    <div class="card-actions">
                        <button class="card-edit" data-section="${dom.escapeHtml(item.section)}" title="Edit">✎</button>
                        ${!item.isUncategorized ? `<button class="card-delete" data-section="${dom.escapeHtml(item.section)}" title="Delete">🗑</button>` : ''}
                    </div>
                </div>
                <div class="stats">
                    <span>📁 ${item.count} group${item.count !== 1 ? 's' : ''}</span>
                </div>
            </div>
        `;
    }
    
    async openCreateModal() {
        const name = await modal.prompt('Add Section', '', { placeholder: 'Section name' });
        if (!name) return;
        if (name.toLowerCase() === 'uncategorized') {
            modal.show({ title: 'Error', content: '"Uncategorized" is a reserved name.', actions: [{ label: 'OK' }], size: 'small' });
            return;
        }
        try {
            await api.post(this.getApiPath(), { section: name });
            await this.load();
        } catch (err) {
            modal.show({ title: 'Error', content: err.message, actions: [{ label: 'OK' }], size: 'small' });
        }
    }
    
    async openEditModal(item) {
        if (item.isUncategorized) {
            modal.show({ title: 'Uncategorized', content: 'The "Uncategorized" pseudo‑section cannot be edited.', actions: [{ label: 'OK' }], size: 'small' });
            return;
        }
        const groupsInSection = state.get('groups').filter(g => (g.section || 'Uncategorized') === item.section);
        let groupsHtml = '';
        if (groupsInSection.length === 0) {
            groupsHtml = '<li style="justify-content:center; color:#888;">No groups in this section</li>';
        } else {
            groupsHtml = groupsInSection.map(g => `
                <li class="section-group-item" data-group-id="${g.id}">
                    <span class="group-name">${dom.escapeHtml(g.group_name || 'Unnamed')}</span>
                    <div class="section-group-actions">
                        <button class="edit-group-from-section" data-group-id="${g.id}" title="Edit Group">✎</button>
                        <button class="delete-group-from-section" data-group-id="${g.id}" title="Delete Group">🗑</button>
                    </div>
                </li>
            `).join('');
        }
        const content = dom.createElement('div', {}, [
            dom.createElement('div', { class: 'form-row' }, [
                dom.createElement('label', {}, ['Section Name']),
                dom.createElement('input', { id: 'editSectionName', type: 'text', value: item.section }),
            ]),
            dom.createElement('div', { class: 'form-row' }, [
                dom.createElement('label', {}, ['Groups in this section']),
                dom.createElement('ul', { class: 'section-group-list' }, [groupsHtml]),
            ]),
        ]);
        const modalId = modal.show({
            title: 'Edit Section',
            content,
            actions: [
                { label: 'Close', variant: 'cancel', onClick: () => modal.close(modalId) },
                { label: 'Save', variant: 'save', onClick: async () => {
                    const newName = document.getElementById('editSectionName').value.trim();
                    if (!newName || newName.toLowerCase() === 'uncategorized') {
                        modal.show({ title: 'Error', content: 'Invalid section name', actions: [{ label: 'OK' }], size: 'small' });
                        return;
                    }
                    if (newName !== item.section) {
                        await api.put(`/api/models/${state.get('currentModel')}/sections/${item.section}`, { new_name: newName });
                        await this.load();
                        await window.managers.groups.load();
                    }
                    modal.close(modalId);
                } },
            ],
            size: 'medium',
            closable: false,
        });
        setTimeout(() => {
            document.querySelectorAll('.edit-group-from-section').forEach(btn => {
                btn.addEventListener('click', async (e) => {
                    const groupId = parseInt(btn.dataset.groupId);
                    const index = state.get('groups').findIndex(g => g.id == groupId);
                    if (index !== -1) await window.managers.groups.openEditModal(state.get('groups')[index], index);
                });
            });
            document.querySelectorAll('.delete-group-from-section').forEach(btn => {
                btn.addEventListener('click', async (e) => {
                    const groupId = parseInt(btn.dataset.groupId);
                    const confirmed = await modal.confirm('Delete this group?');
                    if (confirmed) {
                        const index = state.get('groups').findIndex(g => g.id == groupId);
                        if (index !== -1) {
                            await api.delete(`/api/models/${state.get('currentModel')}/groups/${index}`);
                            await window.managers.groups.load();
                            await this.load();
                            modal.close(modalId);
                            this.openEditModal(item);
                        }
                    }
                });
            });
        }, 100);
    }
    
    async performDelete(item) {
        if (item.isUncategorized) return;
        const groupsUsing = state.get('groups').filter(g => g.section === item.section).length;
        const otherSections = this.originalData.filter(s => s.section !== item.section && !s.isUncategorized).map(s => s.section);
        const action = await this.showDeleteOptions(groupsUsing, otherSections);
        if (!action) return;
        let url = `/api/models/${state.get('currentModel')}/sections/${item.section}?action=${action.action}`;
        if (action.target) url += `&target=${action.target}`;
        await api.delete(url);
        await this.load();
        await window.managers.groups.load();
    }
    
    showDeleteOptions(groupsUsing, otherSections) {
        return new Promise((resolve) => {
            if (groupsUsing === 0) {
                resolve({ action: 'uncategorized' });
                return;
            }
            const content = dom.createElement('div', {}, [
                dom.createElement('p', {}, [`Section is used by ${groupsUsing} group(s).`]),
                dom.createElement('div', { class: 'delete-section-options' }, [
                    otherSections.length > 0 ? dom.createElement('div', { class: 'option-row' }, [
                        dom.createElement('input', { type: 'radio', name: 'deleteAction', value: 'move', id: 'moveRadio', checked: true }),
                        dom.createElement('label', { for: 'moveRadio' }, ['Move groups to:']),
                        dom.createElement('select', { id: 'moveTarget', class: 'compact-select' }, otherSections.map(s => `<option value="${dom.escapeHtml(s)}">${dom.escapeHtml(s)}</option>`).join('')),
                    ]) : null,
                    dom.createElement('div', { class: 'option-row' }, [
                        dom.createElement('input', { type: 'radio', name: 'deleteAction', value: 'uncategorized', id: 'uncatRadio' }),
                        dom.createElement('label', { for: 'uncatRadio' }, ['Move groups to Uncategorized']),
                    ]),
                    dom.createElement('div', { class: 'option-row' }, [
                        dom.createElement('input', { type: 'radio', name: 'deleteAction', value: 'delete', id: 'deleteRadio' }),
                        dom.createElement('label', { for: 'deleteRadio' }, ['Delete all groups using this section']),
                    ]),
                ]),
            ]);
            modal.show({
                title: 'Delete Section',
                content,
                actions: [
                    { label: 'Cancel', variant: 'cancel', onClick: () => resolve(null) },
                    { label: 'Delete', variant: 'save', onClick: () => {
                        const selectedAction = document.querySelector('input[name="deleteAction"]:checked').value;
                        const target = selectedAction === 'move' ? document.getElementById('moveTarget').value : null;
                        resolve({ action: selectedAction, target });
                    } },
                ],
                size: 'medium',
                closable: false,
            });
        });
    }
}
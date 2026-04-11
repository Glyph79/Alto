import { BaseManager } from './BaseManager.js';
import { state } from '../core/state.js';
import { api } from '../core/api.js';
import { modal } from '../ui/modal.js';
import { dom } from '../core/dom.js';
import { error } from '../ui/error.js';

export class SectionManager extends BaseManager {
    constructor() {
        super('sections', {
            apiPath: () => `/api/models/${state.get('currentModel')}/sections`,
            nameField: 'name',
            searchFields: ['name'],
            sortSelectors: {
                'name-asc': (a, b) => a.name.localeCompare(b.name),
                'name-desc': (a, b) => b.name.localeCompare(a.name),
                'groups-desc': (a, b) => b.count - a.count,
                'groups-asc': (a, b) => a.count - b.count,
            },
            defaultSort: 'name-asc',
            gridContainerId: 'sectionsGridContainer',
            emptyStateDivId: 'noSectionsEmptyState',
        });
    }
    
    async fetchData() {
        const groups = state.get('groups');
        const counts = {};
        groups.forEach(g => {
            const sectionId = g.section_id;
            if (sectionId) counts[sectionId] = (counts[sectionId] || 0) + 1;
        });
        const sectionsList = state.get('sections') || [];
        const items = [];
        items.push({ id: null, name: 'Uncategorized', count: groups.filter(g => !g.section_id).length, isUncategorized: true });
        sectionsList.forEach(section => {
            const name = section.name || `Section ${section.id}`;
            items.push({ id: section.id, name: name, count: counts[section.id] || 0, isUncategorized: false });
        });
        return items;
    }
    
    transformData(raw) {
        return raw;
    }
    
    renderItem(item, idx) {
        const name = item.name || 'Unnamed';
        const hue = item.isUncategorized ? 0 : (name.split('').reduce((acc, char) => acc + char.charCodeAt(0), 0) * 7) % 360;
        return `
            <div class="section-card" data-card-index="${idx}" data-section-id="${item.id}">
                <div class="header">
                    <div style="display: flex; align-items: center; gap: 4px;">
                        <span class="section-color-dot" style="background-color: ${item.isUncategorized ? '#888' : `hsl(${hue}, 70%, 60%)`};"></span>
                        <span class="section-name">${dom.escapeHtml(name)}</span>
                    </div>
                    <div class="card-actions">
                        <button class="card-edit" data-section-id="${item.id}" title="${item.isUncategorized ? 'View Section' : 'Edit Section'}">✎</button>
                        ${!item.isUncategorized ? `<button class="card-delete" data-section-id="${item.id}" title="Delete Section">🗑</button>` : ''}
                    </div>
                </div>
                <div class="stats">
                    <span>📁 ${item.count} group${item.count !== 1 ? 's' : ''}</span>
                </div>
            </div>
        `;
    }
    
    async openCreateModal() {
        let modalId = null;
        const content = dom.createElement('div', {});
        const formRow = dom.createElement('div', { class: 'form-row' });
        const label = dom.createElement('label', {}, ['Section Name']);
        const input = dom.createElement('input', { id: 'newSectionName', type: 'text', placeholder: 'Section name', autocomplete: 'off' });
        formRow.appendChild(label);
        formRow.appendChild(input);
        content.appendChild(formRow);
        
        modalId = modal.show({
            title: 'Add Section',
            content: content,
            actions: [
                { label: 'Cancel', variant: 'cancel', onClick: () => modal.close(modalId), close: false },
                {
                    label: 'Create',
                    variant: 'save',
                    close: false,
                    onClick: async () => {
                        const modalEl = document.getElementById(modalId);
                        if (!modalEl) return;
                        let name = modalEl.querySelector('#newSectionName').value.trim();
                        if (!name) name = 'Unnamed Section';
                        if (name.toLowerCase() === 'uncategorized') {
                            error.alert('"Uncategorized" is a reserved name.');
                            return;
                        }
                        try {
                            const result = await api.post(this.getApiPath(), { section: name });
                            if (result.sections) state.set('sections', result.sections);
                            await this.load();
                            modal.close(modalId);
                        } catch (err) {
                            error.alert(err.message);
                        }
                    }
                },
            ],
            size: 'small',
            closable: false,
        });
    }
    
    async openEditModal(item) {
        const groupsInSection = state.get('groups').filter(g => g.section_id === item.id);
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
        
        const content = dom.createElement('div', {});
        if (item.isUncategorized) {
            const infoRow = dom.createElement('div', { class: 'form-row' });
            const infoLabel = dom.createElement('label', {}, ['Section']);
            const infoValue = dom.createElement('div', { style: 'padding: 8px; background: #2d2d5a; border-radius: 6px;' }, [item.name]);
            infoRow.appendChild(infoLabel);
            infoRow.appendChild(infoValue);
            content.appendChild(infoRow);
            const readonlyNote = dom.createElement('p', { style: 'color:#888; margin-bottom: 16px;' }, ['This is a built‑in section and cannot be renamed or deleted.']);
            content.appendChild(readonlyNote);
        } else {
            const formRow1 = dom.createElement('div', { class: 'form-row' });
            const label1 = dom.createElement('label', {}, ['Section Name']);
            const input = dom.createElement('input', { id: 'editSectionName', type: 'text', value: item.name });
            formRow1.appendChild(label1);
            formRow1.appendChild(input);
            content.appendChild(formRow1);
        }
        const formRow2 = dom.createElement('div', { class: 'form-row' });
        const label2 = dom.createElement('label', {}, ['Groups in this section']);
        const ul = dom.createElement('ul', { class: 'section-group-list' });
        ul.innerHTML = groupsHtml;
        formRow2.appendChild(label2);
        formRow2.appendChild(ul);
        content.appendChild(formRow2);
        
        const modalId = modal.show({
            title: item.isUncategorized ? 'Uncategorized Section' : 'Edit Section',
            content: content,
            actions: [
                { label: 'Close', variant: 'cancel', onClick: () => modal.close(modalId), close: false },
                ...(item.isUncategorized ? [] : [{
                    label: 'Save',
                    variant: 'save',
                    close: false,
                    onClick: async () => {
                        const modalEl = document.getElementById(modalId);
                        if (!modalEl) return;
                        const newName = modalEl.querySelector('#editSectionName').value.trim();
                        if (!newName || newName.toLowerCase() === 'uncategorized') {
                            error.alert('Invalid section name');
                            return;
                        }
                        if (newName !== item.name) {
                            try {
                                const result = await api.put(`/api/models/${state.get('currentModel')}/sections/${item.name}`, { new_name: newName });
                                if (result.sections) state.set('sections', result.sections);
                                await this.load();
                                await window.managers.groups.load();
                                modal.close(modalId);
                            } catch (err) {
                                error.alert(err.message);
                            }
                        } else {
                            modal.close(modalId);
                        }
                    }
                }])
            ],
            size: 'medium',
            closable: false,
        });
        
        setTimeout(() => {
            document.querySelectorAll('.edit-group-from-section').forEach(btn => {
                btn.addEventListener('click', async (e) => {
                    const groupId = parseInt(btn.dataset.groupId);
                    const index = state.get('groups').findIndex(g => g.id === groupId);
                    if (index !== -1) {
                        await window.managers.groups.openEditModal(state.get('groups')[index], index);
                        modal.close(modalId);
                    }
                });
            });
            document.querySelectorAll('.delete-group-from-section').forEach(btn => {
                btn.addEventListener('click', async (e) => {
                    const groupId = parseInt(btn.dataset.groupId);
                    const confirmed = await modal.confirm('Delete this group?');
                    if (confirmed) {
                        const index = state.get('groups').findIndex(g => g.id === groupId);
                        if (index !== -1) {
                            try {
                                await api.delete(`/api/models/${state.get('currentModel')}/groups/${index}`);
                                await window.managers.groups.load();
                                await this.load();
                                modal.close(modalId);
                                this.openEditModal(item);
                            } catch (err) {
                                error.alert(err.message);
                            }
                        }
                    }
                });
            });
        }, 100);
    }
    
    async performDelete(item) {
        if (item.isUncategorized) {
            error.alert('The "Uncategorized" section cannot be deleted.');
            return;
        }
        const groupsUsing = state.get('groups').filter(g => g.section_id === item.id).length;
        const otherSections = this.originalData.filter(s => s.id !== item.id && !s.isUncategorized).map(s => s.name);
        const action = await this.showDeleteOptions(groupsUsing, otherSections);
        if (!action) return;
        let url = `/api/models/${state.get('currentModel')}/sections/${item.name}?action=${action.action}`;
        if (action.target) url += `&target=${action.target}`;
        try {
            const result = await api.delete(url);
            if (result.sections) state.set('sections', result.sections);
            await this.load();
            await window.managers.groups.load();
        } catch (err) {
            error.alert(err.message);
        }
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
                    { label: 'Cancel', variant: 'cancel', onClick: () => resolve(null), close: false },
                    { label: 'Delete', variant: 'save', onClick: () => {
                        const selectedAction = document.querySelector('input[name="deleteAction"]:checked').value;
                        const target = selectedAction === 'move' ? document.getElementById('moveTarget').value : null;
                        resolve({ action: selectedAction, target });
                    }, close: false },
                ],
                size: 'medium',
                closable: false,
            });
        });
    }
}
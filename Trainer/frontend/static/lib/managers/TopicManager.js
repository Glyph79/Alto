import { BaseManager, naturalCompare } from './BaseManager.js';
import { state } from '../core/state.js';
import { api } from '../core/api.js';
import { modal } from '../ui/modal.js';
import { dom } from '../core/dom.js';
import events from '../core/events.js';
import { error } from '../ui/error.js';
import { modalLock } from '../ui/modalLock.js';

export class TopicManager extends BaseManager {
    constructor() {
        super('topics', {
            apiPath: () => `/api/models/${state.get('currentModel')}/topics`,
            itemsKey: 'topics',
            nameField: 'name',
            searchFields: ['name'],
            sortSelectors: {
                'name-asc': (a, b) => naturalCompare(a.name, b.name),
                'name-desc': (a, b) => naturalCompare(b.name, a.name),
                'usage-desc': (a, b) => b.count - a.count,
                'usage-asc': (a, b) => a.count - b.count,
            },
            defaultSort: 'name-asc',
            gridContainerId: 'topicsGridContainer',
            emptyStateDivId: 'noTopicsEmptyState',
        });
        // Refresh topics whenever groups change (counts may update)
        events.on('state:groups:changed', () => this.refresh());
    }
    
    async fetchPage(offset, limit) {
        const url = `${this.getApiPath()}?limit=${limit}&offset=${offset}`;
        const response = await api.get(url);
        return {
            items: response.topics,
            total: response.total
        };
    }
    
    async load(reset = true) {
        await super.load(reset);
        // After loading, update global topics state with the transformed items
        // but only the real topics (excluding the pseudo "(No Topic)")
        state.set('topics', this.allItems.filter(t => !t.isNoTopic).map(t => ({ id: t.id, name: t.name })));
    }
    
    transformData(rawTopics) {
        const groups = state.get('groups') || [];
        // Count groups per topic name
        const counts = {};
        groups.forEach(g => {
            const topicName = g.topic || '';
            if (topicName) {
                counts[topicName] = (counts[topicName] || 0) + 1;
            } else {
                counts['(No Topic)'] = (counts['(No Topic)'] || 0) + 1;
            }
        });
        
        // Build the list: first the pseudo "(No Topic)" item, then each real topic
        const items = [];
        items.push({ id: null, name: '(No Topic)', count: counts['(No Topic)'] || 0, isNoTopic: true });
        rawTopics.forEach(topic => {
            items.push({ id: topic.id, name: topic.name, count: counts[topic.name] || 0, isNoTopic: false });
        });
        return items;
    }
    
    renderItem(item, idx) {
        const name = item.name || 'Unnamed Topic';
        const hue = item.isNoTopic ? 0 : (name.split('').reduce((acc, char) => acc + char.charCodeAt(0), 0) * 7) % 360;
        return `
            <div class="topic-card" data-card-index="${idx}" data-topic-id="${item.id}">
                <div class="header">
                    <div style="display: flex; align-items: center; gap: 4px;">
                        <span class="topic-color-dot" style="background-color: ${item.isNoTopic ? '#888' : `hsl(${hue}, 70%, 60%)`};"></span>
                        <span class="topic-name">${dom.escapeHtml(name)}</span>
                    </div>
                    <div class="card-actions">
                        <button class="card-edit" data-topic-id="${item.id}" title="${item.isNoTopic ? 'View Topic' : 'Edit Topic'}">✎</button>
                        ${!item.isNoTopic ? `<button class="card-delete" data-topic-id="${item.id}" title="Delete Topic">🗑</button>` : ''}
                    </div>
                </div>
                <div class="stats">
                    <span>📊 ${item.count} group${item.count !== 1 ? 's' : ''}</span>
                </div>
            </div>
        `;
    }
    
    async openCreateModal() {
        if (!modalLock.lock('topicModal')) return;
        try {
            let modalId = null;
            const content = dom.createElement('div', {});
            const formRow = dom.createElement('div', { class: 'form-row' });
            const label = dom.createElement('label', {}, ['Topic Name']);
            const input = dom.createElement('input', { id: 'newTopicName', type: 'text', placeholder: 'Topic name', autocomplete: 'off' });
            formRow.appendChild(label);
            formRow.appendChild(input);
            content.appendChild(formRow);
            
            modalId = modal.show({
                title: 'Add Topic',
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
                            let name = modalEl.querySelector('#newTopicName').value.trim();
                            if (!name) name = 'Unnamed Topic';
                            if (name.toLowerCase() === 'null' || name === '(No Topic)') {
                                error.alert(`"${name}" is a reserved name.`);
                                return;
                            }
                            try {
                                await api.post(this.getApiPath(), { topic: name });
                                await this.load(true);
                                await window.managers.groups.load(true); // refresh groups to update topic counts
                                modal.close(modalId);
                                modalLock.unlock('topicModal');
                            } catch (err) {
                                error.alert(err.message);
                            }
                        }
                    },
                ],
                size: 'small',
                closable: false,
            });
        } catch (err) {
            modalLock.unlock('topicModal');
            throw err;
        }
    }
    
    async openEditModal(item) {
        if (item.isNoTopic) {
            if (!modalLock.lock('topicModal')) return;
            try {
                const groupsWithoutTopic = state.get('groups').filter(g => !g.topic);
                let groupsHtml = '';
                if (groupsWithoutTopic.length === 0) {
                    groupsHtml = '<li style="justify-content:center; color:#888;">No groups without a topic</li>';
                } else {
                    groupsHtml = groupsWithoutTopic.map(g => `
                        <li class="group-usage-item" data-group-id="${g.id}">
                            <span class="group-name">${dom.escapeHtml(g.group_name || 'Unnamed')}</span>
                            <div class="group-usage-actions">
                                <button class="edit-group-from-topic" data-group-id="${g.id}" title="Edit Group">✎</button>
                                <button class="delete-group-from-topic" data-group-id="${g.id}" title="Delete Group">🗑</button>
                            </div>
                        </li>
                    `).join('');
                }
                const content = dom.createElement('div', {});
                const infoRow = dom.createElement('div', { class: 'form-row' });
                const infoLabel = dom.createElement('label', {}, ['Topic']);
                const infoValue = dom.createElement('div', { style: 'padding: 8px; background: #2d2d5a; border-radius: 6px;' }, ['(No Topic)']);
                infoRow.appendChild(infoLabel);
                infoRow.appendChild(infoValue);
                content.appendChild(infoRow);
                const readonlyNote = dom.createElement('p', { style: 'color:#888; margin-bottom: 16px;' }, ['This is a pseudo‑topic and cannot be renamed or deleted. It represents groups without a topic.']);
                content.appendChild(readonlyNote);
                const groupsRow = dom.createElement('div', { class: 'form-row' });
                const groupsLabel = dom.createElement('label', {}, ['Groups without a topic']);
                const ul = dom.createElement('ul', { class: 'group-usage-list' });
                ul.innerHTML = groupsHtml;
                groupsRow.appendChild(groupsLabel);
                groupsRow.appendChild(ul);
                content.appendChild(groupsRow);
                const modalId = modal.show({
                    title: '(No Topic)',
                    content: content,
                    actions: [{ label: 'Close', variant: 'cancel', onClick: () => { modal.close(modalId); modalLock.unlock('topicModal'); }, close: false }],
                    size: 'medium',
                    closable: false,
                });
                setTimeout(() => {
                    document.querySelectorAll('.edit-group-from-topic').forEach(btn => {
                        btn.addEventListener('click', async (e) => {
                            const groupId = parseInt(btn.dataset.groupId);
                            const index = state.get('groups').findIndex(g => g.id === groupId);
                            if (index !== -1) {
                                await window.managers.groups.openEditModal(state.get('groups')[index], index);
                                modal.close(modalId);
                                modalLock.unlock('topicModal');
                            }
                        });
                    });
                    document.querySelectorAll('.delete-group-from-topic').forEach(btn => {
                        btn.addEventListener('click', async (e) => {
                            const groupId = parseInt(btn.dataset.groupId);
                            const confirmed = await modal.confirm('Delete this group?');
                            if (confirmed) {
                                const index = state.get('groups').findIndex(g => g.id === groupId);
                                if (index !== -1) {
                                    try {
                                        await api.delete(`/api/models/${state.get('currentModel')}/groups/${index}`);
                                        await window.managers.groups.load(true);
                                        await this.load(true);
                                        modal.close(modalId);
                                        modalLock.unlock('topicModal');
                                    } catch (err) {
                                        error.alert(err.message);
                                    }
                                }
                            }
                        });
                    });
                }, 100);
            } catch (err) {
                modalLock.unlock('topicModal');
                throw err;
            }
            return;
        }
        
        if (!modalLock.lock('topicModal')) return;
        try {
            const groupsUsing = await api.get(`/api/models/${state.get('currentModel')}/topics/${item.name}/groups`);
            const groupsHtml = this.renderGroupsList(groupsUsing.groups || [], item.name);
            const content = dom.createElement('div', {});
            const formRow1 = dom.createElement('div', { class: 'form-row' });
            const label1 = dom.createElement('label', {}, ['Topic Name']);
            const input = dom.createElement('input', { id: 'editTopicName', type: 'text', value: item.name });
            formRow1.appendChild(label1);
            formRow1.appendChild(input);
            content.appendChild(formRow1);
            const formRow2 = dom.createElement('div', { class: 'form-row' });
            const label2 = dom.createElement('label', {}, ['Groups using this topic']);
            const ul = dom.createElement('ul', { class: 'group-usage-list', id: 'topicGroupList' });
            ul.innerHTML = groupsHtml;
            formRow2.appendChild(label2);
            formRow2.appendChild(ul);
            content.appendChild(formRow2);
            const modalId = modal.show({
                title: 'Edit Topic',
                content: content,
                actions: [
                    { label: 'Close', variant: 'cancel', onClick: () => { modal.close(modalId); modalLock.unlock('topicModal'); }, close: false },
                    {
                        label: 'Save',
                        variant: 'save',
                        close: false,
                        onClick: async () => {
                            const modalEl = document.getElementById(modalId);
                            if (!modalEl) return;
                            const newName = modalEl.querySelector('#editTopicName').value.trim();
                            if (!newName || newName.toLowerCase() === 'null' || newName === '(No Topic)') {
                                error.alert('Invalid topic name');
                                return;
                            }
                            if (newName !== item.name) {
                                try {
                                    await api.put(`/api/models/${state.get('currentModel')}/topics/${item.name}`, { new_name: newName });
                                    await this.load(true);
                                    await window.managers.groups.load(true);
                                    modal.close(modalId);
                                    modalLock.unlock('topicModal');
                                } catch (err) {
                                    error.alert(err.message);
                                }
                            } else {
                                modal.close(modalId);
                                modalLock.unlock('topicModal');
                            }
                        }
                    },
                ],
                size: 'medium',
                closable: false,
            });
            setTimeout(() => this.attachGroupHandlers(item.name), 100);
        } catch (err) {
            modalLock.unlock('topicModal');
            throw err;
        }
    }
    
    renderGroupsList(groups, topic) {
        if (!groups.length) return '<li style="justify-content:center; color:#888;">No groups use this topic</li>';
        return groups.map(g => `
            <li class="group-usage-item" data-group-id="${g.id}">
                <span class="group-name">${dom.escapeHtml(g.group_name || 'Unnamed')}</span>
                <div class="group-usage-actions">
                    <button class="edit-group-from-topic" data-group-id="${g.id}" title="Edit Group">✎</button>
                    <button class="delete-group-from-topic" data-group-id="${g.id}" title="Delete Group">🗑</button>
                </div>
            </li>
        `).join('');
    }
    
    attachGroupHandlers(topic) {
        document.querySelectorAll('.edit-group-from-topic').forEach(btn => {
            btn.addEventListener('click', async (e) => {
                const groupId = parseInt(btn.dataset.groupId);
                const index = state.get('groups').findIndex(g => g.id === groupId);
                if (index !== -1) {
                    await window.managers.groups.openEditModal(state.get('groups')[index], index);
                    await this.load(true);
                }
            });
        });
        document.querySelectorAll('.delete-group-from-topic').forEach(btn => {
            btn.addEventListener('click', async (e) => {
                const groupId = parseInt(btn.dataset.groupId);
                const confirmed = await modal.confirm('Delete this group?');
                if (confirmed) {
                    const index = state.get('groups').findIndex(g => g.id === groupId);
                    if (index !== -1) {
                        try {
                            await api.delete(`/api/models/${state.get('currentModel')}/groups/${index}`);
                            await window.managers.groups.load(true);
                            await this.load(true);
                        } catch (err) {
                            error.alert(err.message);
                        }
                    }
                }
            });
        });
    }
    
    async performDelete(item) {
        if (item.isNoTopic) {
            error.alert('The "(No Topic)" pseudo‑topic cannot be deleted.');
            return;
        }
        const groupsUsingCount = state.get('groups').filter(g => g.topic === item.name).length;
        let action = 'reassign';
        let target = null;
        if (groupsUsingCount > 0) {
            const otherTopics = state.get('topics').filter(t => t.name !== item.name);
            const result = await this.showDeleteOptions(groupsUsingCount, otherTopics);
            if (!result) return;
            action = result.action;
            target = result.target;
        }
        let url = `/api/models/${state.get('currentModel')}/topics/${item.name}?action=${action}`;
        if (target) url += `&target=${target}`;
        try {
            await api.delete(url);
            await this.load(true);
            await window.managers.groups.load(true);
        } catch (err) {
            error.alert(err.message);
        }
    }
    
    showDeleteOptions(count, otherTopics) {
        return new Promise((resolve) => {
            const optionsHtml = otherTopics.map(t => `<option value="${t.name}">${dom.escapeHtml(t.name)}</option>`).join('');
            const content = dom.createElement('div', {}, [
                dom.createElement('p', {}, [`Topic is used by ${count} group(s).`]),
                dom.createElement('div', { style: 'margin: 20px 0;' }, [
                    dom.createElement('label', {}, [
                        dom.createElement('input', { type: 'radio', name: 'deleteAction', value: 'reassign', checked: true }),
                        ' Reassign groups to: ',
                        dom.createElement('select', { id: 'reassignTarget' }, optionsHtml),
                    ]),
                    dom.createElement('br', {}),
                    dom.createElement('label', {}, [
                        dom.createElement('input', { type: 'radio', name: 'deleteAction', value: 'delete_groups' }),
                        ' Delete all groups using this topic',
                    ]),
                ]),
            ]);
            modal.show({
                title: 'Delete Topic',
                content,
                actions: [
                    { label: 'Cancel', variant: 'cancel', onClick: () => resolve(null), close: false },
                    { label: 'Delete', variant: 'save', onClick: () => {
                        const action = document.querySelector('input[name="deleteAction"]:checked').value;
                        const target = action === 'reassign' ? document.getElementById('reassignTarget').value : null;
                        resolve({ action, target });
                    }, close: false },
                ],
                size: 'medium',
                closable: false,
            });
        });
    }
}
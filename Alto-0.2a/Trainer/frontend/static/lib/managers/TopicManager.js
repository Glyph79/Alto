import { BaseManager } from './BaseManager.js';
import { state } from '../core/state.js';
import { api } from '../core/api.js';
import { modal } from '../ui/modal.js';
import { dom } from '../core/dom.js';
import events from '../core/events.js';
import { error } from '../ui/error.js';

export class TopicManager extends BaseManager {
    constructor() {
        super('topics', {
            apiPath: () => `/api/models/${state.get('currentModel')}/topics`,
            nameField: 'topic',
            searchFields: ['topic'],
            sortSelectors: {
                'name-asc': (a, b) => a.topic.localeCompare(b.topic),
                'name-desc': (a, b) => b.topic.localeCompare(a.topic),
                'usage-desc': (a, b) => b.count - a.count,
                'usage-asc': (a, b) => a.count - b.count,
            },
            defaultSort: 'name-asc',
            gridContainerId: 'topicsGridContainer',
            emptyStateDivId: 'noTopicsEmptyState',
        });
        events.on('groups:updated', () => this.refresh());
    }
    
    async fetchData() {
        const groups = state.get('groups');
        const groupCounts = {};
        groups.forEach(g => {
            const topic = g.topic;
            if (topic) groupCounts[topic] = (groupCounts[topic] || 0) + 1;
        });
        const noTopicCount = groups.filter(g => !g.topic).length;
        const topicsList = state.get('topics') || [];
        const items = [];
        items.push({ topic: '(No Topic)', count: noTopicCount, isNoTopic: true });
        topicsList.forEach(topic => {
            items.push({ topic, count: groupCounts[topic] || 0, isNoTopic: false });
        });
        return items;
    }
    
    transformData(raw) {
        return raw;
    }
    
    renderItem(item, idx) {
        const hue = item.isNoTopic ? 0 : (item.topic.split('').reduce((acc, char) => acc + char.charCodeAt(0), 0) * 7) % 360;
        return `
            <div class="topic-card" data-card-index="${idx}" data-topic="${dom.escapeHtml(item.topic)}">
                <div class="header">
                    <div style="display: flex; align-items: center; gap: 4px;">
                        <span class="topic-color-dot" style="background-color: ${item.isNoTopic ? '#888' : `hsl(${hue}, 70%, 60%)`};"></span>
                        <span class="topic-name">${dom.escapeHtml(item.topic)}</span>
                    </div>
                    <div class="card-actions">
                        <button class="card-edit" data-topic="${dom.escapeHtml(item.topic)}" title="${item.isNoTopic ? 'View Topic' : 'Edit Topic'}">✎</button>
                        ${!item.isNoTopic ? `<button class="card-delete" data-topic="${dom.escapeHtml(item.topic)}" title="Delete Topic">🗑</button>` : ''}
                    </div>
                </div>
                <div class="stats">
                    <span>📊 ${item.count} group${item.count !== 1 ? 's' : ''}</span>
                </div>
            </div>
        `;
    }
    
    async openCreateModal() {
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
                        const name = document.getElementById('newTopicName').value.trim();
                        if (!name) {
                            error.alert('Topic name is required.');
                            return;
                        }
                        if (name.toLowerCase() === 'null' || name === '(No Topic)') {
                            error.alert(`"${name}" is a reserved name.`);
                            return;
                        }
                        try {
                            await api.post(this.getApiPath(), { topic: name });
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
        if (item.isNoTopic) {
            // Read-only modal for (No Topic)
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
                actions: [
                    { label: 'Close', variant: 'cancel', onClick: () => modal.close(modalId), close: false },
                ],
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
                                    await window.managers.groups.load();
                                    await this.load();
                                    modal.close(modalId);
                                } catch (err) {
                                    error.alert(err.message);
                                }
                            }
                        }
                    });
                });
            }, 100);
            return;
        }
        
        // Normal editable topic
        const groupsUsing = await api.get(`/api/models/${state.get('currentModel')}/topics/${item.topic}/groups`);
        const groupsHtml = this.renderGroupsList(groupsUsing.groups || [], item.topic);
        
        const content = dom.createElement('div', {});
        
        const formRow1 = dom.createElement('div', { class: 'form-row' });
        const label1 = dom.createElement('label', {}, ['Topic Name']);
        const input = dom.createElement('input', { id: 'editTopicName', type: 'text', value: item.topic });
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
                { label: 'Close', variant: 'cancel', onClick: () => modal.close(modalId), close: false },
                { 
                    label: 'Save', 
                    variant: 'save', 
                    close: false,
                    onClick: async () => {
                        const newName = document.getElementById('editTopicName').value.trim();
                        if (!newName || newName.toLowerCase() === 'null' || newName === '(No Topic)') {
                            error.alert('Invalid topic name');
                            return;
                        }
                        if (newName !== item.topic) {
                            try {
                                await api.put(`/api/models/${state.get('currentModel')}/topics/${item.topic}`, { new_name: newName });
                                await this.load();
                                modal.close(modalId);
                            } catch (err) {
                                error.alert(err.message);
                            }
                        } else {
                            modal.close(modalId);
                        }
                    }
                },
            ],
            size: 'medium',
            closable: false,
        });
        
        setTimeout(() => this.attachGroupHandlers(item.topic), 100);
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
                    await this.load();
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
                            await window.managers.groups.load();
                            await this.load();
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
        const groupsUsingCount = state.get('groups').filter(g => g.topic === item.topic).length;
        let action = 'reassign';
        let target = null;
        if (groupsUsingCount > 0) {
            const otherTopics = state.get('topics').filter(t => t !== item.topic);
            const result = await this.showDeleteOptions(groupsUsingCount, otherTopics);
            if (!result) return;
            action = result.action;
            target = result.target;
        }
        let url = `/api/models/${state.get('currentModel')}/topics/${item.topic}?action=${action}`;
        if (target) url += `&target=${target}`;
        try {
            await api.delete(url);
            await this.load();
            await window.managers.groups.load();
        } catch (err) {
            error.alert(err.message);
        }
    }
    
    showDeleteOptions(count, otherTopics) {
        return new Promise((resolve) => {
            const optionsHtml = otherTopics.map(t => `<option value="${dom.escapeHtml(t)}">${dom.escapeHtml(t)}</option>`).join('');
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
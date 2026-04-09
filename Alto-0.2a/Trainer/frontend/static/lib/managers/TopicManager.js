// lib/managers/TopicManager.js
import { BaseManager } from './BaseManager.js';
import { state } from '../core/state.js';
import { api } from '../core/api.js';
import { modal } from '../ui/modal.js';
import { dom } from '../core/dom.js';
import events from '../core/events.js';

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
                        <button class="card-edit" data-topic="${dom.escapeHtml(item.topic)}" title="Edit">✎</button>
                        ${!item.isNoTopic ? `<button class="card-delete" data-topic="${dom.escapeHtml(item.topic)}" title="Delete">🗑</button>` : ''}
                    </div>
                </div>
                <div class="stats">
                    <span>📊 ${item.count} group${item.count !== 1 ? 's' : ''}</span>
                </div>
            </div>
        `;
    }
    
    async openCreateModal() {
        const name = await modal.prompt('Add Topic', '', { placeholder: 'Topic name' });
        if (!name) return;
        if (name.toLowerCase() === 'null' || name === '(No Topic)') {
            modal.show({ title: 'Error', content: `"${name}" is a reserved name.`, actions: [{ label: 'OK' }], size: 'small' });
            return;
        }
        try {
            await api.post(this.getApiPath(), { topic: name });
            await this.load();
        } catch (err) {
            modal.show({ title: 'Error', content: err.message, actions: [{ label: 'OK' }], size: 'small' });
        }
    }
    
    async openEditModal(item) {
        if (item.isNoTopic) {
            modal.show({ title: '(No Topic)', content: 'This pseudo-topic cannot be edited.', actions: [{ label: 'OK' }], size: 'small' });
            return;
        }
        const groupsUsing = await api.get(`/api/models/${state.get('currentModel')}/topics/${item.topic}/groups`);
        const groupsHtml = this.renderGroupsList(groupsUsing.groups || [], item.topic);
        const content = dom.createElement('div', {}, [
            dom.createElement('div', { class: 'form-row' }, [
                dom.createElement('label', {}, ['Topic Name']),
                dom.createElement('input', { id: 'editTopicName', type: 'text', value: item.topic }),
            ]),
            dom.createElement('div', { class: 'form-row' }, [
                dom.createElement('label', {}, ['Groups using this topic']),
                dom.createElement('ul', { class: 'group-usage-list', id: 'topicGroupList' }, [groupsHtml]),
            ]),
        ]);
        const modalId = modal.show({
            title: 'Edit Topic',
            content,
            actions: [
                { label: 'Close', variant: 'cancel', onClick: () => modal.close(modalId) },
                { label: 'Save', variant: 'save', onClick: async () => {
                    const newName = document.getElementById('editTopicName').value.trim();
                    if (!newName || newName.toLowerCase() === 'null' || newName === '(No Topic)') {
                        modal.show({ title: 'Error', content: 'Invalid topic name', actions: [{ label: 'OK' }], size: 'small' });
                        return;
                    }
                    if (newName !== item.topic) {
                        await api.put(`/api/models/${state.get('currentModel')}/topics/${item.topic}`, { new_name: newName });
                        await this.load();
                    }
                    modal.close(modalId);
                } },
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
                        await api.delete(`/api/models/${state.get('currentModel')}/groups/${index}`);
                        await window.managers.groups.load();
                        await this.load();
                    }
                }
            });
        });
    }
    
    async performDelete(item) {
        if (item.isNoTopic) return;
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
        await api.delete(url);
        await this.load();
        await window.managers.groups.load();
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
                    { label: 'Cancel', variant: 'cancel', onClick: () => resolve(null) },
                    { label: 'Delete', variant: 'save', onClick: () => {
                        const action = document.querySelector('input[name="deleteAction"]:checked').value;
                        const target = action === 'reassign' ? document.getElementById('reassignTarget').value : null;
                        resolve({ action, target });
                    } },
                ],
                size: 'medium',
                closable: false,
            });
        });
    }
}
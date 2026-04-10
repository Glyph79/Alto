import { BaseManager } from './BaseManager.js';
import { state } from '../core/state.js';
import { api } from '../core/api.js';
import { modal } from '../ui/modal.js';
import { loading } from '../ui/loading.js';
import { retryUI } from '../ui/retry.js';
import { dom } from '../core/dom.js';
import { ListEditor } from '../../components/ListEditor.js';
import { TreeEditor } from '../../components/TreeEditor.js';
import { error } from '../ui/error.js';

export class GroupManager extends BaseManager {
    constructor() {
        super('groups', {
            apiPath: () => `/api/models/${state.get('currentModel')}/groups`,
            nameField: 'group_name',
            searchFields: ['group_name', 'group_description'],
            sortSelectors: {
                'name-asc': (a, b) => (a.group_name || '').localeCompare(b.group_name || ''),
                'name-desc': (a, b) => (b.group_name || '').localeCompare(a.group_name || ''),
                'questions-desc': (a, b) => (b.question_count || 0) - (a.question_count || 0),
                'questions-asc': (a, b) => (a.question_count || 0) - (b.question_count || 0),
                'answers-desc': (a, b) => (b.answer_count || 0) - (a.answer_count || 0),
                'answers-asc': (a, b) => (a.answer_count || 0) - (b.answer_count || 0),
            },
            defaultSort: 'name-asc',
            gridContainerId: 'groupsGridContainer',
            emptyStateDivId: 'noGroupsEmptyState',
        });
        this.currentGroupIndex = null;
        this.modalGroupCopy = null;
        this.questionEditor = null;
        this.answerEditor = null;
        this._topicFilter = '';
    }
    
    setTopicFilter(topic) {
        this._topicFilter = topic;
        this._applyFiltersAndSort();
    }
    
    _applyCustomFilters(items) {
        if (!this._topicFilter) return items;
        if (this._topicFilter === '__NO_TOPIC__') {
            return items.filter(item => !item.topic);
        }
        return items.filter(item => item.topic === this._topicFilter);
    }
    
    async fetchData() {
        const data = await api.get(`${this.getApiPath()}/summaries`);
        if (data.sections) state.set('sections', data.sections);
        return data.groups || [];
    }
    
    transformData(raw) {
        return raw;
    }
    
    // Override load to update state.groups
    async load() {
        await super.load(); // this sets this.originalData and this.displayData
        // Update global state with groups for sections/topics to use
        state.set('groups', this.originalData);
    }
    
    renderItem(group, idx) {
        return `
            <div class="group-card" data-card-index="${idx}" data-group-id="${group.id}">
                <div class="header">
                    <span class="section-badge">${dom.escapeHtml(group.section || 'Uncategorized')}</span>
                    <div class="card-actions">
                        <button class="card-edit" data-group-id="${group.id}" title="Edit">✎</button>
                        <button class="card-delete" data-group-id="${group.id}" title="Delete">🗑</button>
                    </div>
                </div>
                <h4>${dom.escapeHtml(group.group_name || 'Unnamed')}</h4>
                <div class="description">${dom.escapeHtml(group.group_description || '')}</div>
                <div class="stats">
                    <span>❓ ${group.question_count || 0} question${group.question_count !== 1 ? 's' : ''}</span>
                    <span>💬 ${group.answer_count || 0} answer${group.answer_count !== 1 ? 's' : ''}</span>
                </div>
            </div>
        `;
    }
    
    async openCreateModal() {
        await this.openGroupModal(null);
    }
    
    async openEditModal(group, index) {
        if (index !== undefined && index !== null) {
            await this.openGroupModal(index);
        } else {
            const foundIndex = this.originalData.findIndex(g => g.id === group.id);
            if (foundIndex !== -1) await this.openGroupModal(foundIndex);
        }
    }
    
    async openGroupModal(index) {
        this.currentGroupIndex = index;
        const isNew = (index === null);
        
        const modalId = modal.show({
            title: isNew ? 'Create Group' : 'Edit Group',
            content: this.buildModalContent(),
            actions: [
                { label: 'Cancel', variant: 'cancel', onClick: () => this.closeGroupModal(), close: false },
                { label: 'Save Changes', variant: 'save', close: false, onClick: () => this.saveGroup() },
            ],
            size: 'medium',
            closable: false,
        });
        this.modalId = modalId;
        
        const modalContent = document.querySelector(`#${modalId} .modal-content`);
        if (window.disableButtonsInContainer) window.disableButtonsInContainer(modalContent);
        await this.ensureTopicsAndSections();
        
        if (isNew) {
            this.modalGroupCopy = {
                group_name: '',
                group_description: '',
                topic: '',
                section: '',
                fallback: '',
                questions: [],
                answers: [],
            };
            this.populateForm();
            this.initEditors();
            if (window.enableButtonsInContainer) window.enableButtonsInContainer(modalContent);
        } else {
            try {
                const idx = parseInt(index, 10);
                if (isNaN(idx)) throw new Error('Invalid group index');
                const fullGroup = await api.get(`${this.getApiPath()}/${idx}/full`);
                this.modalGroupCopy = fullGroup;
                this.populateForm();
                this.initEditors();
                if (window.enableButtonsInContainer) window.enableButtonsInContainer(modalContent);
            } catch (err) {
                retryUI.show(modalContent, `Failed to load group: ${err.message}`, () => this.openGroupModal(index));
            }
        }
    }
    
    buildModalContent() {
        const div = dom.createElement('div', {});
        div.innerHTML = `
            <div class="form-row">
                <label>Group Name</label>
                <input type="text" id="modalGroupName">
            </div>
            <div class="form-row">
                <label>Description</label>
                <input type="text" id="modalGroupDesc">
            </div>
            <div class="form-row" style="display: flex; gap: 16px;">
                <div style="flex:1;">
                    <label>Topic</label>
                    <select id="modalGroupTopic"></select>
                </div>
                <div style="flex:1;">
                    <label>Section</label>
                    <select id="modalGroupSection"></select>
                </div>
            </div>
            <div class="form-row">
                <label>Fallback (custom default response)</label>
                <select id="modalGroupFallback"></select>
            </div>
            <div class="qa-section">
                <h3>Questions</h3>
                <div id="modalQuestionsContainer"></div>
            </div>
            <div class="qa-section">
                <h3>Answers</h3>
                <div id="modalAnswersContainer"></div>
            </div>
            <div style="margin-top:16px;">
                <button id="modalEditFollowupsBtn" class="tree-btn" style="background:#a78bfa; color:white; border:none; padding:10px; border-radius:6px; width:100%;">🌳 Edit Follow-up Tree</button>
            </div>
        `;
        return div;
    }
    
    populateForm() {
        document.getElementById('modalGroupName').value = this.modalGroupCopy.group_name || '';
        document.getElementById('modalGroupDesc').value = this.modalGroupCopy.group_description || '';
        
        const topicSelect = document.getElementById('modalGroupTopic');
        let topicOptions = '<option value="">(No Topic)</option>';
        (state.get('topics') || []).forEach(t => {
            topicOptions += `<option value="${dom.escapeHtml(t)}">${dom.escapeHtml(t)}</option>`;
        });
        topicSelect.innerHTML = topicOptions;
        topicSelect.value = this.modalGroupCopy.topic || '';
        
        const sectionSelect = document.getElementById('modalGroupSection');
        let sectionOptions = '<option value="">(Uncategorized)</option>';
        (state.get('sections') || []).forEach(s => {
            sectionOptions += `<option value="${dom.escapeHtml(s)}">${dom.escapeHtml(s)}</option>`;
        });
        sectionSelect.innerHTML = sectionOptions;
        sectionSelect.value = this.modalGroupCopy.section || '';
        
        const fallbackSelect = document.getElementById('modalGroupFallback');
        let fbOptions = '<option value="">(None)</option>';
        (state.get('fallbacks') || []).forEach(fb => {
            fbOptions += `<option value="${dom.escapeHtml(fb.name)}">${dom.escapeHtml(fb.name)}</option>`;
        });
        fallbackSelect.innerHTML = fbOptions;
        fallbackSelect.value = this.modalGroupCopy.fallback || '';
    }
    
    initEditors() {
        const questionsContainer = document.getElementById('modalQuestionsContainer');
        const answersContainer = document.getElementById('modalAnswersContainer');
        if (this.questionEditor) this.questionEditor.destroy();
        if (this.answerEditor) this.answerEditor.destroy();
        
        this.questionEditor = new ListEditor({
            container: questionsContainer,
            items: this.modalGroupCopy.questions || [],
            placeholder: 'Question',
            onAdd: (val) => { this.modalGroupCopy.questions.push(val); },
            onEdit: (idx, oldVal, newVal) => { this.modalGroupCopy.questions[idx] = newVal; },
            onDelete: (idx) => { this.modalGroupCopy.questions.splice(idx, 1); },
        });
        this.answerEditor = new ListEditor({
            container: answersContainer,
            items: this.modalGroupCopy.answers || [],
            placeholder: 'Answer',
            onAdd: (val) => { this.modalGroupCopy.answers.push(val); },
            onEdit: (idx, oldVal, newVal) => { this.modalGroupCopy.answers[idx] = newVal; },
            onDelete: (idx) => { this.modalGroupCopy.answers.splice(idx, 1); },
        });
        
        const followupsBtn = document.getElementById('modalEditFollowupsBtn');
        if (followupsBtn) {
            followupsBtn.onclick = () => this.openTreeEditor();
        }
    }
    
    async openTreeEditor() {
        if (this.currentGroupIndex === null) {
            modal.show({
                title: 'Cannot Edit Tree',
                content: 'Please save the group first before editing the follow-up tree.',
                actions: [{ label: 'OK', variant: 'cancel' }],
                size: 'small',
            });
            return;
        }
        const treeEditor = new TreeEditor({
            groupIndex: this.currentGroupIndex,
            onSave: async (treeData) => {
                await api.put(`${this.getApiPath()}/${this.currentGroupIndex}/followups`, treeData);
                this.modalGroupCopy.follow_ups = treeData;
            },
        });
        await treeEditor.open();
    }
    
    async saveGroup() {
        this.modalGroupCopy.group_name = document.getElementById('modalGroupName').value;
        this.modalGroupCopy.group_description = document.getElementById('modalGroupDesc').value;
        this.modalGroupCopy.topic = document.getElementById('modalGroupTopic').value;
        this.modalGroupCopy.section = document.getElementById('modalGroupSection').value;
        this.modalGroupCopy.fallback = document.getElementById('modalGroupFallback').value;
        this.modalGroupCopy.questions = this.questionEditor.getItems();
        this.modalGroupCopy.answers = this.answerEditor.getItems();
        
        try {
            if (this.currentGroupIndex === null) {
                await api.post(this.getApiPath(), this.modalGroupCopy);
            } else {
                await api.put(`${this.getApiPath()}/${this.currentGroupIndex}`, this.modalGroupCopy);
            }
            await this.load(); // this will update state.groups
            await window.managers.topics?.load();
            await window.managers.sections?.load();
            this.closeGroupModal();
        } catch (err) {
            error.alert(`Save failed: ${err.message}`);
        }
    }
    
    closeGroupModal() {
        if (this.questionEditor) this.questionEditor.destroy();
        if (this.answerEditor) this.answerEditor.destroy();
        modal.close(this.modalId);
        this.modalGroupCopy = null;
        this.currentGroupIndex = null;
    }
    
    async ensureTopicsAndSections() {
        if (state.get('topics').length === 0 && state.get('currentModel')) {
            try {
                const topics = await api.get(`/api/models/${state.get('currentModel')}/topics`);
                state.set('topics', topics);
            } catch (e) { /* ignore */ }
        }
        if (state.get('sections').length === 0 && state.get('currentModel')) {
            try {
                const info = await api.get(`/api/models/${state.get('currentModel')}`);
                if (info.sections) state.set('sections', info.sections);
            } catch (e) { /* ignore */ }
        }
    }
    
    async performDelete(item, index) {
        if (index === undefined) {
            index = this.originalData.findIndex(g => g.id === item.id);
        }
        if (index === -1) return;
        try {
            await api.delete(`${this.getApiPath()}/${index}`);
            await this.load(); // update state.groups
            await window.managers.topics?.load();
            await window.managers.sections?.load();
        } catch (err) {
            error.alert(err.message);
        }
    }
}
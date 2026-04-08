// components/TreeEditor.js - Follow-up tree editor (extracted from old tree.js)
import { dom } from '../lib/core/dom.js';
import { modal } from '../lib/ui/modal.js';
import { loading } from '../lib/ui/loading.js';
import { retryUI, retryOperation } from '../lib/ui/retry.js';
import { api } from '../lib/core/api.js';
import { state } from '../lib/core/state.js';
import { ListEditor } from './ListEditor.js';

export class TreeEditor {
    constructor(config) {
        this.groupIndex = config.groupIndex;
        this.onSave = config.onSave;
        this.container = config.container || document.createElement('div');
        this.modalId = null;
        this.currentTree = [];
        this.nodeMap = new Map();
        this.nodeDetailsCache = new Map();
        this.nextNodeId = 0;
        this.selectedNodeId = null;
        this.unsaved = false;
        this.fallbackOptions = config.fallbackOptions || [];
    }

    async open() {
        this.modalId = modal.show({
            title: 'Follow-up Tree Editor',
            content: this.buildModalContent(),
            actions: [
                { label: 'Cancel', variant: 'cancel', onClick: () => this.handleCancel() },
                { label: 'Save Tree', variant: 'save', onClick: () => this.handleSave() },
            ],
            size: 'large',
            closable: false,
        });
        await this.loadTree();
    }

    buildModalContent() {
        const wrapper = dom.createElement('div', { class: 'tree-layout' });
        // Left panel: node QA editor
        const leftPanel = dom.createElement('div', { class: 'tree-column' });
        const qaPanel = dom.createElement('div', { id: 'treeQAPanel', class: 'qa-panel', style: 'display:none;' });
        qaPanel.appendChild(dom.createElement('h3', {}, ['Node Questions & Answers']));
        const questionsSection = dom.createElement('div', { class: 'qa-section' });
        questionsSection.appendChild(dom.createElement('h4', {}, ['Questions']));
        const questionsContainer = dom.createElement('div', { id: 'treeQuestionsContainer' });
        questionsSection.appendChild(questionsContainer);
        const answersSection = dom.createElement('div', { class: 'qa-section' });
        answersSection.appendChild(dom.createElement('h4', {}, ['Answers']));
        const answersContainer = dom.createElement('div', { id: 'treeAnswersContainer' });
        answersSection.appendChild(answersContainer);
        qaPanel.appendChild(questionsSection);
        qaPanel.appendChild(answersSection);
        // Fallback select
        const fbRow = dom.createElement('div', { class: 'form-row' });
        fbRow.appendChild(dom.createElement('label', {}, ['Fallback']));
        const fbSelect = dom.createElement('select', { id: 'treeFallbackSelect' });
        fbRow.appendChild(fbSelect);
        qaPanel.appendChild(fbRow);
        leftPanel.appendChild(qaPanel);
        const noNodeMsg = dom.createElement('div', { id: 'noNodeSelectedMsg', class: 'no-node-message' }, ['Select a node to edit its questions and answers.']);
        leftPanel.appendChild(noNodeMsg);
        // Right panel: tree view
        const rightPanel = dom.createElement('div', { class: 'tree-column' });
        const toolbar = dom.createElement('div', { class: 'tree-toolbar' });
        toolbar.appendChild(dom.createElement('button', { id: 'treeAddRootBtn' }, ['+ Add Root']));
        toolbar.appendChild(dom.createElement('button', { id: 'treeAddChildBtn', disabled: true }, ['+ Add Child']));
        toolbar.appendChild(dom.createElement('button', { id: 'treeEditNodeBtn', disabled: true }, ['✎ Edit Name']));
        toolbar.appendChild(dom.createElement('button', { id: 'treeDeleteNodeBtn', disabled: true }, ['🗑 Delete']));
        rightPanel.appendChild(toolbar);
        const treeContainer = dom.createElement('div', { id: 'treeContainer', class: 'tree-container' });
        rightPanel.appendChild(treeContainer);
        wrapper.appendChild(leftPanel);
        wrapper.appendChild(rightPanel);
        return wrapper;
    }

    async loadTree() {
        const treeContainer = document.getElementById('treeContainer');
        const loadingOverlay = loading.overlay(treeContainer, 'Loading tree data...');
        try {
            const treeData = await retryOperation(async () => {
                return await api.get(`/api/models/${state.get('currentModel')}/groups/${this.groupIndex}/followups`);
            });
            this.setData(treeData);
        } catch (err) {
            loadingOverlay.clear();
            retryUI.show(treeContainer, `Failed to load tree: ${err.message}`, () => this.loadTree());
        } finally {
            loadingOverlay.clear();
        }
    }

    setData(treeData) {
        this.currentTree = treeData || [];
        this.nodeMap.clear();
        this.nodeDetailsCache.clear();
        this.nextNodeId = 0;
        const buildMap = (nodes) => {
            nodes.forEach(node => {
                node.dbId = node.id;
                node.id = `node_${this.nextNodeId++}`;
                this.nodeMap.set(node.id, node);
                if (node.children) buildMap(node.children);
            });
        };
        buildMap(this.currentTree);
        this.selectedNodeId = null;
        this.unsaved = false;
        this.renderTree();
        this.updateToolbarButtons();
        this.hideQAPanel();
        this.attachTreeEvents();
        this.updateFallbackDropdown();
    }

    renderTree() {
        const container = document.getElementById('treeContainer');
        if (!container) return;
        container.innerHTML = this.renderNodes(this.currentTree, 0);
        // Attach expand/collapse and selection after rendering
        document.querySelectorAll('.tree-node-header').forEach(header => {
            const nodeId = header.dataset.nodeId;
            const expandIcon = header.querySelector('.expand-icon');
            if (expandIcon) {
                expandIcon.addEventListener('click', (e) => {
                    e.stopPropagation();
                    const childrenDiv = header.parentElement.querySelector('.tree-children');
                    if (childrenDiv) {
                        const isHidden = childrenDiv.style.display === 'none';
                        childrenDiv.style.display = isHidden ? 'block' : 'none';
                        expandIcon.textContent = isHidden ? '▼' : '▶';
                    }
                });
            }
            header.addEventListener('click', (e) => {
                if (e.target.closest('.node-actions')) return;
                this.selectNode(nodeId);
            });
        });
        if (this.selectedNodeId) {
            const selectedHeader = document.querySelector(`.tree-node-header[data-node-id="${this.selectedNodeId}"]`);
            if (selectedHeader) {
                selectedHeader.classList.add('selected');
                this.showNodeQAPanel(this.selectedNodeId);
            } else {
                this.selectedNodeId = null;
                this.hideQAPanel();
            }
        }
    }

    renderNodes(nodes, level) {
        if (!nodes || nodes.length === 0) return '';
        let html = '';
        nodes.forEach(node => {
            const hasChildren = node.children && node.children.length > 0;
            const expandIcon = hasChildren ? '▼' : '';
            html += `<div class="tree-node">`;
            html += `<div class="tree-node-header" data-node-id="${node.id}">`;
            html += `<span class="expand-icon">${expandIcon}</span>`;
            html += `<span class="name">${dom.escapeHtml(node.branch_name || 'Unnamed')}</span>`;
            html += `<span class="node-actions"></span>`;
            html += `</div>`;
            if (hasChildren) {
                html += `<div class="tree-children" style="display:block;">${this.renderNodes(node.children, level+1)}</div>`;
            }
            html += `</div>`;
        });
        return html;
    }

    selectNode(nodeId) {
        if (this.selectedNodeId) {
            const prev = document.querySelector(`.tree-node-header[data-node-id="${this.selectedNodeId}"]`);
            if (prev) prev.classList.remove('selected');
        }
        this.selectedNodeId = nodeId;
        const current = document.querySelector(`.tree-node-header[data-node-id="${this.selectedNodeId}"]`);
        if (current) current.classList.add('selected');
        this.showNodeQAPanel(nodeId);
        this.updateToolbarButtons();
    }

    async showNodeQAPanel(nodeId) {
        const node = this.nodeMap.get(nodeId);
        if (!node) return;
        this.hideQAPanel();
        const qaPanel = document.getElementById('treeQAPanel');
        const noNodeMsg = document.getElementById('noNodeSelectedMsg');
        if (qaPanel) qaPanel.style.display = 'flex';
        if (noNodeMsg) noNodeMsg.style.display = 'none';

        // Update fallback select
        const fbSelect = document.getElementById('treeFallbackSelect');
        if (fbSelect) {
            fbSelect.value = node.fallback || '';
            fbSelect.onchange = (e) => {
                if (this.selectedNodeId) {
                    this.nodeMap.get(this.selectedNodeId).fallback = e.target.value;
                    this.unsaved = true;
                }
            };
        }

        // Initialize ListEditors for questions and answers
        const questionsContainer = document.getElementById('treeQuestionsContainer');
        const answersContainer = document.getElementById('treeAnswersContainer');
        if (!questionsContainer || !answersContainer) return;

        if (node.dbId && !this.nodeDetailsCache.has(nodeId)) {
            const qLoading = loading.inline(questionsContainer, 'Loading questions');
            const aLoading = loading.inline(answersContainer, 'Loading answers');
            try {
                const details = await retryOperation(async () => {
                    return await api.get(`/api/models/${state.get('currentModel')}/groups/${this.groupIndex}/nodes/${node.dbId}`);
                });
                qLoading.clear();
                aLoading.clear();
                node.questions = details.questions;
                node.answers = details.answers;
                this.nodeDetailsCache.set(nodeId, { questions: node.questions, answers: node.answers });
            } catch (err) {
                qLoading.clear();
                aLoading.clear();
                retryUI.showInline(questionsContainer, 'questions', () => this.showNodeQAPanel(nodeId));
                retryUI.showInline(answersContainer, 'answers', () => this.showNodeQAPanel(nodeId));
                return;
            }
        } else if (!node.questions) {
            node.questions = [];
            node.answers = [];
        }

        this.questionEditor = new ListEditor({
            container: questionsContainer,
            items: node.questions,
            placeholder: 'Question',
            onAdd: (val) => { node.questions.push(val); this.unsaved = true; this.nodeDetailsCache.set(nodeId, { questions: node.questions, answers: node.answers }); },
            onEdit: (idx, oldVal, newVal) => { node.questions[idx] = newVal; this.unsaved = true; this.nodeDetailsCache.set(nodeId, { questions: node.questions, answers: node.answers }); },
            onDelete: (idx) => { node.questions.splice(idx, 1); this.unsaved = true; this.nodeDetailsCache.set(nodeId, { questions: node.questions, answers: node.answers }); },
        });
        this.answerEditor = new ListEditor({
            container: answersContainer,
            items: node.answers,
            placeholder: 'Answer',
            onAdd: (val) => { node.answers.push(val); this.unsaved = true; this.nodeDetailsCache.set(nodeId, { questions: node.questions, answers: node.answers }); },
            onEdit: (idx, oldVal, newVal) => { node.answers[idx] = newVal; this.unsaved = true; this.nodeDetailsCache.set(nodeId, { questions: node.questions, answers: node.answers }); },
            onDelete: (idx) => { node.answers.splice(idx, 1); this.unsaved = true; this.nodeDetailsCache.set(nodeId, { questions: node.questions, answers: node.answers }); },
        });
    }

    hideQAPanel() {
        const qaPanel = document.getElementById('treeQAPanel');
        const noNodeMsg = document.getElementById('noNodeSelectedMsg');
        if (qaPanel) qaPanel.style.display = 'none';
        if (noNodeMsg) noNodeMsg.style.display = 'flex';
        if (this.questionEditor) this.questionEditor.destroy();
        if (this.answerEditor) this.answerEditor.destroy();
    }

    updateToolbarButtons() {
        const hasSelection = this.selectedNodeId !== null;
        const addChildBtn = document.getElementById('treeAddChildBtn');
        const editNodeBtn = document.getElementById('treeEditNodeBtn');
        const deleteNodeBtn = document.getElementById('treeDeleteNodeBtn');
        if (addChildBtn) addChildBtn.disabled = !hasSelection;
        if (editNodeBtn) editNodeBtn.disabled = !hasSelection;
        if (deleteNodeBtn) deleteNodeBtn.disabled = !hasSelection;
    }

    attachTreeEvents() {
        const addRootBtn = document.getElementById('treeAddRootBtn');
        const addChildBtn = document.getElementById('treeAddChildBtn');
        const editNodeBtn = document.getElementById('treeEditNodeBtn');
        const deleteNodeBtn = document.getElementById('treeDeleteNodeBtn');
        if (addRootBtn) addRootBtn.onclick = () => this.addRoot();
        if (addChildBtn) addChildBtn.onclick = () => this.addChild();
        if (editNodeBtn) editNodeBtn.onclick = () => this.editNodeName();
        if (deleteNodeBtn) deleteNodeBtn.onclick = () => this.deleteNode();
    }

    addRoot() {
        const newNode = { branch_name: 'New Root', questions: [], answers: [], children: [], fallback: '' };
        newNode.id = `node_${this.nextNodeId++}`;
        this.nodeMap.set(newNode.id, newNode);
        this.currentTree.push(newNode);
        this.unsaved = true;
        this.renderTree();
        this.selectNode(newNode.id);
    }

    addChild() {
        if (!this.selectedNodeId) return;
        const parentNode = this.nodeMap.get(this.selectedNodeId);
        if (!parentNode) return;
        if (!parentNode.children) parentNode.children = [];
        const newNode = { branch_name: 'New Branch', questions: [], answers: [], children: [], fallback: '' };
        newNode.id = `node_${this.nextNodeId++}`;
        this.nodeMap.set(newNode.id, newNode);
        parentNode.children.push(newNode);
        this.unsaved = true;
        this.renderTree();
        this.selectNode(newNode.id);
    }

    async editNodeName() {
        if (!this.selectedNodeId) return;
        const node = this.nodeMap.get(this.selectedNodeId);
        const newName = await modal.prompt('Edit Branch Name', node.branch_name || '', { placeholder: 'Branch name' });
        if (newName && newName.trim()) {
            node.branch_name = newName.trim();
            this.unsaved = true;
            this.renderTree();
        }
    }

    async deleteNode() {
        if (!this.selectedNodeId) return;
        const node = this.nodeMap.get(this.selectedNodeId);
        const confirmed = await modal.confirm(`Delete '${node.branch_name || 'Unnamed'}' and all its children?`);
        if (!confirmed) return;
        const removeNode = (nodes, nodeId) => {
            for (let i = 0; i < nodes.length; i++) {
                if (nodes[i].id === nodeId) {
                    nodes.splice(i, 1);
                    return true;
                }
                if (nodes[i].children && removeNode(nodes[i].children, nodeId)) return true;
            }
            return false;
        };
        removeNode(this.currentTree, this.selectedNodeId);
        this.nodeMap.delete(this.selectedNodeId);
        this.selectedNodeId = null;
        this.unsaved = true;
        this.renderTree();
        this.updateToolbarButtons();
        this.hideQAPanel();
    }

    updateFallbackDropdown() {
        const select = document.getElementById('treeFallbackSelect');
        if (!select) return;
        let options = '<option value="">(None)</option>';
        (state.get('fallbacks') || []).forEach(fb => {
            options += `<option value="${dom.escapeHtml(fb.name)}">${dom.escapeHtml(fb.name)}</option>`;
        });
        select.innerHTML = options;
        if (this.selectedNodeId) {
            const node = this.nodeMap.get(this.selectedNodeId);
            if (node && node.fallback) select.value = node.fallback;
            else select.value = '';
        }
    }

    async handleSave() {
        const buildFullTree = (nodes) => {
            return nodes.map(node => {
                const details = this.nodeDetailsCache.get(node.id) || { questions: node.questions || [], answers: node.answers || [] };
                return {
                    id: node.dbId,
                    branch_name: node.branch_name,
                    questions: details.questions,
                    answers: details.answers,
                    fallback: node.fallback || '',
                    children: buildFullTree(node.children || []),
                };
            });
        };
        const treeToSave = buildFullTree(this.currentTree);
        try {
            await this.onSave(treeToSave);
            this.unsaved = false;
            modal.close(this.modalId);
        } catch (err) {
            const treeContainer = document.getElementById('treeContainer');
            retryUI.show(treeContainer, `Failed to save tree: ${err.message}`, () => this.handleSave());
        }
    }

    async handleCancel() {
        if (this.unsaved) {
            const confirmed = await modal.confirm('You have unsaved changes. Discard them?');
            if (!confirmed) return;
        }
        modal.close(this.modalId);
    }
}
// ========== Tree Editor State ==========
let currentTree = [];
let nodeMap = new Map();
let nodeDetailsCache = new Map();
let nextNodeId = 0;
let selectedNodeId = null;
let treeUnsaved = false;

window.openTreeModalForGroup = async function(groupIndex) {
    window._pendingGroupIndex = groupIndex;
    const initialTree = [];
    window.openTreeModal(initialTree, { isLoading: true, groupIndex: groupIndex });
    try {
        const treeData = await window.apiGet(`/api/models/${window.currentModel}/groups/${groupIndex}/followups`);
        window.updateTreeModalData(treeData);
    } catch (err) {
        console.error('Failed to load follow-up tree:', err);
        window.updateTreeModalError('Failed to load follow-up tree. You can still edit, but unsaved changes may overwrite existing data.');
    }
};

window.openTreeModal = function(treeData, options = {}) {
    const { isLoading = false, groupIndex = null } = options;
    currentTree = treeData || [];
    nodeMap.clear();
    nodeDetailsCache.clear();
    nextNodeId = 0;
    function buildMap(nodes) {
        nodes.forEach(node => {
            node.dbId = node.id;
            node.id = `node_${nextNodeId++}`;
            nodeMap.set(node.id, node);
            if (node.children) buildMap(node.children);
        });
    }
    buildMap(currentTree);
    selectedNodeId = null;
    treeUnsaved = false;
    renderTree();
    window.pushModal('treeModal');
    updateToolbarButtons();
    document.getElementById('nodeQAPanel').style.display = 'none';
    document.getElementById('noNodeSelected').style.display = 'flex';

    if (isLoading) {
        showTreeLoadingIndicator();
    } else {
        hideTreeLoadingIndicator();
    }
};

function showTreeLoadingIndicator() {
    const container = document.getElementById('treeContainer');
    if (container && !document.getElementById('treeLoadingIndicator')) {
        const loadingDiv = document.createElement('div');
        loadingDiv.id = 'treeLoadingIndicator';
        loadingDiv.className = 'tree-loading';
        loadingDiv.innerHTML = '<div class="spinner"></div><span>Loading tree data...</span>';
        container.style.position = 'relative';
        container.appendChild(loadingDiv);
    }
}

function hideTreeLoadingIndicator() {
    const indicator = document.getElementById('treeLoadingIndicator');
    if (indicator) indicator.remove();
    const container = document.getElementById('treeContainer');
    if (container) container.style.position = '';
}

window.updateTreeModalData = function(treeData) {
    hideTreeLoadingIndicator();
    currentTree = treeData;
    nodeMap.clear();
    nodeDetailsCache.clear();
    nextNodeId = 0;
    function buildMap(nodes) {
        nodes.forEach(node => {
            node.dbId = node.id;
            node.id = `node_${nextNodeId++}`;
            nodeMap.set(node.id, node);
            if (node.children) buildMap(node.children);
        });
    }
    buildMap(currentTree);
    renderTree();
    if (selectedNodeId) {
        const selectedDbId = nodeMap.get(selectedNodeId)?.dbId;
        if (selectedDbId) {
            const newId = Array.from(nodeMap.entries()).find(([_, node]) => node.dbId === selectedDbId)?.[0];
            if (newId) selectNode(newId);
        } else {
            selectedNodeId = null;
        }
    }
    updateToolbarButtons();
};

window.updateTreeModalError = function(message) {
    hideTreeLoadingIndicator();
    const container = document.getElementById('treeContainer');
    if (container) {
        window.showRetryError(container, message, async () => {
            await window.openTreeModalForGroup(window._pendingGroupIndex);
        });
    }
};

function renderTree() {
    const container = document.getElementById('treeContainer');
    container.innerHTML = renderTreeNodes(currentTree, 0);
    document.querySelectorAll('.tree-node-header').forEach(header => {
        const nodeId = header.dataset.nodeId;
        const expandIcon = header.querySelector('.expand-icon');
        if (expandIcon) {
            expandIcon.addEventListener('click', (e) => {
                e.stopPropagation();
                const childrenDiv = header.parentElement.querySelector('.tree-children');
                if (childrenDiv) {
                    if (childrenDiv.style.display === 'none') {
                        childrenDiv.style.display = 'block';
                        expandIcon.textContent = '▼';
                    } else {
                        childrenDiv.style.display = 'none';
                        expandIcon.textContent = '▶';
                    }
                }
            });
        }
        header.addEventListener('click', (e) => {
            if (e.target.closest('.node-actions')) return;
            selectNode(nodeId);
        });
    });
    if (selectedNodeId) {
        const selectedHeader = document.querySelector(`.tree-node-header[data-node-id="${selectedNodeId}"]`);
        if (selectedHeader) {
            selectedHeader.classList.add('selected');
            showNodeQAPanel(selectedNodeId);
        } else {
            selectedNodeId = null;
            document.getElementById('nodeQAPanel').style.display = 'none';
            document.getElementById('noNodeSelected').style.display = 'flex';
        }
    } else {
        document.getElementById('nodeQAPanel').style.display = 'none';
        document.getElementById('noNodeSelected').style.display = 'flex';
    }
}

function renderTreeNodes(nodes, level) {
    if (!nodes || nodes.length === 0) return '';
    let html = '';
    nodes.forEach(node => {
        const hasChildren = node.children && node.children.length > 0;
        const expandIcon = hasChildren ? '▼' : '';
        html += `<div class="tree-node">`;
        html += `<div class="tree-node-header" data-node-id="${node.id}">`;
        html += `<span class="expand-icon">${expandIcon}</span>`;
        html += `<span class="name">${escapeHtml(node.branch_name || 'Unnamed')}</span>`;
        html += `<span class="node-actions"></span>`;
        html += `</div>`;
        if (hasChildren) {
            html += `<div class="tree-children">${renderTreeNodes(node.children, level+1)}</div>`;
        }
        html += `</div>`;
    });
    return html;
}

function selectNode(nodeId) {
    if (selectedNodeId) {
        const prev = document.querySelector(`.tree-node-header[data-node-id="${selectedNodeId}"]`);
        if (prev) prev.classList.remove('selected');
    }
    selectedNodeId = nodeId;
    const current = document.querySelector(`.tree-node-header[data-node-id="${selectedNodeId}"]`);
    if (current) current.classList.add('selected');
    showNodeQAPanel(nodeId);
    updateToolbarButtons();
}

async function showNodeQAPanel(nodeId) {
    const node = nodeMap.get(nodeId);
    if (!node) return;

    document.getElementById('nodeQAPanel').style.display = 'block';
    document.getElementById('noNodeSelected').style.display = 'none';

    // Ensure fallback selector exists
    let fbSelect = document.getElementById('nodeFallbackSelect');
    if (!fbSelect) {
        const panel = document.getElementById('nodeQAPanel');
        const fbRow = document.createElement('div');
        fbRow.className = 'form-row';
        fbRow.innerHTML = `
            <label>Fallback</label>
            <select id="nodeFallbackSelect">
                <option value="">(None)</option>
            </select>
        `;
        const answersSection = panel.querySelector('.qa-section:last-child');
        answersSection.insertAdjacentElement('afterend', fbRow);
        fbSelect = document.getElementById('nodeFallbackSelect');
        fbSelect.addEventListener('change', (e) => {
            if (selectedNodeId) {
                const currNode = nodeMap.get(selectedNodeId);
                currNode.fallback = e.target.value;
                treeUnsaved = true;
            }
        });
    }

    // Populate fallback dropdown
    let options = '<option value="">(None)</option>';
    (window.fallbacks || []).forEach(fb => {
        options += `<option value="${escapeHtml(fb.name)}">${escapeHtml(fb.name)}</option>`;
    });
    fbSelect.innerHTML = options;
    fbSelect.value = node.fallback || '';

    if (!node.dbId) {
        node.questions = node.questions || [];
        node.answers = node.answers || [];
        renderNodeQAPanel(node);
        return;
    }

    if (nodeDetailsCache.has(nodeId)) {
        const details = nodeDetailsCache.get(nodeId);
        node.questions = details.questions;
        node.answers = details.answers;
        renderNodeQAPanel(node);
        return;
    }

    const addQuestionBtn = document.getElementById('treeAddQuestionBtn');
    const addAnswerBtn = document.getElementById('treeAddAnswerBtn');
    if (addQuestionBtn) addQuestionBtn.disabled = true;
    if (addAnswerBtn) addAnswerBtn.disabled = true;

    const qList = document.getElementById('treeQuestionsList');
    const aList = document.getElementById('treeAnswersList');
    qList.innerHTML = '';
    aList.innerHTML = '';

    const qLoading = window.showInlineLoading(qList, "Loading questions");
    const aLoading = window.showInlineLoading(aList, "Loading answers");

    try {
        const details = await window.retryOperation(async () => {
            return await window.apiGet(
                `/api/models/${window.currentModel}/groups/${window.selectedGroupIndex}/nodes/${node.dbId}`
            );
        });
        qLoading.clear();
        aLoading.clear();
        node.questions = details.questions;
        node.answers = details.answers;
        nodeDetailsCache.set(nodeId, details);
        renderNodeQAPanel(node);
        if (addQuestionBtn) addQuestionBtn.disabled = false;
        if (addAnswerBtn) addAnswerBtn.disabled = false;
    } catch (err) {
        qLoading.clear();
        aLoading.clear();
        window.showInlineListRetry(qList, 'questions', async () => {
            await showNodeQAPanel(nodeId);
        });
        window.showInlineListRetry(aList, 'answers', async () => {
            await showNodeQAPanel(nodeId);
        });
    }
}

function renderNodeQAPanel(node) {
    const qList = document.getElementById('treeQuestionsList');
    qList.innerHTML = '';
    (node.questions || []).forEach((q, i) => {
        const li = document.createElement('li');
        li.innerHTML = `<span>${escapeHtml(q)}</span> <span><button class="edit-tree-question" data-idx="${i}">✎</button><button class="delete-tree-question" data-idx="${i}">🗑</button></span>`;
        qList.appendChild(li);
    });
    qList.querySelectorAll('.edit-tree-question').forEach(btn => {
        btn.addEventListener('click', () => editTreeNodeQuestion(parseInt(btn.dataset.idx)));
    });
    qList.querySelectorAll('.delete-tree-question').forEach(btn => {
        btn.addEventListener('click', () => deleteTreeNodeQuestion(parseInt(btn.dataset.idx)));
    });

    const aList = document.getElementById('treeAnswersList');
    aList.innerHTML = '';
    (node.answers || []).forEach((a, i) => {
        const li = document.createElement('li');
        li.innerHTML = `<span>${escapeHtml(a)}</span> <span><button class="edit-tree-answer" data-idx="${i}">✎</button><button class="delete-tree-answer" data-idx="${i}">🗑</button></span>`;
        aList.appendChild(li);
    });
    aList.querySelectorAll('.edit-tree-answer').forEach(btn => {
        btn.addEventListener('click', () => editTreeNodeAnswer(parseInt(btn.dataset.idx)));
    });
    aList.querySelectorAll('.delete-tree-answer').forEach(btn => {
        btn.addEventListener('click', () => deleteTreeNodeAnswer(parseInt(btn.dataset.idx)));
    });
}

function updateToolbarButtons() {
    const hasSelection = selectedNodeId !== null;
    document.getElementById('addChildBtn').disabled = !hasSelection;
    document.getElementById('editNodeBtn').disabled = !hasSelection;
    document.getElementById('deleteNodeBtn').disabled = !hasSelection;
}

document.getElementById('addRootBtn').onclick = () => {
    const newNode = { branch_name: 'New Root', questions: [], answers: [], children: [], fallback: '' };
    newNode.id = `node_${nextNodeId++}`;
    nodeMap.set(newNode.id, newNode);
    currentTree.push(newNode);
    treeUnsaved = true;
    renderTree();
    selectNode(newNode.id);
};

document.getElementById('addChildBtn').onclick = () => {
    if (!selectedNodeId) return;
    const parentNode = nodeMap.get(selectedNodeId);
    if (!parentNode) return;
    if (!parentNode.children) parentNode.children = [];
    const newNode = { branch_name: 'New Branch', questions: [], answers: [], children: [], fallback: '' };
    newNode.id = `node_${nextNodeId++}`;
    nodeMap.set(newNode.id, newNode);
    parentNode.children.push(newNode);
    treeUnsaved = true;
    renderTree();
    selectNode(newNode.id);
};

document.getElementById('editNodeBtn').onclick = () => {
    if (!selectedNodeId) return;
    const node = nodeMap.get(selectedNodeId);
    window.showSimpleModal('Edit Node Name', [{ name: 'name', label: 'Branch Name', value: node.branch_name || '' }], (vals, errorDiv) => {
        if (!vals.name) {
            errorDiv.textContent = 'Branch name cannot be empty.';
            errorDiv.style.display = 'block';
            return;
        }
        node.branch_name = vals.name;
        treeUnsaved = true;
        renderTree();
    }, 'Save');
};

document.getElementById('deleteNodeBtn').onclick = () => {
    if (!selectedNodeId) return;
    const node = nodeMap.get(selectedNodeId);
    window.showConfirmModal(`Delete '${node.branch_name || 'Unnamed'}' and all its children?`, () => {
        function removeNode(nodes, nodeId) {
            for (let i = 0; i < nodes.length; i++) {
                if (nodes[i].id === nodeId) {
                    nodes.splice(i, 1);
                    return true;
                }
                if (nodes[i].children && removeNode(nodes[i].children, nodeId)) return true;
            }
            return false;
        }
        removeNode(currentTree, selectedNodeId);
        nodeMap.delete(selectedNodeId);
        selectedNodeId = null;
        treeUnsaved = true;
        renderTree();
        updateToolbarButtons();
    });
};

function editTreeNodeQuestion(qIdx) {
    const node = nodeMap.get(selectedNodeId);
    window.showSimpleModal('Edit Question', [{ name: 'text', label: 'Question', value: node.questions[qIdx] }], (vals, errorDiv) => {
        if (!vals.text) {
            errorDiv.textContent = 'Question cannot be empty.';
            errorDiv.style.display = 'block';
            return;
        }
        node.questions[qIdx] = vals.text;
        treeUnsaved = true;
        nodeDetailsCache.set(selectedNodeId, { questions: node.questions, answers: node.answers });
        showNodeQAPanel(selectedNodeId);
    }, 'Save');
}

function deleteTreeNodeQuestion(qIdx) {
    const node = nodeMap.get(selectedNodeId);
    window.showConfirmModal('Delete this question?', () => {
        node.questions.splice(qIdx, 1);
        treeUnsaved = true;
        nodeDetailsCache.set(selectedNodeId, { questions: node.questions, answers: node.answers });
        showNodeQAPanel(selectedNodeId);
    });
}

function editTreeNodeAnswer(aIdx) {
    const node = nodeMap.get(selectedNodeId);
    window.showSimpleModal('Edit Answer', [{ name: 'text', label: 'Answer', value: node.answers[aIdx] }], (vals, errorDiv) => {
        if (!vals.text) {
            errorDiv.textContent = 'Answer cannot be empty.';
            errorDiv.style.display = 'block';
            return;
        }
        node.answers[aIdx] = vals.text;
        treeUnsaved = true;
        nodeDetailsCache.set(selectedNodeId, { questions: node.questions, answers: node.answers });
        showNodeQAPanel(selectedNodeId);
    }, 'Save');
}

function deleteTreeNodeAnswer(aIdx) {
    const node = nodeMap.get(selectedNodeId);
    window.showConfirmModal('Delete this answer?', () => {
        node.answers.splice(aIdx, 1);
        treeUnsaved = true;
        nodeDetailsCache.set(selectedNodeId, { questions: node.questions, answers: node.answers });
        showNodeQAPanel(selectedNodeId);
    });
}

document.getElementById('treeAddQuestionBtn').onclick = () => {
    if (!selectedNodeId) return;
    window.showSimpleModal('Add Question', [{ name: 'text', label: 'Question', value: '' }], (vals, errorDiv) => {
        if (!vals.text) {
            errorDiv.textContent = 'Question cannot be empty.';
            errorDiv.style.display = 'block';
            return;
        }
        const node = nodeMap.get(selectedNodeId);
        if (!node.questions) node.questions = [];
        node.questions.push(vals.text);
        treeUnsaved = true;
        nodeDetailsCache.set(selectedNodeId, { questions: node.questions, answers: node.answers });
        showNodeQAPanel(selectedNodeId);
    }, 'Add');
};

document.getElementById('treeAddAnswerBtn').onclick = () => {
    if (!selectedNodeId) return;
    window.showSimpleModal('Add Answer', [{ name: 'text', label: 'Answer', value: '' }], (vals, errorDiv) => {
        if (!vals.text) {
            errorDiv.textContent = 'Answer cannot be empty.';
            errorDiv.style.display = 'block';
            return;
        }
        const node = nodeMap.get(selectedNodeId);
        if (!node.answers) node.answers = [];
        node.answers.push(vals.text);
        treeUnsaved = true;
        nodeDetailsCache.set(selectedNodeId, { questions: node.questions, answers: node.answers });
        showNodeQAPanel(selectedNodeId);
    }, 'Add');
};

document.getElementById('treeModalSaveBtn').onclick = async () => {
    function buildFullTree(nodes) {
        return nodes.map(node => {
            const details = nodeDetailsCache.get(node.id) || { questions: [], answers: [] };
            return {
                id: node.dbId,
                branch_name: node.branch_name,
                questions: details.questions || [],
                answers: details.answers || [],
                fallback: node.fallback || '',
                children: buildFullTree(node.children || [])
            };
        });
    }
    const treeToSave = buildFullTree(currentTree);
    try {
        await window.apiPut(`/api/models/${window.currentModel}/groups/${window.selectedGroupIndex}/followups`, treeToSave);
        if (typeof modalGroupCopy !== 'undefined' && modalGroupCopy) {
            modalGroupCopy.follow_ups = treeToSave;
        }
        treeUnsaved = false;
        window.popModal();
    } catch (err) {
        const container = document.getElementById('treeContainer');
        window.showRetryError(container, `Failed to save tree: ${err.message}`, async () => {
            document.getElementById('treeModalSaveBtn').click();
        });
    }
};

document.getElementById('treeModalCancelBtn').onclick = () => {
    if (treeUnsaved) {
        window.showConfirmModal('You have unsaved changes. Discard them?', () => {
            window.popModal();
        });
    } else {
        window.popModal();
    }
};

window.refreshTreeModalFallbackDropdown = function() {
    const select = document.getElementById('nodeFallbackSelect');
    if (!select) return;
    let options = '<option value="">(None)</option>';
    (window.fallbacks || []).forEach(fb => {
        options += `<option value="${escapeHtml(fb.name)}">${escapeHtml(fb.name)}</option>`;
    });
    select.innerHTML = options;
    if (selectedNodeId) {
        const node = nodeMap.get(selectedNodeId);
        if (node && node.fallback) {
            select.value = node.fallback;
        } else {
            select.value = '';
        }
    }
};

// Inject tree styles
if (!document.querySelector('#tree-styles')) {
    const style = document.createElement('style');
    style.id = 'tree-styles';
    style.textContent = `
        .tree-loading {
            position: absolute;
            top: 0;
            left: 0;
            right: 0;
            bottom: 0;
            background: rgba(0,0,0,0.7);
            display: flex;
            align-items: center;
            justify-content: center;
            z-index: 10;
            border-radius: 8px;
        }
        .tree-loading .spinner {
            width: 24px;
            height: 24px;
            border: 3px solid #fff;
            border-top-color: #6c63ff;
            border-radius: 50%;
            animation: spin 0.8s linear infinite;
            margin-right: 12px;
        }
        @keyframes spin {
            to { transform: rotate(360deg); }
        }
    `;
    document.head.appendChild(style);
}
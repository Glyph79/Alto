// ========== Global State ==========
let currentModel = null;
let groups = [];
let sections = [];
let selectedGroupIndex = -1;

// Tree editor state
let currentTree = [];
let nodeMap = new Map();
let nextNodeId = 0;
let selectedNodeId = null;
let treeUnsaved = false;

// ========== API Helpers ==========
async function apiGet(url) {
    const r = await fetch(url);
    if (!r.ok) {
        const err = await r.json();
        throw new Error(err.error || `HTTP ${r.status}`);
    }
    return r.json();
}
async function apiPost(url, data) {
    const r = await fetch(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data)
    });
    if (!r.ok) {
        const err = await r.json();
        throw new Error(err.error || `HTTP ${r.status}`);
    }
    return r.json();
}
async function apiPut(url, data) {
    const r = await fetch(url, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data)
    });
    if (!r.ok) {
        const err = await r.json();
        throw new Error(err.error || `HTTP ${r.status}`);
    }
    return r.json();
}
async function apiDelete(url) {
    const r = await fetch(url, { method: 'DELETE' });
    if (!r.ok) {
        const err = await r.json();
        throw new Error(err.error || `HTTP ${r.status}`);
    }
    return r.json();
}

// ========== Modal Helpers ==========
function showSimpleModal(title, fields, onSave, buttonText = 'Save') {
    const modal = document.getElementById('simpleModal');
    const content = document.getElementById('simpleModalContent');
    let html = `<h2>${title}</h2>`;
    html += `<div id="simpleModalError" style="color: #ff6b9d; margin-bottom: 16px; display: none;"></div>`;
    fields.forEach(f => {
        if (f.type === 'textarea') {
            html += `<textarea id="simple_${f.name}" placeholder="${f.label}">${f.value || ''}</textarea>`;
        } else {
            html += `<input type="text" id="simple_${f.name}" placeholder="${f.label}" value="${f.value || ''}">`;
        }
    });
    html += `<div class="modal-actions">
                <button class="save" id="simpleSaveBtn">${buttonText}</button>
                <button class="cancel" id="simpleCancelBtn">Cancel</button>
            </div>`;
    content.innerHTML = html;
    modal.style.display = 'flex';

    document.getElementById('simpleCancelBtn').onclick = () => { modal.style.display = 'none'; };
    document.getElementById('simpleSaveBtn').onclick = () => {
        const values = {};
        fields.forEach(f => values[f.name] = document.getElementById(`simple_${f.name}`).value);
        const errorDiv = document.getElementById('simpleModalError');
        errorDiv.style.display = 'none';
        onSave(values, errorDiv);
    };
}

function showConfirmModal(message, onConfirm) {
    const modal = document.getElementById('simpleModal');
    const content = document.getElementById('simpleModalContent');
    content.innerHTML = `
        <h2>Confirm</h2>
        <p style="margin: 20px 0; color: #ccc;">${message}</p>
        <div class="modal-actions">
            <button class="save" id="confirmYesBtn">Yes</button>
            <button class="cancel" id="confirmNoBtn">No</button>
        </div>
    `;
    modal.style.display = 'flex';

    document.getElementById('confirmNoBtn').onclick = () => { modal.style.display = 'none'; };
    document.getElementById('confirmYesBtn').onclick = () => {
        modal.style.display = 'none';
        onConfirm();
    };
}

// ========== UI Enable/Disable ==========
function setControlsEnabled(enabled) {
    const modelDependentControls = [
        document.getElementById('modelSelect'),
        document.getElementById('editModelBtn'),
        document.getElementById('deleteModelBtn'),
        document.getElementById('saveModelBtn'),
        document.getElementById('exportBtn'),
        document.getElementById('addGroupBtn'),
        document.getElementById('createFirstGroupBtn'),
        document.getElementById('sectionFilter')
    ];
    modelDependentControls.forEach(ctrl => { if (ctrl) ctrl.disabled = !enabled; });

    document.getElementById('importBtn').disabled = false;
    document.getElementById('createModelBtn').disabled = false;
    document.getElementById('createFirstModelBtn').disabled = false;
}

// ========== Load Models ==========
async function loadModels() {
    try {
        const models = await apiGet('/api/models');
        const select = document.getElementById('modelSelect');
        select.innerHTML = '';
        models.forEach(m => {
            const opt = document.createElement('option');
            opt.value = m;
            opt.textContent = m;
            select.appendChild(opt);
        });

        select.addEventListener('change', (e) => {
            switchModel(e.target.value);
        });

        if (models.length > 0) {
            select.value = models[0];
            await switchModel(models[0]);
            document.getElementById('noModelsEmptyState').style.display = 'none';
            setControlsEnabled(true);
        } else {
            currentModel = null;
            groups = [];
            sections = [];
            renderGroups();
            document.getElementById('noModelsEmptyState').style.display = 'block';
            document.getElementById('noGroupsEmptyState').style.display = 'none';
            setControlsEnabled(false);
        }
    } catch (err) {
        alert('Error loading models: ' + err.message);
    }
}

async function switchModel(modelName) {
    currentModel = modelName;
    await loadGroupsAndSections();
}

async function loadGroupsAndSections() {
    if (!currentModel) return;
    try {
        const data = await apiGet(`/api/models/${currentModel}/groups`);
        groups = data.groups || [];
        sections = data.sections || ["General", "Technical", "Creative"];
        renderGroups();
        renderSectionFilter();
        document.getElementById('groupModal').style.display = 'none';
        document.getElementById('treeModal').style.display = 'none';
    } catch (err) {
        alert('Error loading groups: ' + err.message);
    }
}

function renderSectionFilter() {
    const select = document.getElementById('sectionFilter');
    select.innerHTML = '<option value="All Sections">All Sections</option><option value="Uncategorized">Uncategorized</option>';
    sections.forEach(s => {
        const opt = document.createElement('option');
        opt.value = s;
        opt.textContent = s;
        select.appendChild(opt);
    });
}

// ========== Render Groups (Cards) ==========
function renderGroups() {
    const filter = document.getElementById('sectionFilter').value;
    let filtered = groups;
    if (filter === 'Uncategorized') filtered = groups.filter(g => !g.section);
    else if (filter !== 'All Sections') filtered = groups.filter(g => g.section === filter);

    const container = document.getElementById('groupsGridContainer');
    if (!container) return;
    if (filtered.length === 0) {
        container.innerHTML = '';
        document.getElementById('noGroupsEmptyState').style.display = 'flex';
        return;
    }
    document.getElementById('noGroupsEmptyState').style.display = 'none';

    let html = '<div class="groups-grid">';
    filtered.forEach((g, idx) => {
        const originalIndex = groups.findIndex(gg => gg === g);
        const section = g.section || 'Uncategorized';
        html += `
            <div class="group-card" data-index="${originalIndex}">
                <div class="header">
                    <span class="section-badge">${section}</span>
                    <div class="card-actions">
                        <button class="edit-group" title="Edit">✎</button>
                        <button class="delete-group" title="Delete">🗑</button>
                    </div>
                </div>
                <h4>${g.group_name || 'Unnamed'}</h4>
                <div class="description">${g.group_description || ''}</div>
                <div class="stats">
                    <span>❓ ${g.questions?.length || 0}</span>
                    <span>💬 ${g.answers?.length || 0}</span>
                </div>
            </div>
        `;
    });
    html += '</div>';
    container.innerHTML = html;

    document.querySelectorAll('.group-card').forEach(card => {
        const index = card.dataset.index;
        card.addEventListener('click', (e) => {
            if (e.target.closest('.card-actions')) return;
            if (index !== undefined) openGroupModal(parseInt(index));
        });
        card.querySelector('.edit-group').addEventListener('click', (e) => {
            e.stopPropagation();
            if (index !== undefined) openGroupModal(parseInt(index));
        });
        card.querySelector('.delete-group').addEventListener('click', (e) => {
            e.stopPropagation();
            if (index !== undefined) deleteGroup(parseInt(index));
        });
    });
}

async function deleteGroup(index) {
    showConfirmModal('Are you sure you want to delete this group?', async () => {
        await apiDelete(`/api/models/${currentModel}/groups/${index}`);
        await loadGroupsAndSections();
    });
}

// ========== Group Modal ==========
function openGroupModal(index) {
    selectedGroupIndex = index;
    const group = groups[index];
    if (!group) return;

    document.getElementById('modalGroupName').value = group.group_name || '';
    document.getElementById('modalGroupDesc').value = group.group_description || '';

    const sectionSelect = document.getElementById('modalGroupSection');
    sectionSelect.innerHTML = sections.map(s => `<option value="${s}">${s}</option>`).join('');
    sectionSelect.value = group.section || sections[0] || '';

    document.getElementById('modalGroupTopic').value = group.topic || 'general';
    document.getElementById('modalGroupPriority').value = group.priority || 'medium';

    const qList = document.getElementById('modalQuestionsList');
    qList.innerHTML = '';
    (group.questions || []).forEach((q, i) => {
        const li = document.createElement('li');
        li.innerHTML = `<span>${q}</span> <span><button onclick="editQuestion(${i})">✎</button><button onclick="deleteQuestion(${i})">🗑</button></span>`;
        qList.appendChild(li);
    });

    const aList = document.getElementById('modalAnswersList');
    aList.innerHTML = '';
    (group.answers || []).forEach((a, i) => {
        const li = document.createElement('li');
        li.innerHTML = `<span>${a}</span> <span><button onclick="editAnswer(${i})">✎</button><button onclick="deleteAnswer(${i})">🗑</button></span>`;
        aList.appendChild(li);
    });

    document.getElementById('groupModal').style.display = 'flex';
}

// Question/Answer handlers (inside group modal)
window.editQuestion = (qIdx) => {
    const question = groups[selectedGroupIndex].questions[qIdx];
    showSimpleModal('Edit Question', [{ name: 'text', label: 'Question', value: question }], async (vals, errorDiv) => {
        if (!vals.text) {
            errorDiv.textContent = 'Question cannot be empty.';
            errorDiv.style.display = 'block';
            return;
        }
        await apiPut(`/api/models/${currentModel}/groups/${selectedGroupIndex}/questions/${qIdx}`, { question: vals.text });
        await loadGroupsAndSections();
        document.getElementById('simpleModal').style.display = 'none';
        openGroupModal(selectedGroupIndex);
    }, 'Save');
};
window.deleteQuestion = (qIdx) => {
    showConfirmModal('Delete this question?', async () => {
        await apiDelete(`/api/models/${currentModel}/groups/${selectedGroupIndex}/questions/${qIdx}`);
        await loadGroupsAndSections();
        openGroupModal(selectedGroupIndex);
    });
};
window.editAnswer = (aIdx) => {
    const answer = groups[selectedGroupIndex].answers[aIdx];
    showSimpleModal('Edit Answer', [{ name: 'text', label: 'Answer', value: answer }], async (vals, errorDiv) => {
        if (!vals.text) {
            errorDiv.textContent = 'Answer cannot be empty.';
            errorDiv.style.display = 'block';
            return;
        }
        await apiPut(`/api/models/${currentModel}/groups/${selectedGroupIndex}/answers/${aIdx}`, { answer: vals.text });
        await loadGroupsAndSections();
        document.getElementById('simpleModal').style.display = 'none';
        openGroupModal(selectedGroupIndex);
    }, 'Save');
};
window.deleteAnswer = (aIdx) => {
    showConfirmModal('Delete this answer?', async () => {
        await apiDelete(`/api/models/${currentModel}/groups/${selectedGroupIndex}/answers/${aIdx}`);
        await loadGroupsAndSections();
        openGroupModal(selectedGroupIndex);
    });
};

document.getElementById('modalAddQuestionBtn').onclick = () => {
    showSimpleModal('Add Question', [{ name: 'text', label: 'Question', value: '' }], async (vals, errorDiv) => {
        if (!vals.text) {
            errorDiv.textContent = 'Question cannot be empty.';
            errorDiv.style.display = 'block';
            return;
        }
        await apiPost(`/api/models/${currentModel}/groups/${selectedGroupIndex}/questions`, { question: vals.text });
        await loadGroupsAndSections();
        document.getElementById('simpleModal').style.display = 'none';
        openGroupModal(selectedGroupIndex);
    }, 'Add');
};
document.getElementById('modalAddAnswerBtn').onclick = () => {
    showSimpleModal('Add Answer', [{ name: 'text', label: 'Answer', value: '' }], async (vals, errorDiv) => {
        if (!vals.text) {
            errorDiv.textContent = 'Answer cannot be empty.';
            errorDiv.style.display = 'block';
            return;
        }
        await apiPost(`/api/models/${currentModel}/groups/${selectedGroupIndex}/answers`, { answer: vals.text });
        await loadGroupsAndSections();
        document.getElementById('simpleModal').style.display = 'none';
        openGroupModal(selectedGroupIndex);
    }, 'Add');
};

// ========== Save Group (with questions and answers) ==========
document.getElementById('modalSaveBtn').onclick = async () => {
    if (selectedGroupIndex === -1) return;

    // Gather current questions from the list
    const questions = [];
    const qList = document.getElementById('modalQuestionsList');
    for (let li of qList.children) {
        const span = li.querySelector('span:first-child');
        if (span) questions.push(span.textContent);
    }

    // Gather current answers from the list
    const answers = [];
    const aList = document.getElementById('modalAnswersList');
    for (let li of aList.children) {
        const span = li.querySelector('span:first-child');
        if (span) answers.push(span.textContent);
    }

    const updated = {
        group_name: document.getElementById('modalGroupName').value,
        group_description: document.getElementById('modalGroupDesc').value,
        section: document.getElementById('modalGroupSection').value,
        topic: document.getElementById('modalGroupTopic').value,
        priority: document.getElementById('modalGroupPriority').value,
        questions: questions,
        answers: answers
        // follow_ups are handled separately
    };
    await apiPut(`/api/models/${currentModel}/groups/${selectedGroupIndex}`, updated);
    await loadGroupsAndSections();
    document.getElementById('groupModal').style.display = 'none';
};

document.getElementById('modalCancelBtn').onclick = () => {
    document.getElementById('groupModal').style.display = 'none';
};

// ========== Follow-up Tree Modal ==========
document.getElementById('modalEditFollowupsBtn').onclick = async () => {
    if (selectedGroupIndex === -1) return;
    currentTree = await apiGet(`/api/models/${currentModel}/groups/${selectedGroupIndex}/followups`);
    nodeMap.clear();
    nextNodeId = 0;
    function buildMap(nodes) {
        nodes.forEach(node => {
            node.id = `node_${nextNodeId++}`;
            nodeMap.set(node.id, node);
            if (node.children) buildMap(node.children);
        });
    }
    buildMap(currentTree);
    selectedNodeId = null;
    treeUnsaved = false;
    renderTree();
    document.getElementById('treeModal').style.display = 'flex';
    updateToolbarButtons();
    document.getElementById('nodeQAPanel').style.display = 'none';
    document.getElementById('noNodeSelected').style.display = 'flex';
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
        html += `<span class="name">${node.branch_name || 'Unnamed'}</span>`;
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

function showNodeQAPanel(nodeId) {
    const node = nodeMap.get(nodeId);
    if (!node) return;
    document.getElementById('nodeQAPanel').style.display = 'block';
    document.getElementById('noNodeSelected').style.display = 'none';
    const qList = document.getElementById('treeQuestionsList');
    qList.innerHTML = '';
    (node.questions || []).forEach((q, i) => {
        const li = document.createElement('li');
        li.innerHTML = `<span>${q}</span> <span><button onclick="editTreeNodeQuestion(${i})">✎</button><button onclick="deleteTreeNodeQuestion(${i})">🗑</button></span>`;
        qList.appendChild(li);
    });
    const aList = document.getElementById('treeAnswersList');
    aList.innerHTML = '';
    (node.answers || []).forEach((a, i) => {
        const li = document.createElement('li');
        li.innerHTML = `<span>${a}</span> <span><button onclick="editTreeNodeAnswer(${i})">✎</button><button onclick="deleteTreeNodeAnswer(${i})">🗑</button></span>`;
        aList.appendChild(li);
    });
}

function updateToolbarButtons() {
    const hasSelection = selectedNodeId !== null;
    document.getElementById('addChildBtn').disabled = !hasSelection;
    document.getElementById('editNodeBtn').disabled = !hasSelection;
    document.getElementById('deleteNodeBtn').disabled = !hasSelection;
}

document.getElementById('addRootBtn').onclick = () => {
    const newNode = { branch_name: 'New Root', questions: [], answers: [], children: [] };
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
    const newNode = { branch_name: 'New Branch', questions: [], answers: [], children: [] };
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
    showSimpleModal('Edit Node Name', [{ name: 'name', label: 'Branch Name', value: node.branch_name || '' }], (vals, errorDiv) => {
        if (!vals.name) {
            errorDiv.textContent = 'Branch name cannot be empty.';
            errorDiv.style.display = 'block';
            return;
        }
        node.branch_name = vals.name;
        treeUnsaved = true;
        document.getElementById('simpleModal').style.display = 'none';
        renderTree();
    }, 'Save');
};

document.getElementById('deleteNodeBtn').onclick = () => {
    if (!selectedNodeId) return;
    const node = nodeMap.get(selectedNodeId);
    showConfirmModal(`Delete '${node.branch_name || 'Unnamed'}' and all its children?`, () => {
        function removeNode(nodes, nodeId) {
            for (let i = 0; i < nodes.length; i++) {
                if (nodes[i].id === nodeId) {
                    nodes.splice(i, 1);
                    return true;
                }
                if (nodes[i].children) {
                    if (removeNode(nodes[i].children, nodeId)) return true;
                }
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

window.editTreeNodeQuestion = (qIdx) => {
    const node = nodeMap.get(selectedNodeId);
    const question = node.questions[qIdx];
    showSimpleModal('Edit Question', [{ name: 'text', label: 'Question', value: question }], (vals, errorDiv) => {
        if (!vals.text) {
            errorDiv.textContent = 'Question cannot be empty.';
            errorDiv.style.display = 'block';
            return;
        }
        node.questions[qIdx] = vals.text;
        treeUnsaved = true;
        document.getElementById('simpleModal').style.display = 'none';
        showNodeQAPanel(selectedNodeId);
    }, 'Save');
};
window.deleteTreeNodeQuestion = (qIdx) => {
    const node = nodeMap.get(selectedNodeId);
    showConfirmModal('Delete this question?', () => {
        node.questions.splice(qIdx, 1);
        treeUnsaved = true;
        showNodeQAPanel(selectedNodeId);
    });
};
window.editTreeNodeAnswer = (aIdx) => {
    const node = nodeMap.get(selectedNodeId);
    const answer = node.answers[aIdx];
    showSimpleModal('Edit Answer', [{ name: 'text', label: 'Answer', value: answer }], (vals, errorDiv) => {
        if (!vals.text) {
            errorDiv.textContent = 'Answer cannot be empty.';
            errorDiv.style.display = 'block';
            return;
        }
        node.answers[aIdx] = vals.text;
        treeUnsaved = true;
        document.getElementById('simpleModal').style.display = 'none';
        showNodeQAPanel(selectedNodeId);
    }, 'Save');
};
window.deleteTreeNodeAnswer = (aIdx) => {
    const node = nodeMap.get(selectedNodeId);
    showConfirmModal('Delete this answer?', () => {
        node.answers.splice(aIdx, 1);
        treeUnsaved = true;
        showNodeQAPanel(selectedNodeId);
    });
};

document.getElementById('treeAddQuestionBtn').onclick = () => {
    if (!selectedNodeId) return;
    showSimpleModal('Add Question', [{ name: 'text', label: 'Question', value: '' }], (vals, errorDiv) => {
        if (!vals.text) {
            errorDiv.textContent = 'Question cannot be empty.';
            errorDiv.style.display = 'block';
            return;
        }
        const node = nodeMap.get(selectedNodeId);
        if (!node.questions) node.questions = [];
        node.questions.push(vals.text);
        treeUnsaved = true;
        document.getElementById('simpleModal').style.display = 'none';
        showNodeQAPanel(selectedNodeId);
    }, 'Add');
};
document.getElementById('treeAddAnswerBtn').onclick = () => {
    if (!selectedNodeId) return;
    showSimpleModal('Add Answer', [{ name: 'text', label: 'Answer', value: '' }], (vals, errorDiv) => {
        if (!vals.text) {
            errorDiv.textContent = 'Answer cannot be empty.';
            errorDiv.style.display = 'block';
            return;
        }
        const node = nodeMap.get(selectedNodeId);
        if (!node.answers) node.answers = [];
        node.answers.push(vals.text);
        treeUnsaved = true;
        document.getElementById('simpleModal').style.display = 'none';
        showNodeQAPanel(selectedNodeId);
    }, 'Add');
};

// ========== FIX: Save tree without closing group modal ==========
document.getElementById('treeModalSaveBtn').onclick = async () => {
    function stripIds(nodes) {
        return nodes.map(node => {
            const { id, ...rest } = node;
            return { ...rest, children: stripIds(node.children || []) };
        });
    }
    const treeToSave = stripIds(currentTree);
    await apiPut(`/api/models/${currentModel}/groups/${selectedGroupIndex}/followups`, treeToSave);
    treeUnsaved = false;
    document.getElementById('treeModal').style.display = 'none';
    // Do NOT reload groups here, because that would close the group modal.
    // The group modal remains open, and the tree is saved.
};

document.getElementById('treeModalCancelBtn').onclick = () => {
    if (treeUnsaved) {
        showConfirmModal('You have unsaved changes. Discard them?', () => {
            document.getElementById('treeModal').style.display = 'none';
        });
    } else {
        document.getElementById('treeModal').style.display = 'none';
    }
};

// ========== Create New Group ==========
async function createNewGroup() {
    if (!currentModel) {
        alert('Please select or create a model first.');
        return;
    }
    const newGroup = {
        group_name: 'New Group',
        group_description: '',
        questions: [],
        answers: [],
        topic: 'general',
        priority: 'medium',
        section: sections[0] || ''
    };
    await apiPost(`/api/models/${currentModel}/groups`, newGroup);
    await loadGroupsAndSections();
}

document.getElementById('addGroupBtn').onclick = createNewGroup;
document.getElementById('createFirstGroupBtn').onclick = createNewGroup;

// ========== Model Management ==========
document.getElementById('createModelBtn').onclick = () => {
    showSimpleModal('Create New Model', [
        { name: 'name', label: 'Model Name', value: '' },
        { name: 'description', label: 'Description', value: '' },
        { name: 'author', label: 'Author', value: '' },
        { name: 'version', label: 'Version', value: '1.0.0' }
    ], async (vals, errorDiv) => {
        if (!vals.name) {
            errorDiv.textContent = 'Model name is required.';
            errorDiv.style.display = 'block';
            return;
        }
        const response = await fetch('/api/models', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(vals)
        });
        if (response.ok) {
            await loadModels();
            document.getElementById('simpleModal').style.display = 'none';
        } else {
            const err = await response.json();
            errorDiv.textContent = err.error || 'Failed to create model.';
            errorDiv.style.display = 'block';
        }
    }, 'Create');
};

document.getElementById('createFirstModelBtn').onclick = () => {
    document.getElementById('createModelBtn').click();
};

document.getElementById('editModelBtn').onclick = async () => {
    if (!currentModel) return;
    const data = await apiGet(`/api/models/${currentModel}`);
    showSimpleModal('Edit Model', [
        { name: 'description', label: 'Description', value: data.description || '' },
        { name: 'author', label: 'Author', value: data.author || '' },
        { name: 'version', label: 'Version', value: data.version || '1.0.0' }
    ], async (vals, errorDiv) => {
        await apiPut(`/api/models/${currentModel}`, vals);
        await loadModels();
        document.getElementById('simpleModal').style.display = 'none';
    }, 'Save');
};

document.getElementById('deleteModelBtn').onclick = async () => {
    if (!currentModel) return;
    showConfirmModal(`Delete model '${currentModel}'?`, async () => {
        await apiDelete(`/api/models/${currentModel}`);
        await loadModels();
    });
};

document.getElementById('saveModelBtn').onclick = () => alert('All changes are auto-saved.');

// ========== Section Filter ==========
document.getElementById('sectionFilter').onchange = renderGroups;

// ========== Import/Export ==========
document.getElementById('importBtn').onclick = () => {
    const input = document.createElement('input');
    input.type = 'file';
    input.accept = '.json';
    input.onchange = async (e) => {
        const file = e.target.files[0];
        const formData = new FormData();
        formData.append('file', file);
        await fetch(`/api/models/${currentModel}/import`, { method: 'POST', body: formData });
        await loadGroupsAndSections();
    };
    input.click();
};
document.getElementById('exportBtn').onclick = () => {
    if (!currentModel) return;
    window.open(`/api/models/${currentModel}/export`);
};

// ========== Initialize ==========
loadModels();
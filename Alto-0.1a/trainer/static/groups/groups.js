// ========== Load Groups & Sections ==========
window.loadGroupsAndSections = async function() {
    if (!window.currentModel) return;
    try {
        const data = await window.apiGet(`/api/models/${window.currentModel}/groups`);
        window.groups = data.groups || [];
        window.sections = data.sections || ["General", "Technical", "Creative"];
        renderGroups();
        renderSectionFilter();
        document.getElementById('groupModal').style.display = 'none';
        document.getElementById('treeModal').style.display = 'none';
        document.getElementById('groupSearch').disabled = false;
        document.getElementById('sectionFilter').disabled = false;
        document.getElementById('addGroupBtn').disabled = false;
    } catch (err) {
        alert('Error loading groups: ' + err.message);
    }
};

let groupCards = [];

function renderSectionFilter() {
    const select = document.getElementById('sectionFilter');
    select.innerHTML = '<option value="All Sections">All Sections</option><option value="Uncategorized">Uncategorized</option>';
    window.sections.forEach(s => {
        const opt = document.createElement('option');
        opt.value = s;
        opt.textContent = s;
        select.appendChild(opt);
    });
}

function renderGroups() {
    const container = document.getElementById('groupsGridContainer');
    if (!container) return;
    if (window.groups.length === 0) {
        container.innerHTML = '';
        document.getElementById('noGroupsEmptyState').style.display = 'flex';
        groupCards = [];
        return;
    }
    document.getElementById('noGroupsEmptyState').style.display = 'none';

    let html = '<div class="groups-grid">';
    window.groups.forEach((g, idx) => {
        const section = g.section || 'Uncategorized';
        html += `
            <div class="group-card" data-index="${idx}" data-name="${g.group_name || ''}" data-desc="${g.group_description || ''}">
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

    groupCards = Array.from(document.querySelectorAll('.group-card')).map(card => ({
        element: card,
        group: window.groups[parseInt(card.dataset.index)],
        index: parseInt(card.dataset.index)
    }));

    groupCards.forEach(card => {
        const index = card.index;
        card.element.addEventListener('click', (e) => {
            if (e.target.closest('.card-actions')) return;
            openGroupModal(index);
        });
        card.element.querySelector('.edit-group').addEventListener('click', (e) => {
            e.stopPropagation();
            openGroupModal(index);
        });
        card.element.querySelector('.delete-group').addEventListener('click', (e) => {
            e.stopPropagation();
            deleteGroup(index);
        });
    });

    filterAndSortGroups();
}

function filterAndSortGroups() {
    const searchTerm = document.getElementById('groupSearch').value.toLowerCase();
    const sectionFilter = document.getElementById('sectionFilter').value;

    let visibleCards = groupCards.filter(card => {
        const name = card.group.group_name || '';
        const desc = card.group.group_description || '';
        const matchesSearch = name.toLowerCase().includes(searchTerm) || desc.toLowerCase().includes(searchTerm);
        if (!matchesSearch) return false;

        if (sectionFilter === 'All Sections') return true;
        if (sectionFilter === 'Uncategorized') return !card.group.section;
        return card.group.section === sectionFilter;
    });

    const grid = document.querySelector('.groups-grid');
    visibleCards.forEach(card => grid.appendChild(card.element));
    groupCards.forEach(card => {
        card.element.style.display = visibleCards.includes(card) ? 'flex' : 'none';
    });
}

async function deleteGroup(index, callback) {
    window.showConfirmModal('Are you sure you want to delete this group?', async () => {
        await window.apiDelete(`/api/models/${window.currentModel}/groups/${index}`);
        await window.loadGroupsAndSections();
        if (callback) callback();
    });
}

// ========== Group Modal ==========
window.selectedGroupIndex = -1;
let modalGroupCopy = null;

window.openGroupModal = function(index, onSaveCallback) {
    window.selectedGroupIndex = index;
    const group = window.groups[index];
    if (!group) return;

    modalGroupCopy = JSON.parse(JSON.stringify(group));

    document.getElementById('modalGroupName').value = modalGroupCopy.group_name || '';
    document.getElementById('modalGroupDesc').value = modalGroupCopy.group_description || '';

    const sectionSelect = document.getElementById('modalGroupSection');
    sectionSelect.innerHTML = window.sections.map(s => `<option value="${s}">${s}</option>`).join('');
    sectionSelect.value = modalGroupCopy.section || window.sections[0] || '';

    const topicSelect = document.getElementById('modalGroupTopic');
    if (window.topicsList && window.topicsList.length) {
        topicSelect.innerHTML = window.topicsList.map(t => `<option value="${t}">${t}</option>`).join('');
        topicSelect.value = modalGroupCopy.topic || window.topicsList[0] || '';
    } else {
        topicSelect.innerHTML = '<option value="general">general</option>';
        topicSelect.value = modalGroupCopy.topic || 'general';
    }

    document.getElementById('modalGroupPriority').value = modalGroupCopy.priority || 'medium';

    refreshModalLists();
    document.getElementById('groupModal').style.display = 'flex';

    window._groupModalOnSave = onSaveCallback;
};

window.refreshGroupModalTopicDropdown = function() {
    if (document.getElementById('groupModal').style.display === 'flex' && modalGroupCopy) {
        const topicSelect = document.getElementById('modalGroupTopic');
        topicSelect.innerHTML = window.topicsList.map(t => `<option value="${t}">${t}</option>`).join('');
        if (window.topicsList.includes(modalGroupCopy.topic)) {
            topicSelect.value = modalGroupCopy.topic;
        } else {
            topicSelect.value = window.topicsList[0] || '';
            modalGroupCopy.topic = topicSelect.value;
        }
    }
};

function refreshModalLists() {
    const qList = document.getElementById('modalQuestionsList');
    qList.innerHTML = '';
    (modalGroupCopy.questions || []).forEach((q, i) => {
        const li = document.createElement('li');
        li.innerHTML = `<span>${q}</span> <span><button onclick="editQuestion(${i})">✎</button><button onclick="deleteQuestion(${i})">🗑</button></span>`;
        qList.appendChild(li);
    });

    const aList = document.getElementById('modalAnswersList');
    aList.innerHTML = '';
    (modalGroupCopy.answers || []).forEach((a, i) => {
        const li = document.createElement('li');
        li.innerHTML = `<span>${a}</span> <span><button onclick="editAnswer(${i})">✎</button><button onclick="deleteAnswer(${i})">🗑</button></span>`;
        aList.appendChild(li);
    });
}

window.editQuestion = (qIdx) => {
    window.showSimpleModal('Edit Question', [{ name: 'text', label: 'Question', value: modalGroupCopy.questions[qIdx] }], (vals, errorDiv) => {
        if (!vals.text) {
            errorDiv.textContent = 'Question cannot be empty.';
            errorDiv.style.display = 'block';
            return;
        }
        modalGroupCopy.questions[qIdx] = vals.text;
        refreshModalLists();
        document.getElementById('simpleModal').style.display = 'none';
    }, 'Save');
};

window.deleteQuestion = (qIdx) => {
    window.showConfirmModal('Delete this question?', () => {
        modalGroupCopy.questions.splice(qIdx, 1);
        refreshModalLists();
    });
};

window.editAnswer = (aIdx) => {
    window.showSimpleModal('Edit Answer', [{ name: 'text', label: 'Answer', value: modalGroupCopy.answers[aIdx] }], (vals, errorDiv) => {
        if (!vals.text) {
            errorDiv.textContent = 'Answer cannot be empty.';
            errorDiv.style.display = 'block';
            return;
        }
        modalGroupCopy.answers[aIdx] = vals.text;
        refreshModalLists();
        document.getElementById('simpleModal').style.display = 'none';
    }, 'Save');
};

window.deleteAnswer = (aIdx) => {
    window.showConfirmModal('Delete this answer?', () => {
        modalGroupCopy.answers.splice(aIdx, 1);
        refreshModalLists();
    });
};

document.getElementById('modalAddQuestionBtn').onclick = () => {
    window.showSimpleModal('Add Question', [{ name: 'text', label: 'Question', value: '' }], (vals, errorDiv) => {
        if (!vals.text) {
            errorDiv.textContent = 'Question cannot be empty.';
            errorDiv.style.display = 'block';
            return;
        }
        if (!modalGroupCopy.questions) modalGroupCopy.questions = [];
        modalGroupCopy.questions.push(vals.text);
        refreshModalLists();
        document.getElementById('simpleModal').style.display = 'none';
    }, 'Add');
};

document.getElementById('modalAddAnswerBtn').onclick = () => {
    window.showSimpleModal('Add Answer', [{ name: 'text', label: 'Answer', value: '' }], (vals, errorDiv) => {
        if (!vals.text) {
            errorDiv.textContent = 'Answer cannot be empty.';
            errorDiv.style.display = 'block';
            return;
        }
        if (!modalGroupCopy.answers) modalGroupCopy.answers = [];
        modalGroupCopy.answers.push(vals.text);
        refreshModalLists();
        document.getElementById('simpleModal').style.display = 'none';
    }, 'Add');
};

document.getElementById('modalSaveBtn').onclick = async () => {
    if (window.selectedGroupIndex === -1 || !modalGroupCopy) return;

    modalGroupCopy.group_name = document.getElementById('modalGroupName').value;
    modalGroupCopy.group_description = document.getElementById('modalGroupDesc').value;
    modalGroupCopy.section = document.getElementById('modalGroupSection').value;
    modalGroupCopy.topic = document.getElementById('modalGroupTopic').value;
    modalGroupCopy.priority = document.getElementById('modalGroupPriority').value;

    await window.apiPut(`/api/models/${window.currentModel}/groups/${window.selectedGroupIndex}`, modalGroupCopy);
    await window.loadGroupsAndSections();
    document.getElementById('groupModal').style.display = 'none';
    modalGroupCopy = null;

    if (window._groupModalOnSave) {
        window._groupModalOnSave();
        window._groupModalOnSave = null;
    }
};

document.getElementById('modalCancelBtn').onclick = () => {
    modalGroupCopy = null;
    document.getElementById('groupModal').style.display = 'none';
    window._groupModalOnSave = null;
};

// Create new group
async function createNewGroup() {
    if (!window.currentModel) {
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
        section: window.sections[0] || ''
    };
    await window.apiPost(`/api/models/${window.currentModel}/groups`, newGroup);
    await window.loadGroupsAndSections();
}

document.getElementById('addGroupBtn').onclick = createNewGroup;
document.getElementById('createFirstGroupBtn').onclick = createNewGroup;

document.getElementById('groupSearch').addEventListener('input', filterAndSortGroups);
document.getElementById('sectionFilter').onchange = filterAndSortGroups;

// ========== Tree Modal ==========
let currentTree = [];
let nodeMap = new Map();
let nodeDetailsCache = new Map();
let nextNodeId = 0;
let selectedNodeId = null;
let treeUnsaved = false;

document.getElementById('modalEditFollowupsBtn').onclick = async () => {
    // Hide group modal
    document.getElementById('groupModal').style.display = 'none';

    if (typeof window.selectedGroupIndex === 'undefined' || window.selectedGroupIndex === -1) return;
    currentTree = await window.apiGet(`/api/models/${window.currentModel}/groups/${window.selectedGroupIndex}/followups`);
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

async function showNodeQAPanel(nodeId) {
    if (window.currentNodeAnimation) {
        clearTimeout(window.currentNodeAnimation.timeout);
        clearInterval(window.currentNodeAnimation.interval);
        window.currentNodeAnimation = null;
    }

    const node = nodeMap.get(nodeId);
    if (!node) return;

    document.getElementById('nodeQAPanel').style.display = 'block';
    document.getElementById('noNodeSelected').style.display = 'none';

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

    let loadingTimeout = setTimeout(() => {
        document.getElementById('treeQuestionsList').innerHTML = '<li>Loading questions</li>';
        document.getElementById('treeAnswersList').innerHTML = '<li>Loading answers</li>';
        
        let dots = 0;
        const loadingInterval = setInterval(() => {
            dots = (dots + 1) % 4;
            const dotsStr = '.'.repeat(dots);
            document.getElementById('treeQuestionsList').innerHTML = `<li>Loading questions${dotsStr}</li>`;
            document.getElementById('treeAnswersList').innerHTML = `<li>Loading answers${dotsStr}</li>`;
        }, 300);
        
        window.currentNodeAnimation = { timeout: loadingTimeout, interval: loadingInterval };
    }, 300);

    let attempts = 0;
    const maxAttempts = 3;
    let lastError;

    while (attempts < maxAttempts) {
        attempts++;
        try {
            const details = await window.apiGet(
                `/api/models/${window.currentModel}/groups/${window.selectedGroupIndex}/nodes/${node.dbId}`
            );
            if (window.currentNodeAnimation) {
                clearTimeout(window.currentNodeAnimation.timeout);
                clearInterval(window.currentNodeAnimation.interval);
                window.currentNodeAnimation = null;
            } else {
                clearTimeout(loadingTimeout);
            }
            node.questions = details.questions;
            node.answers = details.answers;
            nodeDetailsCache.set(nodeId, details);
            renderNodeQAPanel(node);
            return;
        } catch (err) {
            lastError = err;
            if (attempts < maxAttempts) {
                await new Promise(resolve => setTimeout(resolve, 200 * Math.pow(2, attempts - 1)));
            }
        }
    }

    if (window.currentNodeAnimation) {
        clearTimeout(window.currentNodeAnimation.timeout);
        clearInterval(window.currentNodeAnimation.interval);
        window.currentNodeAnimation = null;
    } else {
        clearTimeout(loadingTimeout);
    }
    document.getElementById('treeQuestionsList').innerHTML = '<li style="color: #ff6b9d;">Error loading questions</li>';
    document.getElementById('treeAnswersList').innerHTML = '<li style="color: #ff6b9d;">Error loading answers</li>';
}

function renderNodeQAPanel(node) {
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
    window.showSimpleModal('Edit Node Name', [{ name: 'name', label: 'Branch Name', value: node.branch_name || '' }], (vals, errorDiv) => {
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
    window.showConfirmModal(`Delete '${node.branch_name || 'Unnamed'}' and all its children?`, () => {
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
    window.showSimpleModal('Edit Question', [{ name: 'text', label: 'Question', value: question }], (vals, errorDiv) => {
        if (!vals.text) {
            errorDiv.textContent = 'Question cannot be empty.';
            errorDiv.style.display = 'block';
            return;
        }
        node.questions[qIdx] = vals.text;
        treeUnsaved = true;
        nodeDetailsCache.set(selectedNodeId, { questions: node.questions, answers: node.answers });
        document.getElementById('simpleModal').style.display = 'none';
        showNodeQAPanel(selectedNodeId);
    }, 'Save');
};

window.deleteTreeNodeQuestion = (qIdx) => {
    const node = nodeMap.get(selectedNodeId);
    window.showConfirmModal('Delete this question?', () => {
        node.questions.splice(qIdx, 1);
        treeUnsaved = true;
        nodeDetailsCache.set(selectedNodeId, { questions: node.questions, answers: node.answers });
        showNodeQAPanel(selectedNodeId);
    });
};

window.editTreeNodeAnswer = (aIdx) => {
    const node = nodeMap.get(selectedNodeId);
    const answer = node.answers[aIdx];
    window.showSimpleModal('Edit Answer', [{ name: 'text', label: 'Answer', value: answer }], (vals, errorDiv) => {
        if (!vals.text) {
            errorDiv.textContent = 'Answer cannot be empty.';
            errorDiv.style.display = 'block';
            return;
        }
        node.answers[aIdx] = vals.text;
        treeUnsaved = true;
        nodeDetailsCache.set(selectedNodeId, { questions: node.questions, answers: node.answers });
        document.getElementById('simpleModal').style.display = 'none';
        showNodeQAPanel(selectedNodeId);
    }, 'Save');
};

window.deleteTreeNodeAnswer = (aIdx) => {
    const node = nodeMap.get(selectedNodeId);
    window.showConfirmModal('Delete this answer?', () => {
        node.answers.splice(aIdx, 1);
        treeUnsaved = true;
        nodeDetailsCache.set(selectedNodeId, { questions: node.questions, answers: node.answers });
        showNodeQAPanel(selectedNodeId);
    });
};

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
        document.getElementById('simpleModal').style.display = 'none';
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
        document.getElementById('simpleModal').style.display = 'none';
        showNodeQAPanel(selectedNodeId);
    }, 'Add');
};

document.getElementById('treeModalSaveBtn').onclick = async () => {
    function buildFullTree(nodes) {
        return nodes.map(node => {
            const details = nodeDetailsCache.get(node.id) || { questions: [], answers: [] };
            return {
                branch_name: node.branch_name,
                questions: details.questions || [],
                answers: details.answers || [],
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
        document.getElementById('treeModal').style.display = 'none';
        document.getElementById('groupModal').style.display = 'flex';
    } catch (err) {
        alert('Failed to save follow‑up tree: ' + err.message);
    }
};

document.getElementById('treeModalCancelBtn').onclick = () => {
    if (treeUnsaved) {
        window.showConfirmModal('You have unsaved changes. Discard them?', () => {
            document.getElementById('treeModal').style.display = 'none';
            document.getElementById('groupModal').style.display = 'flex';
        });
    } else {
        document.getElementById('treeModal').style.display = 'none';
        document.getElementById('groupModal').style.display = 'flex';
    }
};
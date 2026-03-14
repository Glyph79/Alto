// ========== Tree Editor State ==========
let currentTree = [];
let nodeMap = new Map();
let nextNodeId = 0;
let selectedNodeId = null;
let treeUnsaved = false;

// ========== Open Tree Modal ==========
document.getElementById('modalEditFollowupsBtn').onclick = async () => {
    if (typeof selectedGroupIndex === 'undefined' || selectedGroupIndex === -1) return;
    currentTree = await window.apiGet(`/api/models/${window.currentModel}/groups/${selectedGroupIndex}/followups`);
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

// Tree toolbar handlers
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

// Node Q&A editing
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
        document.getElementById('simpleModal').style.display = 'none';
        showNodeQAPanel(selectedNodeId);
    }, 'Save');
};

window.deleteTreeNodeQuestion = (qIdx) => {
    const node = nodeMap.get(selectedNodeId);
    window.showConfirmModal('Delete this question?', () => {
        node.questions.splice(qIdx, 1);
        treeUnsaved = true;
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
        document.getElementById('simpleModal').style.display = 'none';
        showNodeQAPanel(selectedNodeId);
    }, 'Save');
};

window.deleteTreeNodeAnswer = (aIdx) => {
    const node = nodeMap.get(selectedNodeId);
    window.showConfirmModal('Delete this answer?', () => {
        node.answers.splice(aIdx, 1);
        treeUnsaved = true;
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
        document.getElementById('simpleModal').style.display = 'none';
        showNodeQAPanel(selectedNodeId);
    }, 'Add');
};

// Tree modal save/cancel
document.getElementById('treeModalSaveBtn').onclick = async () => {
    function stripIds(nodes) {
        return nodes.map(node => {
            const { id, ...rest } = node;
            return { ...rest, children: stripIds(node.children || []) };
        });
    }
    const treeToSave = stripIds(currentTree);
    try {
        await window.apiPut(`/api/models/${window.currentModel}/groups/${selectedGroupIndex}/followups`, treeToSave);
        // Keep modalGroupCopy in sync if present
        if (typeof modalGroupCopy !== 'undefined' && modalGroupCopy) {
            modalGroupCopy.follow_ups = treeToSave;
        }
        treeUnsaved = false;
        document.getElementById('treeModal').style.display = 'none';
    } catch (err) {
        alert('Failed to save follow‑up tree: ' + err.message);
    }
};

document.getElementById('treeModalCancelBtn').onclick = () => {
    if (treeUnsaved) {
        window.showConfirmModal('You have unsaved changes. Discard them?', () => {
            document.getElementById('treeModal').style.display = 'none';
        });
    } else {
        document.getElementById('treeModal').style.display = 'none';
    }
};
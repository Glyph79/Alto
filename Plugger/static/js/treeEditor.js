import { showModal, hideModal, showTextInputModal, showConfirmModal, escapeHtml } from './modals.js';
import { openNodeScriptEditor } from './scriptEditor.js';

let currentTree = [];
let nodeMap = new Map();
let nextNodeId = 0;
let selectedNodeId = null;
let treeUnsaved = false;
let pluginCopy = null;

export function openTreeEditor(plugin) {
    pluginCopy = plugin;
    currentTree = JSON.parse(JSON.stringify(pluginCopy.tree || []));
    nodeMap.clear();
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
    showModal('treeModal');
    updateToolbarButtons();
    document.getElementById('nodeEditorPanel').style.display = 'none';
    document.getElementById('noNodeSelectedMsg').style.display = 'flex';

    const panel = document.getElementById('nodeEditorPanel');
    panel.removeEventListener('click', handleEditScriptClick);
    panel.addEventListener('click', handleEditScriptClick);
}

function handleEditScriptClick(e) {
    const btn = e.target.closest('.edit-node-script-btn');
    if (!btn) return;
    e.preventDefault();
    if (selectedNodeId) {
        const node = nodeMap.get(selectedNodeId);
        if (node) {
            openNodeScriptEditor(node.id, node.branch_name || 'Node', node.script_json || '{}', (id, newScript) => {
                const targetNode = nodeMap.get(id);
                if (targetNode) {
                    targetNode.script_json = newScript;
                    treeUnsaved = true;
                    // Also update the corresponding node in currentTree for consistency
                    updateNodeScriptInTree(currentTree, id, newScript);
                }
            });
        }
    }
}

// Helper to update script in the original tree structure
function updateNodeScriptInTree(nodes, nodeId, newScript) {
    for (let node of nodes) {
        if (node.id === nodeId) {
            node.script_json = newScript;
            return true;
        }
        if (node.children && updateNodeScriptInTree(node.children, nodeId, newScript)) return true;
    }
    return false;
}

function renderTree() {
    const container = document.getElementById('treeContainer');
    container.innerHTML = renderTreeNodes(currentTree, 0);
    attachTreeEvents();
    if (selectedNodeId) {
        const selectedHeader = document.querySelector(`.tree-node-header[data-node-id="${selectedNodeId}"]`);
        if (selectedHeader) {
            selectedHeader.classList.add('selected');
            showNodeEditor(selectedNodeId);
        } else {
            selectedNodeId = null;
            document.getElementById('nodeEditorPanel').style.display = 'none';
            document.getElementById('noNodeSelectedMsg').style.display = 'flex';
        }
    } else {
        document.getElementById('nodeEditorPanel').style.display = 'none';
        document.getElementById('noNodeSelectedMsg').style.display = 'flex';
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
            html += `<div class="tree-children" style="display:block;">${renderTreeNodes(node.children, level+1)}</div>`;
        }
        html += `</div>`;
    });
    return html;
}

function attachTreeEvents() {
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
}

function selectNode(nodeId) {
    if (selectedNodeId) {
        const prev = document.querySelector(`.tree-node-header[data-node-id="${selectedNodeId}"]`);
        if (prev) prev.classList.remove('selected');
    }
    selectedNodeId = nodeId;
    const current = document.querySelector(`.tree-node-header[data-node-id="${selectedNodeId}"]`);
    if (current) current.classList.add('selected');
    showNodeEditor(nodeId);
    updateToolbarButtons();
}

function showNodeEditor(nodeId) {
    const node = nodeMap.get(nodeId);
    if (!node) return;
    document.getElementById('nodeEditorPanel').style.display = 'block';
    document.getElementById('noNodeSelectedMsg').style.display = 'none';

    let branchRow = document.getElementById('nodeBranchRow');
    if (!branchRow) {
        const container = document.getElementById('nodeEditorPanel');
        const firstChild = container.firstChild;
        branchRow = document.createElement('div');
        branchRow.className = 'form-row';
        branchRow.id = 'nodeBranchRow';
        branchRow.innerHTML = `
            <label>Branch Name</label>
            <div style="display: flex; gap: 8px;">
                <input type="text" id="nodeBranchName" style="flex:1;" placeholder="e.g., AskAnother">
                <button class="edit-node-script-btn add-btn" style="margin:0;">✎ Edit Script</button>
            </div>
        `;
        container.insertBefore(branchRow, firstChild);
    } else {
        document.getElementById('nodeBranchName').value = node.branch_name || '';
    }
    document.getElementById('nodeBranchName').value = node.branch_name || '';
    renderNodeQuestionsList(node.questions || []);
}

function renderNodeQuestionsList(questions) {
    const container = document.getElementById('nodeQuestionsList');
    container.innerHTML = '';
    if (!questions || questions.length === 0) {
        const li = document.createElement('li');
        li.style.justifyContent = 'center';
        li.style.color = '#888';
        li.textContent = 'No questions. Add one below.';
        container.appendChild(li);
    } else {
        questions.forEach((q, idx) => {
            const li = document.createElement('li');
            li.innerHTML = `<span>${escapeHtml(q)}</span> <span><button class="edit-node-question" data-idx="${idx}">✎</button><button class="delete-node-question" data-idx="${idx}">🗑</button></span>`;
            container.appendChild(li);
        });
    }
    attachQuestionEvents(questions);
}

function attachQuestionEvents(questions) {
    document.querySelectorAll('.edit-node-question').forEach(btn => {
        btn.addEventListener('click', () => {
            const idx = parseInt(btn.dataset.idx);
            showTextInputModal('Edit Question', questions[idx], (newVal) => {
                questions[idx] = newVal;
                renderNodeQuestionsList(questions);
            });
        });
    });
    document.querySelectorAll('.delete-node-question').forEach(btn => {
        btn.addEventListener('click', () => {
            const idx = parseInt(btn.dataset.idx);
            showConfirmModal('Delete this question?', () => {
                questions.splice(idx, 1);
                renderNodeQuestionsList(questions);
            });
        });
    });
}

function updateToolbarButtons() {
    const hasSelection = selectedNodeId !== null;
    document.getElementById('addChildNodeBtn').disabled = !hasSelection;
    document.getElementById('deleteNodeBtn').disabled = !hasSelection;
}

document.getElementById('addRootNodeBtn').onclick = () => {
    const newNode = {
        branch_name: 'New Node',
        questions: [],
        script_json: '{}',
        children: []
    };
    newNode.id = `node_${nextNodeId++}`;
    nodeMap.set(newNode.id, newNode);
    currentTree.push(newNode);
    treeUnsaved = true;
    renderTree();
    selectNode(newNode.id);
};

document.getElementById('addChildNodeBtn').onclick = () => {
    if (!selectedNodeId) return;
    const parentNode = nodeMap.get(selectedNodeId);
    if (!parentNode) return;
    if (!parentNode.children) parentNode.children = [];
    const newNode = {
        branch_name: 'New Child',
        questions: [],
        script_json: '{}',
        children: []
    };
    newNode.id = `node_${nextNodeId++}`;
    nodeMap.set(newNode.id, newNode);
    parentNode.children.push(newNode);
    treeUnsaved = true;
    renderTree();
    selectNode(newNode.id);
};

document.getElementById('deleteNodeBtn').onclick = () => {
    if (!selectedNodeId) return;
    const node = nodeMap.get(selectedNodeId);
    showConfirmModal(`Delete node "${node.branch_name || 'Unnamed'}" and all its children?`, () => {
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
        document.getElementById('nodeEditorPanel').style.display = 'none';
        document.getElementById('noNodeSelectedMsg').style.display = 'flex';
    });
};

document.getElementById('treeSaveBtn').onclick = () => {
    if (selectedNodeId) {
        const node = nodeMap.get(selectedNodeId);
        node.branch_name = document.getElementById('nodeBranchName').value.trim() || 'Unnamed';
        const questions = [];
        document.querySelectorAll('#nodeQuestionsList li span:first-child').forEach(span => {
            const q = span.textContent.trim();
            if (q) questions.push(q);
        });
        node.questions = questions;
    }
    // Build full tree from nodeMap (which has the latest script_json)
    function buildFullTree(nodes) {
        return nodes.map(node => {
            const mapNode = nodeMap.get(node.id);
            return {
                id: node.dbId,
                branch_name: node.branch_name,
                questions: node.questions || [],
                script_json: mapNode ? mapNode.script_json : (node.script_json || '{}'),
                children: buildFullTree(node.children || [])
            };
        });
    }
    const fullTree = buildFullTree(currentTree);
    pluginCopy.tree = fullTree;
    treeUnsaved = false;
    hideModal('treeModal');
};

document.getElementById('treeCancelBtn').onclick = () => {
    if (treeUnsaved && !confirm('You have unsaved changes. Discard them?')) return;
    hideModal('treeModal');
};

document.getElementById('addNodeQuestionBtn').onclick = () => {
    if (!selectedNodeId) return;
    const node = nodeMap.get(selectedNodeId);
    const questions = node.questions || [];
    showTextInputModal('Add Question', '', (newVal) => {
        questions.push(newVal);
        node.questions = questions;
        renderNodeQuestionsList(questions);
        treeUnsaved = true;
    });
};
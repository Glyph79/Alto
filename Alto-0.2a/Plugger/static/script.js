// ------------------------------------------------------------------
// Global state
// ------------------------------------------------------------------
let plugins = [];
let currentPluginName = null;
let pluginCopy = null;

// DOM elements
const gridContainer = document.getElementById('pluginsGridContainer');
const emptyState = document.getElementById('emptyState');
const searchInput = document.getElementById('searchInput');
const sortSelect = document.getElementById('sortSelect');
const newPluginBtn = document.getElementById('newPluginBtn');

// ------------------------------------------------------------------
// API helpers
// ------------------------------------------------------------------
async function apiGet(url) {
    const res = await fetch(url);
    if (!res.ok) throw new Error(await res.text());
    return res.json();
}
async function apiPost(url, data) {
    const res = await fetch(url, {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify(data)
    });
    if (!res.ok) throw new Error(await res.text());
    return res.json();
}
async function apiPut(url, data) {
    const res = await fetch(url, {
        method: 'PUT',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify(data)
    });
    if (!res.ok) throw new Error(await res.text());
    return res.json();
}
async function apiDelete(url) {
    const res = await fetch(url, {method: 'DELETE'});
    if (!res.ok) throw new Error(await res.text());
    return res.json();
}

// ------------------------------------------------------------------
// Custom modal helpers
// ------------------------------------------------------------------
function showAlertModal(title, message, onClose) {
    const modal = document.getElementById('simpleModal');
    const content = document.getElementById('simpleModalContent');
    content.innerHTML = `
        <h2>${escapeHtml(title)}</h2>
        <p style="margin: 20px 0; color: #ccc;">${escapeHtml(message)}</p>
        <div class="modal-actions">
            <button class="save" id="alertOkBtn">OK</button>
        </div>
    `;
    showModal('simpleModal');
    document.getElementById('alertOkBtn').onclick = () => {
        hideModal('simpleModal');
        if (onClose) onClose();
    };
}

function showTextInputModal(title, initialValue, onSave) {
    const modal = document.getElementById('simpleModal');
    const content = document.getElementById('simpleModalContent');
    content.innerHTML = `
        <h2>${escapeHtml(title)}</h2>
        <div class="form-row">
            <input type="text" id="modalInput" value="${escapeHtml(initialValue)}" style="width:100%;">
        </div>
        <div id="modalError" style="color:#ff6b9d; margin-bottom:12px; display:none;"></div>
        <div class="modal-actions">
            <button class="cancel" id="modalCancel">Cancel</button>
            <button class="save" id="modalSave">Save</button>
        </div>
    `;
    showModal('simpleModal');

    const input = document.getElementById('modalInput');
    const errorDiv = document.getElementById('modalError');
    const saveBtn = document.getElementById('modalSave');
    const cancelBtn = document.getElementById('modalCancel');

    saveBtn.onclick = () => {
        const value = input.value.trim();
        if (!value) {
            errorDiv.textContent = 'Value cannot be empty.';
            errorDiv.style.display = 'block';
            return;
        }
        onSave(value);
        hideModal('simpleModal');
    };
    cancelBtn.onclick = () => hideModal('simpleModal');
}

function showConfirmModal(message, onConfirm) {
    const modal = document.getElementById('simpleModal');
    const content = document.getElementById('simpleModalContent');
    content.innerHTML = `
        <h2>Confirm</h2>
        <p style="margin: 20px 0; color: #ccc;">${escapeHtml(message)}</p>
        <div class="modal-actions">
            <button class="cancel" id="confirmCancel">Cancel</button>
            <button class="save" id="confirmDelete">Delete</button>
        </div>
    `;
    showModal('simpleModal');

    const cancelBtn = document.getElementById('confirmCancel');
    const deleteBtn = document.getElementById('confirmDelete');

    cancelBtn.onclick = () => hideModal('simpleModal');
    deleteBtn.onclick = () => {
        hideModal('simpleModal');
        onConfirm();
    };
}

// ------------------------------------------------------------------
// Load plugins from server
// ------------------------------------------------------------------
async function loadPlugins() {
    try {
        plugins = await apiGet('/api/plugins');
        renderPlugins();
    } catch (err) {
        showAlertModal('Error', 'Error loading plugins: ' + err.message);
    }
}

// ------------------------------------------------------------------
// Rendering plugins (grid)
// ------------------------------------------------------------------
function renderPlugins() {
    const searchTerm = searchInput.value.toLowerCase();
    let filtered = plugins.filter(p => p.name.toLowerCase().includes(searchTerm) ||
                                        (p.description && p.description.toLowerCase().includes(searchTerm)));

    const sortBy = sortSelect.value;
    filtered.sort((a, b) => {
        if (sortBy === 'name-asc') return a.name.localeCompare(b.name);
        if (sortBy === 'name-desc') return b.name.localeCompare(a.name);
        if (sortBy === 'version-desc') return b.version.localeCompare(a.version);
        if (sortBy === 'version-asc') return a.version.localeCompare(b.version);
        return 0;
    });

    if (filtered.length === 0) {
        gridContainer.innerHTML = '';
        emptyState.style.display = 'block';
        return;
    }
    emptyState.style.display = 'none';

    let html = '<div class="plugins-grid">';
    filtered.forEach(p => {
        html += `
            <div class="plugin-card" data-name="${escapeHtml(p.name)}">
                <div class="header">
                    <span class="version">v${escapeHtml(p.version)}</span>
                    <div class="card-actions">
                        <button class="edit-plugin" title="Edit">✎</button>
                        <button class="delete-plugin" title="Delete">🗑</button>
                    </div>
                </div>
                <h4>${escapeHtml(p.name)}</h4>
                <div class="description">${escapeHtml(p.description || '')}</div>
            </div>
        `;
    });
    html += '</div>';
    gridContainer.innerHTML = html;

    document.querySelectorAll('.plugin-card').forEach(card => {
        const name = card.dataset.name;
        card.addEventListener('click', (e) => {
            if (e.target.closest('.card-actions')) return;
            openPluginModal(name);
        });
        card.querySelector('.edit-plugin').addEventListener('click', (e) => {
            e.stopPropagation();
            openPluginModal(name);
        });
        card.querySelector('.delete-plugin').addEventListener('click', (e) => {
            e.stopPropagation();
            deletePlugin(name);
        });
    });
}

function escapeHtml(str) {
    if (!str) return '';
    return str.replace(/[&<>]/g, function(m) {
        if (m === '&') return '&amp;';
        if (m === '<') return '&lt;';
        if (m === '>') return '&gt;';
        return m;
    });
}

// ------------------------------------------------------------------
// Plugin modal: load data and show
// ------------------------------------------------------------------
async function openPluginModal(name) {
    currentPluginName = name;
    const isNew = name === null;
    const title = isNew ? 'Create New Plugin' : 'Edit Plugin';
    document.getElementById('pluginModalTitle').innerText = title;

    if (isNew) {
        pluginCopy = {
            name: '',
            version: '1.0.0',
            description: '',
            triggers: [],
            response: { type: 'static', answers: [] },
            mappings: {},
            tree: []
        };
        document.getElementById('pluginName').value = '';
        document.getElementById('pluginVersion').value = '1.0.0';
        document.getElementById('pluginDescription').value = '';
    } else {
        try {
            const plugin = await apiGet(`/api/plugins/${encodeURIComponent(name)}`);
            pluginCopy = JSON.parse(JSON.stringify(plugin));
            document.getElementById('pluginName').value = plugin.name;
            document.getElementById('pluginVersion').value = plugin.version;
            document.getElementById('pluginDescription').value = plugin.description || '';
        } catch (err) {
            showAlertModal('Error', 'Failed to load plugin: ' + err.message);
            return;
        }
    }

    renderQuestionsList();
    renderAnswersList();
    renderApiFields();
    renderMappingsList();

    const responseType = pluginCopy.response?.type || 'static';
    document.querySelector(`input[name="responseType"][value="${responseType}"]`).checked = true;
    toggleResponseSections(responseType);

    showModal('pluginModal');
}

// ------------------------------------------------------------------
// Questions list management
// ------------------------------------------------------------------
function renderQuestionsList() {
    const list = document.getElementById('questionsList');
    list.innerHTML = '';
    (pluginCopy.triggers || []).forEach((trigger, idx) => {
        const li = document.createElement('li');
        li.innerHTML = `<span>${escapeHtml(trigger)}</span> <span><button onclick="editQuestion(${idx})">✎</button><button onclick="deleteQuestion(${idx})">🗑</button></span>`;
        list.appendChild(li);
    });
}
window.editQuestion = (idx) => {
    const current = pluginCopy.triggers[idx];
    showTextInputModal('Edit Question', current, (newVal) => {
        pluginCopy.triggers[idx] = newVal;
        renderQuestionsList();
    });
};
window.deleteQuestion = (idx) => {
    showConfirmModal('Delete this question?', () => {
        pluginCopy.triggers.splice(idx, 1);
        renderQuestionsList();
    });
};
document.getElementById('addQuestionBtn').onclick = () => {
    showTextInputModal('Add Question', '', (newVal) => {
        if (!pluginCopy.triggers) pluginCopy.triggers = [];
        pluginCopy.triggers.push(newVal);
        renderQuestionsList();
    });
};

// ------------------------------------------------------------------
// Static answers list management (root)
// ------------------------------------------------------------------
function renderAnswersList() {
    const list = document.getElementById('answersList');
    list.innerHTML = '';
    const answers = pluginCopy.response?.answers || [];
    answers.forEach((ans, idx) => {
        const li = document.createElement('li');
        li.innerHTML = `<span>${escapeHtml(ans)}</span> <span><button onclick="editAnswer(${idx})">✎</button><button onclick="deleteAnswer(${idx})">🗑</button></span>`;
        list.appendChild(li);
    });
}
window.editAnswer = (idx) => {
    const current = pluginCopy.response.answers[idx];
    showTextInputModal('Edit Answer', current, (newVal) => {
        pluginCopy.response.answers[idx] = newVal;
        renderAnswersList();
    });
};
window.deleteAnswer = (idx) => {
    showConfirmModal('Delete this answer?', () => {
        pluginCopy.response.answers.splice(idx, 1);
        renderAnswersList();
    });
};
document.getElementById('addAnswerBtn').onclick = () => {
    showTextInputModal('Add Answer', '', (newVal) => {
        if (!pluginCopy.response) pluginCopy.response = { type: 'static', answers: [] };
        if (!pluginCopy.response.answers) pluginCopy.response.answers = [];
        pluginCopy.response.answers.push(newVal);
        renderAnswersList();
    });
};

// ------------------------------------------------------------------
// API fields population (root) – now with conditional templates
// ------------------------------------------------------------------
function renderApiFields() {
    const resp = pluginCopy.response || { type: 'static' };
    document.getElementById('apiUrl').value = resp.url || '';
    renderConditionalTemplates();
}

function renderConditionalTemplates() {
    const container = document.getElementById('conditionalTemplatesList');
    const templates = pluginCopy.response?.conditionalTemplates || [];
    if (templates.length === 0) {
        container.innerHTML = '<div style="color:#888; text-align:center; padding:16px;">No conditional templates. Add one to handle different API responses.</div>';
        return;
    }
    let html = '<div class="conditional-grid">';
    templates.forEach((item, idx) => {
        html += `
            <div class="conditional-card" data-index="${idx}">
                <div class="conditional-header">
                    <span class="condition">${escapeHtml(item.condition) || '(always)'}</span>
                    <div class="card-actions">
                        <button class="move-up" title="Move Up" ${idx === 0 ? 'disabled' : ''}>↑</button>
                        <button class="move-down" title="Move Down" ${idx === templates.length-1 ? 'disabled' : ''}>↓</button>
                        <button class="edit-conditional" title="Edit">✎</button>
                        <button class="delete-conditional" title="Delete">🗑</button>
                    </div>
                </div>
                <div class="template-preview">${escapeHtml(item.template)}</div>
            </div>
        `;
    });
    html += '</div>';
    container.innerHTML = html;

    // Add event listeners
    container.querySelectorAll('.move-up').forEach(btn => {
        btn.addEventListener('click', (e) => {
            e.stopPropagation();
            const card = btn.closest('.conditional-card');
            const idx = parseInt(card.dataset.index);
            if (idx > 0) {
                const arr = pluginCopy.response.conditionalTemplates;
                [arr[idx-1], arr[idx]] = [arr[idx], arr[idx-1]];
                renderConditionalTemplates();
            }
        });
    });
    container.querySelectorAll('.move-down').forEach(btn => {
        btn.addEventListener('click', (e) => {
            e.stopPropagation();
            const card = btn.closest('.conditional-card');
            const idx = parseInt(card.dataset.index);
            const arr = pluginCopy.response.conditionalTemplates;
            if (idx < arr.length-1) {
                [arr[idx], arr[idx+1]] = [arr[idx+1], arr[idx]];
                renderConditionalTemplates();
            }
        });
    });
    container.querySelectorAll('.edit-conditional').forEach(btn => {
        btn.addEventListener('click', (e) => {
            e.stopPropagation();
            const card = btn.closest('.conditional-card');
            const idx = parseInt(card.dataset.index);
            editConditionalTemplate(idx);
        });
    });
    container.querySelectorAll('.delete-conditional').forEach(btn => {
        btn.addEventListener('click', (e) => {
            e.stopPropagation();
            const card = btn.closest('.conditional-card');
            const idx = parseInt(card.dataset.index);
            showConfirmModal('Delete this conditional template?', () => {
                pluginCopy.response.conditionalTemplates.splice(idx, 1);
                renderConditionalTemplates();
            });
        });
    });
}

function editConditionalTemplate(idx) {
    const item = pluginCopy.response.conditionalTemplates[idx];
    // Create a simple modal with two fields
    const modal = document.getElementById('simpleModal');
    const content = document.getElementById('simpleModalContent');
    content.innerHTML = `
        <h2>Edit Conditional Template</h2>
        <div class="form-row">
            <label>Condition (leave empty for default)</label>
            <input type="text" id="condCondition" value="${escapeHtml(item.condition || '')}" placeholder="e.g., {temperature} > 80 or {weathercode} == 0">
        </div>
        <div class="form-row">
            <label>Template</label>
            <textarea id="condTemplate" rows="3">${escapeHtml(item.template)}</textarea>
        </div>
        <div class="modal-actions">
            <button class="cancel" id="condCancel">Cancel</button>
            <button class="save" id="condSave">Save</button>
        </div>
    `;
    showModal('simpleModal');

    document.getElementById('condCancel').onclick = () => hideModal('simpleModal');
    document.getElementById('condSave').onclick = () => {
        const condition = document.getElementById('condCondition').value.trim();
        const template = document.getElementById('condTemplate').value.trim();
        if (!template) {
            showAlertModal('Error', 'Template cannot be empty');
            return;
        }
        pluginCopy.response.conditionalTemplates[idx] = { condition, template };
        renderConditionalTemplates();
        hideModal('simpleModal');
    };
}

document.getElementById('addConditionalTemplateBtn').onclick = () => {
    // Open a modal to add new conditional template
    const modal = document.getElementById('simpleModal');
    const content = document.getElementById('simpleModalContent');
    content.innerHTML = `
        <h2>Add Conditional Template</h2>
        <div class="form-row">
            <label>Condition (leave empty for default)</label>
            <input type="text" id="condCondition" placeholder="e.g., {temperature} > 80 or {weathercode} == 0">
        </div>
        <div class="form-row">
            <label>Template</label>
            <textarea id="condTemplate" rows="3" placeholder="The weather is {temperature}°C and {conditions}."></textarea>
        </div>
        <div class="modal-actions">
            <button class="cancel" id="condCancel">Cancel</button>
            <button class="save" id="condSave">Add</button>
        </div>
    `;
    showModal('simpleModal');

    document.getElementById('condCancel').onclick = () => hideModal('simpleModal');
    document.getElementById('condSave').onclick = () => {
        const condition = document.getElementById('condCondition').value.trim();
        const template = document.getElementById('condTemplate').value.trim();
        if (!template) {
            showAlertModal('Error', 'Template cannot be empty');
            return;
        }
        if (!pluginCopy.response.conditionalTemplates) pluginCopy.response.conditionalTemplates = [];
        pluginCopy.response.conditionalTemplates.push({ condition, template });
        renderConditionalTemplates();
        hideModal('simpleModal');
    };
};

function getApiFields() {
    return {
        url: document.getElementById('apiUrl').value.trim(),
        conditionalTemplates: pluginCopy.response?.conditionalTemplates || []
    };
}

// ------------------------------------------------------------------
// Response type toggle (root)
// ------------------------------------------------------------------
function toggleResponseSections(type) {
    const staticDiv = document.getElementById('staticResponseSection');
    const apiDiv = document.getElementById('apiResponseSection');
    if (type === 'static') {
        staticDiv.style.display = 'block';
        apiDiv.style.display = 'none';
    } else {
        staticDiv.style.display = 'none';
        apiDiv.style.display = 'block';
    }
}
document.querySelectorAll('input[name="responseType"]').forEach(radio => {
    radio.addEventListener('change', (e) => {
        if (e.target.checked) {
            const type = e.target.value;
            toggleResponseSections(type);
            if (!pluginCopy.response) pluginCopy.response = {};
            pluginCopy.response.type = type;
        }
    });
});

// ------------------------------------------------------------------
// Mappings management
// ------------------------------------------------------------------
function renderMappingsList() {
    const container = document.getElementById('mappingsList');
    const mappings = pluginCopy.mappings || {};
    if (Object.keys(mappings).length === 0) {
        container.innerHTML = '<div style="color:#888;">No mapping tables yet. Add one to capture values.</div>';
        return;
    }
    let html = '<div class="mappings-grid">';
    for (let [tableName, table] of Object.entries(mappings)) {
        const fieldNames = table.fields || [];
        const entryCount = Object.keys(table.entries || {}).length;
        html += `
            <div class="mapping-card" data-table="${escapeHtml(tableName)}">
                <div class="header">
                    <strong>${escapeHtml(tableName)}</strong>
                    <div class="card-actions">
                        <button class="edit-mapping" title="Edit">✎</button>
                        <button class="delete-mapping" title="Delete">🗑</button>
                    </div>
                </div>
                <div class="mapping-details">
                    <span>${entryCount} entr${entryCount !== 1 ? 'ies' : 'y'}</span> · 
                    <span>fields: ${fieldNames.map(f => escapeHtml(f)).join(', ')}</span>
                </div>
            </div>
        `;
    }
    html += '</div>';
    container.innerHTML = html;

    document.querySelectorAll('.edit-mapping').forEach(btn => {
        const card = btn.closest('.mapping-card');
        const tableName = card.dataset.table;
        btn.addEventListener('click', (e) => {
            e.stopPropagation();
            openMappingEditor(tableName);
        });
    });
    document.querySelectorAll('.delete-mapping').forEach(btn => {
        const card = btn.closest('.mapping-card');
        const tableName = card.dataset.table;
        btn.addEventListener('click', (e) => {
            e.stopPropagation();
            showConfirmModal(`Delete mapping table "${tableName}"?`, () => {
                delete pluginCopy.mappings[tableName];
                renderMappingsList();
            });
        });
    });
}

function openMappingEditor(tableName = null) {
    const mappings = pluginCopy.mappings || {};
    let table = tableName ? mappings[tableName] : null;
    const isNew = !table;

    let html = `
        <div style="min-width: 500px;">
            <h3>${isNew ? 'Add Mapping Table' : 'Edit Mapping Table'}</h3>
            <div class="form-row">
                <label>Table Name</label>
                <input type="text" id="mappingName" value="${tableName ? escapeHtml(tableName) : ''}" ${!isNew ? 'disabled' : ''}>
            </div>
            <div class="form-row">
                <label>Field Names (comma‑separated)</label>
                <input type="text" id="mappingFields" value="${table ? (table.fields || []).join(', ') : ''}" placeholder="e.g., latitude, longitude">
            </div>
            <div class="form-row">
                <label>Entries</label>
                <div id="entriesContainer"></div>
                <button class="add-btn" id="addEntryBtn">+ Add Entry</button>
            </div>
            <div class="modal-actions">
                <button class="cancel" id="mappingCancelBtn">Cancel</button>
                <button class="save" id="mappingSaveBtn">Save</button>
            </div>
        </div>
    `;

    const modal = document.getElementById('simpleModal');
    const content = document.getElementById('simpleModalContent');
    content.innerHTML = html;
    showModal('simpleModal');

    function renderEntriesList(entries) {
        const container = document.getElementById('entriesContainer');
        if (!container) return;
        const fields = document.getElementById('mappingFields').value.split(',').map(s => s.trim()).filter(s => s);
        let entriesHtml = '<div style="background:#2d2d5a; border-radius:8px; padding:8px;">';
        for (let [key, values] of Object.entries(entries)) {
            entriesHtml += `
                <div class="entry-row" style="margin-bottom:12px; border-bottom:1px solid #3d3d7a; padding-bottom:8px;">
                    <div style="display:flex; gap:8px; align-items:center;">
                        <input type="text" placeholder="Key (word to match)" value="${escapeHtml(key)}" style="flex:1;">
                        ${fields.map(f => `
                            <input type="text" placeholder="${f}" value="${escapeHtml(values[f] || '')}" style="flex:1;">
                        `).join('')}
                        <button class="delete-entry" style="background:none; border:none; color:#ff6b9d;">🗑</button>
                    </div>
                </div>
            `;
        }
        entriesHtml += '</div>';
        container.innerHTML = entriesHtml;

        container.querySelectorAll('.delete-entry').forEach(btn => {
            btn.addEventListener('click', () => {
                btn.closest('.entry-row').remove();
            });
        });
    }

    const fieldsInput = document.getElementById('mappingFields');
    fieldsInput.addEventListener('change', () => {
        const entries = getCurrentEntries();
        renderEntriesList(entries);
    });

    function getCurrentEntries() {
        const entries = {};
        const rows = document.querySelectorAll('.entry-row');
        rows.forEach(row => {
            const inputs = row.querySelectorAll('input');
            if (!inputs.length) return;
            const key = inputs[0].value.trim();
            if (!key) return;
            const values = {};
            const fields = document.getElementById('mappingFields').value.split(',').map(s => s.trim()).filter(s => s);
            const inputArray = Array.from(inputs);
            inputArray.slice(1, 1 + fields.length).forEach((input, idx) => {
                values[fields[idx]] = input.value.trim();
            });
            entries[key] = values;
        });
        return entries;
    }

    if (!isNew && table && table.entries) {
        renderEntriesList(table.entries);
    } else {
        renderEntriesList({});
    }

    document.getElementById('mappingSaveBtn').onclick = () => {
        const name = document.getElementById('mappingName').value.trim();
        if (!name) {
            showAlertModal('Validation Error', 'Table name is required.');
            return;
        }
        const fieldsStr = document.getElementById('mappingFields').value;
        const fields = fieldsStr.split(',').map(s => s.trim()).filter(s => s);
        if (fields.length === 0) {
            showAlertModal('Validation Error', 'At least one field name is required.');
            return;
        }
        const entries = getCurrentEntries();

        if (isNew && pluginCopy.mappings[name]) {
            showAlertModal('Validation Error', 'A mapping table with that name already exists.');
            return;
        }

        if (!pluginCopy.mappings) pluginCopy.mappings = {};
        pluginCopy.mappings[name] = { fields, entries };
        renderMappingsList();
        hideModal('simpleModal');
    };
    document.getElementById('mappingCancelBtn').onclick = () => {
        hideModal('simpleModal');
    };
    document.getElementById('addEntryBtn').onclick = () => {
        const entries = getCurrentEntries();
        entries[''] = {};
        renderEntriesList(entries);
    };
}

document.getElementById('addMappingBtn').onclick = () => {
    openMappingEditor(null);
};

// ------------------------------------------------------------------
// Tree editor (nodes have static answers only)
// ------------------------------------------------------------------
let currentTree = [];
let nodeMap = new Map();
let nodeDetailsCache = new Map(); // nodeId -> { questions, answers }
let nextNodeId = 0;
let selectedNodeId = null;
let treeUnsaved = false;

function openTreeEditor() {
    // Copy the current tree from pluginCopy
    currentTree = JSON.parse(JSON.stringify(pluginCopy.tree || []));
    nodeMap.clear();
    nodeDetailsCache.clear();
    nextNodeId = 0;
    function buildMap(nodes) {
        nodes.forEach(node => {
            node.dbId = node.id;          // preserve real DB id (undefined for new nodes)
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
    document.getElementById('nodeQAPanel').style.display = 'none';
    document.getElementById('noNodeSelected').style.display = 'flex';
}

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

function showNodeQAPanel(nodeId) {
    const node = nodeMap.get(nodeId);
    if (!node) return;

    // Load from cache or use node's own data
    let fullNode = nodeDetailsCache.get(nodeId);
    if (!fullNode) {
        fullNode = {
            questions: node.questions || [],
            answers: node.answers || []
        };
        nodeDetailsCache.set(nodeId, fullNode);
    }

    document.getElementById('nodeQAPanel').style.display = 'block';
    document.getElementById('noNodeSelected').style.display = 'none';

    renderNodeQAPanel(fullNode);
}

function renderNodeQAPanel(fullNode) {
    // Questions list
    const qList = document.getElementById('treeQuestionsList');
    qList.innerHTML = '';
    (fullNode.questions || []).forEach((q, i) => {
        const li = document.createElement('li');
        li.innerHTML = `<span>${escapeHtml(q)}</span> <span><button onclick="editTreeNodeQuestion(${i})">✎</button><button onclick="deleteTreeNodeQuestion(${i})">🗑</button></span>`;
        qList.appendChild(li);
    });

    // Answers list
    const aList = document.getElementById('treeAnswersList');
    aList.innerHTML = '';
    (fullNode.answers || []).forEach((a, i) => {
        const li = document.createElement('li');
        li.innerHTML = `<span>${escapeHtml(a)}</span> <span><button onclick="editTreeNodeAnswer(${i})">✎</button><button onclick="deleteTreeNodeAnswer(${i})">🗑</button></span>`;
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
    const newNode = {
        branch_name: 'New Root',
        questions: [],
        answers: [],
        children: []
    };
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
    const newNode = {
        branch_name: 'New Branch',
        questions: [],
        answers: [],
        children: []
    };
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
    showTextInputModal('Edit Node Name', node.branch_name || '', (newName) => {
        node.branch_name = newName;
        treeUnsaved = true;
        renderTree();
    });
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

// Node Q&A editing
window.editTreeNodeQuestion = (qIdx) => {
    const node = nodeMap.get(selectedNodeId);
    const fullNode = nodeDetailsCache.get(selectedNodeId) || { questions: node.questions || [], answers: node.answers || [] };
    showTextInputModal('Edit Question', fullNode.questions[qIdx], (newVal) => {
        fullNode.questions[qIdx] = newVal;
        nodeDetailsCache.set(selectedNodeId, fullNode);
        treeUnsaved = true;
        showNodeQAPanel(selectedNodeId);
    });
};

window.deleteTreeNodeQuestion = (qIdx) => {
    showConfirmModal('Delete this question?', () => {
        const fullNode = nodeDetailsCache.get(selectedNodeId) || { questions: [], answers: [] };
        fullNode.questions.splice(qIdx, 1);
        nodeDetailsCache.set(selectedNodeId, fullNode);
        treeUnsaved = true;
        showNodeQAPanel(selectedNodeId);
    });
};

window.editTreeNodeAnswer = (aIdx) => {
    const node = nodeMap.get(selectedNodeId);
    const fullNode = nodeDetailsCache.get(selectedNodeId) || { questions: node.questions || [], answers: node.answers || [] };
    showTextInputModal('Edit Answer', fullNode.answers[aIdx], (newVal) => {
        fullNode.answers[aIdx] = newVal;
        nodeDetailsCache.set(selectedNodeId, fullNode);
        treeUnsaved = true;
        showNodeQAPanel(selectedNodeId);
    });
};

window.deleteTreeNodeAnswer = (aIdx) => {
    showConfirmModal('Delete this answer?', () => {
        const fullNode = nodeDetailsCache.get(selectedNodeId) || { questions: [], answers: [] };
        fullNode.answers.splice(aIdx, 1);
        nodeDetailsCache.set(selectedNodeId, fullNode);
        treeUnsaved = true;
        showNodeQAPanel(selectedNodeId);
    });
};

document.getElementById('treeAddQuestionBtn').onclick = () => {
    if (!selectedNodeId) return;
    showTextInputModal('Add Question', '', (newQ) => {
        const fullNode = nodeDetailsCache.get(selectedNodeId) || { questions: [], answers: [] };
        if (!fullNode.questions) fullNode.questions = [];
        fullNode.questions.push(newQ);
        nodeDetailsCache.set(selectedNodeId, fullNode);
        treeUnsaved = true;
        showNodeQAPanel(selectedNodeId);
    });
};

document.getElementById('treeAddAnswerBtn').onclick = () => {
    if (!selectedNodeId) return;
    showTextInputModal('Add Answer', '', (newA) => {
        const fullNode = nodeDetailsCache.get(selectedNodeId) || { questions: [], answers: [] };
        if (!fullNode.answers) fullNode.answers = [];
        fullNode.answers.push(newA);
        nodeDetailsCache.set(selectedNodeId, fullNode);
        treeUnsaved = true;
        showNodeQAPanel(selectedNodeId);
    });
};

// Tree modal save/cancel
document.getElementById('treeModalSaveBtn').onclick = () => {
    function buildFullTree(nodes) {
        return nodes.map(node => {
            const cached = nodeDetailsCache.get(node.id);
            return {
                id: node.dbId,
                branch_name: node.branch_name,
                questions: cached ? cached.questions : (node.questions || []),
                answers: cached ? cached.answers : (node.answers || []),
                children: buildFullTree(node.children || [])
            };
        });
    }
    const fullTree = buildFullTree(currentTree);
    pluginCopy.tree = fullTree;
    treeUnsaved = false;
    hideModal('treeModal');
};

document.getElementById('treeModalCancelBtn').onclick = () => {
    if (treeUnsaved && !confirm('You have unsaved changes. Discard them?')) return;
    hideModal('treeModal');
};

document.getElementById('editTreeBtn').onclick = () => {
    openTreeEditor();
};

// ------------------------------------------------------------------
// Save plugin modal
// ------------------------------------------------------------------
document.getElementById('pluginSaveBtn').onclick = async () => {
    const name = document.getElementById('pluginName').value.trim();
    const version = document.getElementById('pluginVersion').value.trim();
    const description = document.getElementById('pluginDescription').value.trim();
    if (!name) {
        showAlertModal('Validation Error', 'Name is required');
        return;
    }
    const triggers = pluginCopy.triggers || [];
    const responseType = document.querySelector('input[name="responseType"]:checked').value;
    let response = { type: responseType };
    if (responseType === 'static') {
        response.answers = pluginCopy.response?.answers || [];
    } else {
        const api = getApiFields();
        response.url = api.url;
        response.conditionalTemplates = api.conditionalTemplates;
        if (!response.url) {
            showAlertModal('Validation Error', 'URL is required for API response');
            return;
        }
        if (!response.conditionalTemplates || response.conditionalTemplates.length === 0) {
            showAlertModal('Validation Error', 'At least one conditional template is required for API response');
            return;
        }
    }

    const data = {
        name, version, description,
        triggers,
        response,
        mappings: pluginCopy.mappings || {},
        tree: pluginCopy.tree
    };

    try {
        if (currentPluginName === null) {
            await apiPost('/api/plugins', data);
        } else {
            await apiPut(`/api/plugins/${encodeURIComponent(currentPluginName)}`, data);
        }
        hideModal('pluginModal');
        await loadPlugins();
    } catch (err) {
        showAlertModal('Error', 'Error saving plugin: ' + err.message);
    }
};

document.getElementById('pluginCancelBtn').onclick = () => {
    hideModal('pluginModal');
};

// ------------------------------------------------------------------
// Delete plugin
// ------------------------------------------------------------------
async function deletePlugin(name) {
    showConfirmModal(`Delete plugin "${name}"? This action cannot be undone.`, async () => {
        try {
            await apiDelete(`/api/plugins/${encodeURIComponent(name)}`);
            await loadPlugins();
        } catch (err) {
            showAlertModal('Error', 'Error deleting plugin: ' + err.message);
        }
    });
}

// ------------------------------------------------------------------
// Modal helpers
// ------------------------------------------------------------------
function showModal(id) {
    const modal = document.getElementById(id);
    modal.classList.add('visible');
}
function hideModal(id) {
    const modal = document.getElementById(id);
    modal.classList.remove('visible');
}

// ------------------------------------------------------------------
// Event listeners
// ------------------------------------------------------------------
searchInput.addEventListener('input', () => renderPlugins());
sortSelect.addEventListener('change', () => renderPlugins());
newPluginBtn.onclick = () => openPluginModal(null);

// Start
loadPlugins();
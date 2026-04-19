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
// Retry & loading utilities (self-contained)
// ------------------------------------------------------------------
const RETRY_CONFIG = {
    maxAttempts: 3,
    baseDelayMs: 200,
    loadingDelayMs: 300,
    backoffFactor: 2,
};

function delay(ms) {
    return new Promise(resolve => setTimeout(resolve, ms));
}

async function retryOperation(operation, options = {}) {
    const config = { ...RETRY_CONFIG, ...options };
    let lastError;
    for (let attempt = 1; attempt <= config.maxAttempts; attempt++) {
        try {
            return await operation();
        } catch (err) {
            lastError = err;
            if (attempt === config.maxAttempts) break;
            const wait = config.baseDelayMs * Math.pow(config.backoffFactor, attempt - 1);
            await delay(wait);
        }
    }
    throw lastError;
}

function showInlineLoading(container, text = "Loading", delayMs = null) {
    const delayTime = delayMs !== null ? delayMs : RETRY_CONFIG.loadingDelayMs;
    let timeout = null;
    let loadingElement = null;

    const clear = () => {
        if (timeout) {
            clearTimeout(timeout);
            timeout = null;
        }
        if (loadingElement && loadingElement.parentNode) {
            loadingElement.remove();
            loadingElement = null;
        }
    };

    timeout = setTimeout(() => {
        loadingElement = document.createElement('div');
        loadingElement.className = 'inline-loading';
        loadingElement.innerHTML = `
            <div class="inline-spinner"></div>
            <span>${text}...</span>
        `;
        container.appendChild(loadingElement);
        timeout = null;
    }, delayTime);

    return { clear };
}

function showInlineListRetry(listElement, itemType, retryCallback) {
    listElement.innerHTML = '';
    const li = document.createElement('li');
    li.className = 'retry-list-item';
    li.innerHTML = `
        <span style="color:#ffaa66;">⚠️ Failed to load ${itemType}.</span>
        <button class="retry-list-btn" style="margin-left:12px; background:#6c63ff; border:none; border-radius:4px; padding:4px 12px; color:white; cursor:pointer;">Retry</button>
    `;
    const btn = li.querySelector('.retry-list-btn');
    btn.addEventListener('click', async (e) => {
        e.preventDefault();
        btn.disabled = true;
        btn.textContent = '...';
        try {
            await retryCallback();
        } catch (err) {
            btn.disabled = false;
            btn.textContent = 'Retry';
            const span = li.querySelector('span');
            span.textContent = `⚠️ Failed: ${err.message}`;
        }
    });
    listElement.appendChild(li);
}

function showRetryError(container, message, retryCallback) {
    const existing = container.querySelector('.retry-error');
    if (existing) existing.remove();

    const errorDiv = document.createElement('div');
    errorDiv.className = 'retry-error';
    errorDiv.innerHTML = `
        <div class="error-icon">⚠️</div>
        <div class="error-message">${escapeHtml(message)}</div>
        <button class="retry-btn">Retry</button>
    `;
    const btn = errorDiv.querySelector('.retry-btn');
    btn.addEventListener('click', async (e) => {
        e.preventDefault();
        btn.disabled = true;
        btn.textContent = 'Retrying...';
        try {
            await retryCallback();
            errorDiv.remove();
        } catch (err) {
            btn.disabled = false;
            btn.textContent = 'Retry';
            const msgDiv = errorDiv.querySelector('.error-message');
            msgDiv.textContent = `Failed: ${err.message}`;
        }
    });
    container.appendChild(errorDiv);
    return errorDiv;
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
// Modal helpers
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

function showModal(id) {
    const modal = document.getElementById(id);
    modal.classList.add('visible');
}
function hideModal(id) {
    const modal = document.getElementById(id);
    modal.classList.remove('visible');
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
                        <button class="edit-plugin" data-name="${escapeHtml(p.name)}" title="Edit">✎</button>
                        <button class="delete-plugin" data-name="${escapeHtml(p.name)}" title="Delete">🗑</button>
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
    });
    document.querySelectorAll('.edit-plugin').forEach(btn => {
        btn.addEventListener('click', (e) => {
            e.stopPropagation();
            openPluginModal(btn.dataset.name);
        });
    });
    document.querySelectorAll('.delete-plugin').forEach(btn => {
        btn.addEventListener('click', (e) => {
            e.stopPropagation();
            deletePlugin(btn.dataset.name);
        });
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
// Questions list management (no inline onclick)
// ------------------------------------------------------------------
function renderQuestionsList() {
    const list = document.getElementById('questionsList');
    list.innerHTML = '';
    (pluginCopy.triggers || []).forEach((trigger, idx) => {
        const li = document.createElement('li');
        li.innerHTML = `<span>${escapeHtml(trigger)}</span> <span><button class="edit-question" data-idx="${idx}">✎</button><button class="delete-question" data-idx="${idx}">🗑</button></span>`;
        list.appendChild(li);
    });
    list.querySelectorAll('.edit-question').forEach(btn => {
        btn.addEventListener('click', () => {
            const idx = parseInt(btn.dataset.idx);
            const current = pluginCopy.triggers[idx];
            showTextInputModal('Edit Question', current, (newVal) => {
                pluginCopy.triggers[idx] = newVal;
                renderQuestionsList();
            });
        });
    });
    list.querySelectorAll('.delete-question').forEach(btn => {
        btn.addEventListener('click', () => {
            const idx = parseInt(btn.dataset.idx);
            showConfirmModal('Delete this question?', () => {
                pluginCopy.triggers.splice(idx, 1);
                renderQuestionsList();
            });
        });
    });
}
document.getElementById('addQuestionBtn').onclick = () => {
    showTextInputModal('Add Question', '', (newVal) => {
        if (!pluginCopy.triggers) pluginCopy.triggers = [];
        pluginCopy.triggers.push(newVal);
        renderQuestionsList();
    });
};

// ------------------------------------------------------------------
// Static answers list management (no inline onclick)
// ------------------------------------------------------------------
function renderAnswersList() {
    const list = document.getElementById('answersList');
    list.innerHTML = '';
    const answers = pluginCopy.response?.answers || [];
    answers.forEach((ans, idx) => {
        const li = document.createElement('li');
        li.innerHTML = `<span>${escapeHtml(ans)}</span> <span><button class="edit-answer" data-idx="${idx}">✎</button><button class="delete-answer" data-idx="${idx}">🗑</button></span>`;
        list.appendChild(li);
    });
    list.querySelectorAll('.edit-answer').forEach(btn => {
        btn.addEventListener('click', () => {
            const idx = parseInt(btn.dataset.idx);
            const current = pluginCopy.response.answers[idx];
            showTextInputModal('Edit Answer', current, (newVal) => {
                pluginCopy.response.answers[idx] = newVal;
                renderAnswersList();
            });
        });
    });
    list.querySelectorAll('.delete-answer').forEach(btn => {
        btn.addEventListener('click', () => {
            const idx = parseInt(btn.dataset.idx);
            showConfirmModal('Delete this answer?', () => {
                pluginCopy.response.answers.splice(idx, 1);
                renderAnswersList();
            });
        });
    });
}
document.getElementById('addAnswerBtn').onclick = () => {
    showTextInputModal('Add Answer', '', (newVal) => {
        if (!pluginCopy.response) pluginCopy.response = { type: 'static', answers: [] };
        if (!pluginCopy.response.answers) pluginCopy.response.answers = [];
        pluginCopy.response.answers.push(newVal);
        renderAnswersList();
    });
};

// ------------------------------------------------------------------
// API fields (conditional templates) – no inline onclick
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
                        <button class="move-up" data-idx="${idx}" title="Move Up" ${idx === 0 ? 'disabled' : ''}>↑</button>
                        <button class="move-down" data-idx="${idx}" title="Move Down" ${idx === templates.length-1 ? 'disabled' : ''}>↓</button>
                        <button class="edit-conditional" data-idx="${idx}" title="Edit">✎</button>
                        <button class="delete-conditional" data-idx="${idx}" title="Delete">🗑</button>
                    </div>
                </div>
                <div class="template-preview">${escapeHtml(item.template)}</div>
            </div>
        `;
    });
    html += '</div>';
    container.innerHTML = html;

    container.querySelectorAll('.move-up').forEach(btn => {
        btn.addEventListener('click', (e) => {
            e.stopPropagation();
            const idx = parseInt(btn.dataset.idx);
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
            const idx = parseInt(btn.dataset.idx);
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
            const idx = parseInt(btn.dataset.idx);
            editConditionalTemplate(idx);
        });
    });
    container.querySelectorAll('.delete-conditional').forEach(btn => {
        btn.addEventListener('click', (e) => {
            e.stopPropagation();
            const idx = parseInt(btn.dataset.idx);
            showConfirmModal('Delete this conditional template?', () => {
                pluginCopy.response.conditionalTemplates.splice(idx, 1);
                renderConditionalTemplates();
            });
        });
    });
}

function editConditionalTemplate(idx) {
    const item = pluginCopy.response.conditionalTemplates[idx];
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
// Response type toggle
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
// Mappings management (no inline onclick)
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
                        <button class="edit-mapping" data-table="${escapeHtml(tableName)}" title="Edit">✎</button>
                        <button class="delete-mapping" data-table="${escapeHtml(tableName)}" title="Delete">🗑</button>
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

    container.querySelectorAll('.edit-mapping').forEach(btn => {
        btn.addEventListener('click', (e) => {
            e.stopPropagation();
            const tableName = btn.dataset.table;
            openMappingEditor(tableName);
        });
    });
    container.querySelectorAll('.delete-mapping').forEach(btn => {
        btn.addEventListener('click', (e) => {
            e.stopPropagation();
            const tableName = btn.dataset.table;
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
// Tree editor (fixed – no inline onclick, clean loading)
// ------------------------------------------------------------------
let currentTree = [];
let nodeMap = new Map();
let nodeDetailsCache = new Map();
let nextNodeId = 0;
let selectedNodeId = null;
let treeUnsaved = false;

function openTreeEditor() {
    currentTree = JSON.parse(JSON.stringify(pluginCopy.tree || []));
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

    const addQuestionBtn = document.getElementById('treeAddQuestionBtn');
    const addAnswerBtn = document.getElementById('treeAddAnswerBtn');
    if (addQuestionBtn) addQuestionBtn.disabled = true;
    if (addAnswerBtn) addAnswerBtn.disabled = true;

    const qList = document.getElementById('treeQuestionsList');
    const aList = document.getElementById('treeAnswersList');
    qList.innerHTML = '';
    aList.innerHTML = '';

    const qLoading = showInlineLoading(qList, "Loading questions");
    const aLoading = showInlineLoading(aList, "Loading answers");

    (async () => {
        try {
            const details = await retryOperation(async () => {
                return await apiGet(`/api/plugins/${encodeURIComponent(currentPluginName)}/node/${node.dbId}`);
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
            showInlineListRetry(qList, 'questions', async () => {
                await showNodeQAPanel(nodeId);
            });
            showInlineListRetry(aList, 'answers', async () => {
                await showNodeQAPanel(nodeId);
            });
        }
    })();
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

function editTreeNodeQuestion(qIdx) {
    const node = nodeMap.get(selectedNodeId);
    const fullNode = nodeDetailsCache.get(selectedNodeId) || { questions: node.questions || [], answers: node.answers || [] };
    showTextInputModal('Edit Question', fullNode.questions[qIdx], (newVal) => {
        fullNode.questions[qIdx] = newVal;
        nodeDetailsCache.set(selectedNodeId, fullNode);
        treeUnsaved = true;
        showNodeQAPanel(selectedNodeId);
    });
}

function deleteTreeNodeQuestion(qIdx) {
    showConfirmModal('Delete this question?', () => {
        const fullNode = nodeDetailsCache.get(selectedNodeId) || { questions: [], answers: [] };
        fullNode.questions.splice(qIdx, 1);
        nodeDetailsCache.set(selectedNodeId, fullNode);
        treeUnsaved = true;
        showNodeQAPanel(selectedNodeId);
    });
}

function editTreeNodeAnswer(aIdx) {
    const node = nodeMap.get(selectedNodeId);
    const fullNode = nodeDetailsCache.get(selectedNodeId) || { questions: node.questions || [], answers: node.answers || [] };
    showTextInputModal('Edit Answer', fullNode.answers[aIdx], (newVal) => {
        fullNode.answers[aIdx] = newVal;
        nodeDetailsCache.set(selectedNodeId, fullNode);
        treeUnsaved = true;
        showNodeQAPanel(selectedNodeId);
    });
}

function deleteTreeNodeAnswer(aIdx) {
    showConfirmModal('Delete this answer?', () => {
        const fullNode = nodeDetailsCache.get(selectedNodeId) || { questions: [], answers: [] };
        fullNode.answers.splice(aIdx, 1);
        nodeDetailsCache.set(selectedNodeId, fullNode);
        treeUnsaved = true;
        showNodeQAPanel(selectedNodeId);
    });
}

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
// Event listeners
// ------------------------------------------------------------------
searchInput.addEventListener('input', () => renderPlugins());
sortSelect.addEventListener('change', () => renderPlugins());
newPluginBtn.onclick = () => openPluginModal(null);

// Start
loadPlugins();

// Inject inline-loading styles (if not already present)
if (!document.querySelector('#inline-loading-styles')) {
    const style = document.createElement('style');
    style.id = 'inline-loading-styles';
    style.textContent = `
        .inline-loading {
            display: flex;
            align-items: center;
            gap: 8px;
            padding: 8px;
            background: transparent;
            color: #aaa;
            font-size: 0.85rem;
        }
        .inline-spinner {
            width: 16px;
            height: 16px;
            border: 2px solid #6c63ff;
            border-top-color: transparent;
            border-radius: 50%;
            animation: spin 0.6s linear infinite;
        }
        @keyframes spin { to { transform: rotate(360deg); } }
        .retry-list-item {
            display: flex;
            align-items: center;
            justify-content: center;
            padding: 12px;
            background: #2d2d5a;
            border-radius: 6px;
            color: #ffe0e0;
        }
        .retry-list-btn {
            background: #6c63ff;
            border: none;
            border-radius: 4px;
            padding: 4px 12px;
            color: white;
            cursor: pointer;
            font-size: 0.8rem;
        }
        .retry-list-btn:hover { background: #5a52d5; }
        .retry-list-btn:disabled { opacity: 0.6; cursor: not-allowed; }
        .retry-error {
            display: flex;
            flex-direction: column;
            align-items: center;
            gap: 12px;
            background: #2d2d5a;
            border: 1px solid #ff6b9d;
            border-radius: 8px;
            padding: 20px;
            margin: 20px;
            text-align: center;
            color: #ffe0e0;
        }
        .retry-error .error-icon { font-size: 32px; }
        .retry-error .error-message { font-size: 0.9rem; }
        .retry-error .retry-btn {
            background: #6c63ff;
            color: white;
            border: none;
            padding: 8px 16px;
            border-radius: 6px;
            cursor: pointer;
            font-size: 0.9rem;
        }
        .retry-error .retry-btn:hover { background: #5a52d5; }
        .retry-error .retry-btn:disabled { opacity: 0.6; cursor: not-allowed; }
    `;
    document.head.appendChild(style);
}
// ------------------------------------------------------------------
// Global state
// ------------------------------------------------------------------
let plugins = [];
let currentPluginName = null;
let pluginCopy = null;
let currentBlocklyWorkspace = null;

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
// Modal helpers
// ------------------------------------------------------------------
function showModal(id) {
    document.getElementById(id).classList.add('visible');
}
function hideModal(id) {
    document.getElementById(id).classList.remove('visible');
}

function showAlertModal(title, message) {
    const modal = document.getElementById('simpleModal');
    const content = document.getElementById('simpleModalContent');
    content.innerHTML = `
        <h2>${escapeHtml(title)}</h2>
        <p style="margin: 20px 0;">${escapeHtml(message)}</p>
        <div class="modal-actions">
            <button class="save" id="alertOkBtn">OK</button>
        </div>
    `;
    showModal('simpleModal');
    document.getElementById('alertOkBtn').onclick = () => hideModal('simpleModal');
}

function showConfirmModal(message, onConfirm) {
    const modal = document.getElementById('simpleModal');
    const content = document.getElementById('simpleModalContent');
    content.innerHTML = `
        <h2>Confirm</h2>
        <p style="margin: 20px 0;">${escapeHtml(message)}</p>
        <div class="modal-actions">
            <button class="cancel" id="confirmCancel">Cancel</button>
            <button class="save" id="confirmOk">OK</button>
        </div>
    `;
    showModal('simpleModal');
    document.getElementById('confirmCancel').onclick = () => hideModal('simpleModal');
    document.getElementById('confirmOk').onclick = () => {
        hideModal('simpleModal');
        onConfirm();
    };
}

function showTextInputModal(title, initialValue, onSave) {
    const modal = document.getElementById('simpleModal');
    const content = document.getElementById('simpleModalContent');
    content.innerHTML = `
        <h2>${escapeHtml(title)}</h2>
        <input type="text" id="modalInput" value="${escapeHtml(initialValue)}" style="width:100%; margin:16px 0;">
        <div class="modal-actions">
            <button class="cancel" id="modalCancel">Cancel</button>
            <button class="save" id="modalSave">Save</button>
        </div>
    `;
    showModal('simpleModal');
    const input = document.getElementById('modalInput');
    document.getElementById('modalSave').onclick = () => {
        const val = input.value.trim();
        if (val) onSave(val);
        hideModal('simpleModal');
    };
    document.getElementById('modalCancel').onclick = () => hideModal('simpleModal');
    input.focus();
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
    document.getElementById('pluginModalTitle').innerText = isNew ? 'Create New Plugin' : 'Edit Plugin';

    if (isNew) {
        pluginCopy = {
            name: '',
            version: '1.0.0',
            description: '',
            triggers: [],
            script_json: '{}'
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
    renderTriggersList(pluginCopy.triggers || []);
    initBlockly(pluginCopy.script_json || '{}');
    showModal('pluginModal');
}

function renderTriggersList(triggers) {
    const container = document.getElementById('triggersList');
    container.innerHTML = '';
    if (!triggers || triggers.length === 0) {
        const li = document.createElement('li');
        li.style.justifyContent = 'center';
        li.style.color = '#888';
        li.textContent = 'No triggers. Add one below.';
        container.appendChild(li);
    } else {
        triggers.forEach((trigger, idx) => {
            const li = document.createElement('li');
            li.innerHTML = `<span>${escapeHtml(trigger)}</span> <span><button class="edit-trigger" data-idx="${idx}">✎</button><button class="delete-trigger" data-idx="${idx}">🗑</button></span>`;
            container.appendChild(li);
        });
    }
    // Attach events after render
    document.querySelectorAll('.edit-trigger').forEach(btn => {
        btn.addEventListener('click', () => {
            const idx = parseInt(btn.dataset.idx);
            showTextInputModal('Edit Trigger', triggers[idx], (newVal) => {
                triggers[idx] = newVal;
                renderTriggersList(triggers);
            });
        });
    });
    document.querySelectorAll('.delete-trigger').forEach(btn => {
        btn.addEventListener('click', () => {
            const idx = parseInt(btn.dataset.idx);
            showConfirmModal('Delete this trigger?', () => {
                triggers.splice(idx, 1);
                renderTriggersList(triggers);
            });
        });
    });
}

document.getElementById('addTriggerBtn').onclick = () => {
    let triggers = pluginCopy.triggers || [];
    showTextInputModal('Add Trigger', '', (newVal) => {
        triggers.push(newVal);
        pluginCopy.triggers = triggers;
        renderTriggersList(triggers);
    });
};

// ------------------------------------------------------------------
// Blockly integration with dark theme
// ------------------------------------------------------------------
function initBlockly(scriptJson) {
    if (currentBlocklyWorkspace) {
        currentBlocklyWorkspace.dispose();
        currentBlocklyWorkspace = null;
    }
    setTimeout(() => {
        // Define custom dark theme
        const darkTheme = Blockly.Theme.defineTheme('darkTheme', {
            'base': Blockly.Themes.Classic,
            'componentStyles': {
                'workspaceBackgroundColour': '#1a1a2e',
                'toolboxBackgroundColour': '#252547',
                'toolboxForegroundColour': '#fff',
                'flyoutBackgroundColour': '#2d2d5a',
                'flyoutForegroundColour': '#fff',
                'flyoutOpacity': 0.9,
                'scrollbarColour': '#4a4a7a',
                'scrollbarOpacity': 0.6,
                'cursorColour': '#6c63ff',
            },
            'blockStyles': {
                'logic_blocks': {
                    'colourPrimary': '#ffaa66',
                    'colourSecondary': '#ffaa66',
                    'colourTertiary': '#cc8844',
                },
                'loop_blocks': {
                    'colourPrimary': '#ffaa66',
                    'colourSecondary': '#ffaa66',
                    'colourTertiary': '#cc8844',
                },
                'math_blocks': {
                    'colourPrimary': '#6c63ff',
                    'colourSecondary': '#6c63ff',
                    'colourTertiary': '#4a3fcc',
                },
                'text_blocks': {
                    'colourPrimary': '#00ff88',
                    'colourSecondary': '#00ff88',
                    'colourTertiary': '#00aa55',
                },
                'list_blocks': {
                    'colourPrimary': '#ff6b9d',
                    'colourSecondary': '#ff6b9d',
                    'colourTertiary': '#cc5577',
                },
                'colour_blocks': {
                    'colourPrimary': '#ffaa66',
                    'colourSecondary': '#ffaa66',
                    'colourTertiary': '#cc8844',
                },
                'variable_blocks': {
                    'colourPrimary': '#a78bfa',
                    'colourSecondary': '#a78bfa',
                    'colourTertiary': '#8a5cf0',
                },
                'procedure_blocks': {
                    'colourPrimary': '#a78bfa',
                    'colourSecondary': '#a78bfa',
                    'colourTertiary': '#8a5cf0',
                },
            },
            'categoryStyles': {
                'api_category': {
                    'colour': '#6c63ff',
                },
                'logic_category': {
                    'colour': '#ffaa66',
                },
                'response_category': {
                    'colour': '#00ff88',
                },
            },
        });

        currentBlocklyWorkspace = Blockly.inject('blocklyDiv', {
            toolbox: `<xml xmlns="https://developers.google.com/blockly/xml" id="toolbox" style="display: none">
                <category name="API" colour="#6c63ff">
                    <block type="call_api"></block>
                </category>
                <category name="Logic" colour="#ffaa66">
                    <block type="controls_if"></block>
                </category>
                <category name="Response" colour="#00ff88">
                    <block type="respond"></block>
                </category>
            </xml>`,
            grid: { spacing: 20, length: 3, colour: '#4a4a7a' },
            zoom: { controls: true, wheel: true },
            theme: darkTheme,
        });
        defineCustomBlocks();
        if (scriptJson && scriptJson !== '{}') {
            try {
                const xml = Blockly.Xml.textToDom(scriptJson);
                Blockly.Xml.domToWorkspace(xml, currentBlocklyWorkspace);
            } catch(e) { console.error('Failed to load script', e); }
        }
    }, 100);
}

function defineCustomBlocks() {
    // Block: call_api
    Blockly.Blocks['call_api'] = {
        init: function() {
            this.appendValueInput('URL')
                .setCheck('String')
                .appendField('call API');
            this.appendDummyInput()
                .appendField('method')
                .appendField(new Blockly.FieldDropdown([['GET','GET'],['POST','POST'],['PUT','PUT'],['DELETE','DELETE']]), 'METHOD');
            this.appendValueInput('HEADERS')
                .setCheck('Object')
                .appendField('headers (JSON)');
            this.appendValueInput('BODY')
                .setCheck('String')
                .appendField('body');
            this.appendValueInput('STORE')
                .setCheck('String')
                .appendField('store result in variable');
            this.setPreviousStatement(true, null);
            this.setNextStatement(true, null);
            this.setColour(108, 99, 255);
        }
    };
    Blockly.JavaScript['call_api'] = function(block) {
        var url = Blockly.JavaScript.valueToCode(block, 'URL', Blockly.JavaScript.ORDER_ATOMIC);
        var method = block.getFieldValue('METHOD');
        var headers = Blockly.JavaScript.valueToCode(block, 'HEADERS', Blockly.JavaScript.ORDER_ATOMIC);
        var body = Blockly.JavaScript.valueToCode(block, 'BODY', Blockly.JavaScript.ORDER_ATOMIC);
        var store = Blockly.JavaScript.valueToCode(block, 'STORE', Blockly.JavaScript.ORDER_ATOMIC);
        return `call_api(${url}, '${method}', ${headers}, ${body}, ${store});\n`;
    };

    // Block: respond
    Blockly.Blocks['respond'] = {
        init: function() {
            this.appendValueInput('TEXT')
                .setCheck('String')
                .appendField('respond with');
            this.setPreviousStatement(true, null);
            this.setNextStatement(false);
            this.setColour(0, 255, 136);
        }
    };
    Blockly.JavaScript['respond'] = function(block) {
        var text = Blockly.JavaScript.valueToCode(block, 'TEXT', Blockly.JavaScript.ORDER_ATOMIC);
        return `respond(${text});\n`;
    };
}

// ------------------------------------------------------------------
// Save plugin
// ------------------------------------------------------------------
document.getElementById('pluginSaveBtn').onclick = async () => {
    const name = document.getElementById('pluginName').value.trim();
    const version = document.getElementById('pluginVersion').value.trim();
    const description = document.getElementById('pluginDescription').value.trim();
    if (!name) {
        showAlertModal('Validation Error', 'Plugin name is required');
        return;
    }
    const triggers = pluginCopy.triggers || [];
    if (triggers.length === 0) {
        showAlertModal('Validation Error', 'At least one trigger is required');
        return;
    }
    if (!currentBlocklyWorkspace) {
        showAlertModal('Error', 'Blockly workspace not initialized');
        return;
    }
    const xml = Blockly.Xml.workspaceToDom(currentBlocklyWorkspace);
    const scriptJson = Blockly.Xml.domToText(xml);
    const data = {
        name, version, description,
        triggers: triggers,
        script_json: scriptJson
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
    if (currentBlocklyWorkspace) {
        currentBlocklyWorkspace.dispose();
        currentBlocklyWorkspace = null;
    }
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

loadPlugins();
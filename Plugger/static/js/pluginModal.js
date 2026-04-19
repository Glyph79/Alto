import { apiPost, apiPut, apiGet } from './api.js';
import { showModal, hideModal, showAlertModal, showTextInputModal, showConfirmModal, escapeHtml } from './modals.js';
import { loadPlugins } from './pluginGrid.js';
import { openRootScriptEditor } from './scriptEditor.js';
import { openTreeEditor } from './treeEditor.js';

let currentPluginName = null;
let pluginCopy = null;

export async function openPluginModal(name) {
    currentPluginName = name;
    const isNew = name === null;
    document.getElementById('pluginModalTitle').innerText = isNew ? 'Create New Plugin' : 'Edit Plugin';

    if (isNew) {
        pluginCopy = {
            name: '',
            version: '1.0.0',
            description: '',
            triggers: [],
            root_script_json: '{}',
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
    renderTriggersList(pluginCopy.triggers || []);
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
    attachTriggerEvents(triggers);
}

function attachTriggerEvents(triggers) {
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

document.getElementById('editRootScriptBtn').onclick = () => {
    openRootScriptEditor(pluginCopy);
};

document.getElementById('editTreeBtn').onclick = () => {
    openTreeEditor(pluginCopy);
};

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
    const data = {
        name, version, description,
        triggers: triggers,
        root_script_json: pluginCopy.root_script_json || '{}',
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
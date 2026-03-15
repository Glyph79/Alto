// ========== Load Models ==========
async function loadModels() {
    try {
        const models = await window.apiGet('/api/models');
        const select = document.getElementById('modelSelect');
        select.innerHTML = '';
        models.forEach(m => {
            const opt = document.createElement('option');
            opt.value = m.name;
            opt.textContent = `${m.name} (${m.version})`;
            select.appendChild(opt);
        });

        select.addEventListener('change', (e) => {
            switchModel(e.target.value);
        });

        if (models.length > 0) {
            select.value = models[0].name;
            await switchModel(models[0].name);
            document.getElementById('noModelsEmptyState').style.display = 'none';
            window.setControlsEnabled(true);
        } else {
            window.currentModel = null;
            window.groups = [];
            window.sections = [];
            if (typeof renderGroups === 'function') renderGroups();
            document.getElementById('noModelsEmptyState').style.display = 'block';
            document.getElementById('noGroupsEmptyState').style.display = 'none';
            window.setControlsEnabled(false);
        }
    } catch (err) {
        alert('Error loading models: ' + err.message);
    }
}

async function switchModel(modelName) {
    window.currentModel = modelName;
    await window.loadGroupsAndSections();
    await window.loadTopics();   // load topics as well
}

// ========== Model CRUD ==========
document.getElementById('createModelBtn').onclick = () => {
    window.showSimpleModal('Create New Model', [
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
    if (!window.currentModel) return;
    const data = await window.apiGet(`/api/models/${window.currentModel}`);
    window.showSimpleModal('Edit Model', [
        { name: 'name', label: 'Model Name', value: data.name },
        { name: 'description', label: 'Description', value: data.description || '' },
        { name: 'author', label: 'Author', value: data.author || '' },
        { name: 'version', label: 'Version', value: data.version || '1.0.0' }
    ], async (vals, errorDiv) => {
        // Check if name changed
        if (vals.name !== window.currentModel) {
            // Call rename API
            const renameRes = await fetch(`/api/models/${window.currentModel}/rename`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ new_name: vals.name })
            });
            if (!renameRes.ok) {
                const err = await renameRes.json();
                errorDiv.textContent = err.error || 'Rename failed';
                errorDiv.style.display = 'block';
                return;
            }
            // After rename, update metadata using new name
            const updateRes = await fetch(`/api/models/${vals.name}`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    description: vals.description,
                    author: vals.author,
                    version: vals.version
                })
            });
            if (!updateRes.ok) {
                const err = await updateRes.json();
                errorDiv.textContent = err.error || 'Update failed';
                errorDiv.style.display = 'block';
                return;
            }
        } else {
            // Name unchanged – just update metadata
            const updateRes = await fetch(`/api/models/${window.currentModel}`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    description: vals.description,
                    author: vals.author,
                    version: vals.version
                })
            });
            if (!updateRes.ok) {
                const err = await updateRes.json();
                errorDiv.textContent = err.error || 'Update failed';
                errorDiv.style.display = 'block';
                return;
            }
        }
        // Reload models and switch to the (possibly new) model
        await loadModels();
        const select = document.getElementById('modelSelect');
        if (select.querySelector(`option[value="${vals.name}"]`)) {
            select.value = vals.name;
            await switchModel(vals.name);
        }
    }, 'Save');
};

document.getElementById('deleteModelBtn').onclick = async () => {
    if (!window.currentModel) return;
    window.showConfirmModal(`Delete model '${window.currentModel}'?`, async () => {
        await window.apiDelete(`/api/models/${window.currentModel}`);
        await loadModels();
    });
};

// ========== Import/Export ==========
document.getElementById('importBtn').onclick = () => {
    const input = document.createElement('input');
    input.type = 'file';
    input.accept = '.db';
    input.onchange = async (e) => {
        const file = e.target.files[0];
        const formData = new FormData();
        formData.append('file', file);

        // First attempt: let backend read name from db
        let response = await fetch('/api/models/import-db', {
            method: 'POST',
            body: formData
        });

        let result = await response.json();

        if (response.ok) {
            // Success – model created, reload and switch
            await loadModels();
            const select = document.getElementById('modelSelect');
            if (select.querySelector(`option[value="${result.model.name}"]`)) {
                select.value = result.model.name;
                await switchModel(result.model.name);
            }
            return;
        }

        if (response.status === 409 && result.code === 'CONFLICT') {
            // Name conflict – ask user what to do
            const action = await showImportConflictDialog(result.existing_name, result.db_name);
            if (!action) return; // cancelled

            const newFormData = new FormData();
            newFormData.append('file', file);
            if (action.overwrite) {
                newFormData.append('name', action.name);
                newFormData.append('overwrite', 'true');
            } else {
                newFormData.append('name', action.name);
            }

            response = await fetch('/api/models/import-db', {
                method: 'POST',
                body: newFormData
            });
            if (response.ok) {
                result = await response.json();
                await loadModels();
                const select = document.getElementById('modelSelect');
                if (select.querySelector(`option[value="${result.model.name}"]`)) {
                    select.value = result.model.name;
                    await switchModel(result.model.name);
                }
            } else {
                const err = await response.json();
                alert(`Import failed: ${err.error || 'Unknown error'}`);
            }
        } else {
            alert(`Import failed: ${result.error || 'Unknown error'}`);
        }
    };
    input.click();
};

// Helper to show conflict dialog (returns a promise)
function showImportConflictDialog(existingName, dbName) {
    return new Promise((resolve) => {
        const modal = document.getElementById('simpleModal');
        const content = document.getElementById('simpleModalContent');
        content.innerHTML = `
            <h2>Model Already Exists</h2>
            <p>A model named <strong>${existingName}</strong> already exists.</p>
            <p>The database you're importing contains model <strong>${dbName}</strong>.</p>
            <div style="margin: 20px 0;">
                <label for="newNameInput">Enter a new name (or leave blank to overwrite):</label>
                <input type="text" id="newNameInput" placeholder="New model name" style="width:100%; margin-top:8px;">
            </div>
            <div class="modal-actions">
                <button class="save" id="confirmOverwriteBtn">Overwrite</button>
                <button class="save" id="confirmRenameBtn">Rename</button>
                <button class="cancel" id="cancelImportBtn">Cancel</button>
            </div>
        `;
        window.pushModal('simpleModal');

        document.getElementById('cancelImportBtn').onclick = () => {
            window.popModal();
            resolve(null);
        };
        document.getElementById('confirmOverwriteBtn').onclick = () => {
            window.popModal();
            resolve({ overwrite: true, name: existingName });
        };
        document.getElementById('confirmRenameBtn').onclick = () => {
            const newName = document.getElementById('newNameInput').value.trim();
            if (!newName) {
                alert('Please enter a new name.');
                return;
            }
            window.popModal();
            resolve({ overwrite: false, name: newName });
        };
    });
}

document.getElementById('exportBtn').onclick = () => {
    if (!window.currentModel) return;
    window.open(`/api/models/${window.currentModel}/export-db`);
};

// Initialize
loadModels();
import { state } from '../core/state.js';
import { api } from '../core/api.js';
import { modal } from '../ui/modal.js';
import { dom } from '../core/dom.js';
import events from '../core/events.js';
import { error } from '../ui/error.js';

export class ModelManager {
    constructor() {
        this.models = [];
        this.selectEl = document.getElementById('modelSelect');
        this.initEventListeners();
    }

    async load() {
        try {
            this.models = await api.get('/api/models');
            this.renderSelect();
            
            if (this.models.length > 0) {
                const current = state.get('currentModel');
                let matchedModel = null;
                if (current) {
                    matchedModel = this.models.find(m => m.name === current);
                    if (!matchedModel) {
                        matchedModel = this.models.find(m => m.name.toLowerCase() === current.toLowerCase());
                    }
                }
                if (matchedModel) {
                    await state.setCurrentModel(matchedModel.name);
                } else {
                    await state.setCurrentModel(this.models[0].name);
                }
            } else {
                await state.setCurrentModel(null);
                this.showEmptyState();
            }
            this.updateUI();
            this.selectEl.disabled = this.models.length === 0;
        } catch (err) {
            error.alert(err.message);
            this.selectEl.disabled = true;
        }
    }

    renderSelect() {
        this.selectEl.innerHTML = '';
        this.models.forEach(m => {
            const opt = dom.createElement('option', { value: m.name }, [`${m.name} (${m.version})`]);
            this.selectEl.appendChild(opt);
        });
        const current = state.get('currentModel');
        if (current && this.models.some(m => m.name === current)) {
            this.selectEl.value = current;
        } else if (this.models.length > 0) {
            this.selectEl.value = this.models[0].name;
        }
    }

    async switchModel(modelName) {
        if (!modelName) return;
        const exact = this.models.find(m => m.name === modelName);
        if (!exact) {
            const caseInsensitive = this.models.find(m => m.name.toLowerCase() === modelName.toLowerCase());
            if (caseInsensitive) {
                await state.setCurrentModel(caseInsensitive.name);
                this.selectEl.value = caseInsensitive.name;
            } else {
                error.alert(`Model "${modelName}" does not exist.`);
                return;
            }
        } else {
            await state.setCurrentModel(exact.name);
            this.selectEl.value = exact.name;
        }
        this.updateUI();
    }

    updateUI() {
        const hasModel = !!state.get('currentModel');
        const btns = ['editModelBtn', 'deleteModelBtn', 'exportBtn'];
        btns.forEach(id => {
            const btn = document.getElementById(id);
            if (btn) btn.disabled = !hasModel;
        });
        const emptyStateDiv = document.getElementById('noModelsEmptyState');
        if (emptyStateDiv) emptyStateDiv.style.display = hasModel ? 'none' : 'flex';
        events.emit('models:updated', { models: this.models, current: state.get('currentModel') });
    }

    showEmptyState() {
        const emptyStateDiv = document.getElementById('noModelsEmptyState');
        if (emptyStateDiv && this.models.length === 0) {
            emptyStateDiv.style.display = 'flex';
            const btn = document.getElementById('createFirstModelBtn');
            if (btn) btn.onclick = () => this.createModel();
        }
        const containers = ['groupsGridContainer', 'sectionsGridContainer', 'topicsGridContainer', 'variantsGridContainer', 'fallbacksGridContainer'];
        containers.forEach(id => {
            const container = document.getElementById(id);
            if (container) container.innerHTML = '';
        });
    }

    async createModel() {
        const vals = await this.showCreateModal();
        if (!vals) return;
        try {
            await api.post('/api/models', vals);
            await this.load();
        } catch (err) {
            error.alert(err.message);
        }
    }

    showCreateModal() {
        return new Promise((resolve) => {
            let modalId = null;
            const content = dom.createElement('div', {}, [
                dom.createElement('input', { id: 'modelName', type: 'text', placeholder: 'Model Name', style: 'width:100%; margin-bottom:12px;' }),
                dom.createElement('input', { id: 'modelDesc', type: 'text', placeholder: 'Description', style: 'width:100%; margin-bottom:12px;' }),
                dom.createElement('input', { id: 'modelAuthor', type: 'text', placeholder: 'Author', style: 'width:100%; margin-bottom:12px;' }),
                dom.createElement('input', { id: 'modelVersion', type: 'text', placeholder: 'Version', value: '1.0.0', style: 'width:100%;' }),
            ]);
            modalId = modal.show({
                title: 'Create New Model',
                content,
                actions: [
                    { label: 'Cancel', variant: 'cancel', onClick: () => { modal.close(modalId); resolve(null); }, close: false },
                    {
                        label: 'Create',
                        variant: 'save',
                        close: false,
                        onClick: () => {
                            const modalEl = document.getElementById(modalId);
                            if (!modalEl) return;
                            const nameInput = modalEl.querySelector('#modelName');
                            const descInput = modalEl.querySelector('#modelDesc');
                            const authorInput = modalEl.querySelector('#modelAuthor');
                            const versionInput = modalEl.querySelector('#modelVersion');
                            const name = nameInput ? nameInput.value.trim() : '';
                            if (!name) {
                                error.alert('Model name required');
                                return;
                            }
                            resolve({
                                name,
                                description: descInput ? descInput.value : '',
                                author: authorInput ? authorInput.value : '',
                                version: versionInput ? versionInput.value : '1.0.0',
                            });
                            modal.close(modalId);
                        }
                    },
                ],
                size: 'medium',
                closable: false,
            });
        });
    }

    async editModel() {
        const current = state.get('currentModel');
        if (!current) return;
        const model = this.models.find(m => m.name === current);
        if (!model) return;
        const vals = await this.showEditModal(model);
        if (!vals) return;
        try {
            if (vals.name !== current) {
                await api.post(`/api/models/${current}/rename`, { new_name: vals.name });
            }
            await api.put(`/api/models/${vals.name}`, {
                description: vals.description,
                author: vals.author,
                version: vals.version,
            });
            await this.load();
            await state.setCurrentModel(vals.name);
        } catch (err) {
            error.alert(err.message);
        }
    }

    showEditModal(model) {
        return new Promise((resolve) => {
            let modalId = null;
            const content = dom.createElement('div', {}, [
                dom.createElement('input', { id: 'modelName', type: 'text', placeholder: 'Model Name', value: model.name, style: 'width:100%; margin-bottom:12px;' }),
                dom.createElement('input', { id: 'modelDesc', type: 'text', placeholder: 'Description', value: model.description || '', style: 'width:100%; margin-bottom:12px;' }),
                dom.createElement('input', { id: 'modelAuthor', type: 'text', placeholder: 'Author', value: model.author || '', style: 'width:100%; margin-bottom:12px;' }),
                dom.createElement('input', { id: 'modelVersion', type: 'text', placeholder: 'Version', value: model.version || '1.0.0', style: 'width:100%;' }),
            ]);
            modalId = modal.show({
                title: 'Edit Model',
                content,
                actions: [
                    { label: 'Cancel', variant: 'cancel', onClick: () => { modal.close(modalId); resolve(null); }, close: false },
                    {
                        label: 'Save',
                        variant: 'save',
                        close: false,
                        onClick: () => {
                            const modalEl = document.getElementById(modalId);
                            if (!modalEl) return;
                            const nameInput = modalEl.querySelector('#modelName');
                            const descInput = modalEl.querySelector('#modelDesc');
                            const authorInput = modalEl.querySelector('#modelAuthor');
                            const versionInput = modalEl.querySelector('#modelVersion');
                            const name = nameInput ? nameInput.value.trim() : '';
                            if (!name) {
                                error.alert('Model name required');
                                return;
                            }
                            resolve({
                                name,
                                description: descInput ? descInput.value : '',
                                author: authorInput ? authorInput.value : '',
                                version: versionInput ? versionInput.value : '1.0.0',
                            });
                            modal.close(modalId);
                        }
                    },
                ],
                size: 'medium',
                closable: false,
            });
        });
    }

    async deleteModel() {
        const current = state.get('currentModel');
        if (!current) return;
        const confirmed = await modal.confirm(`Delete model "${current}"?`);
        if (!confirmed) return;
        try {
            await api.delete(`/api/models/${current}`);
            await this.load();
        } catch (err) {
            error.alert(err.message);
        }
    }

    exportModel() {
        const current = state.get('currentModel');
        if (current) window.open(`/api/models/${current}/export`);
    }

    async importModel() {
        const input = dom.createElement('input', { type: 'file', accept: '.db,.rbm' });
        input.onchange = async (e) => {
            const file = e.target.files[0];
            const isLegacy = file.name.toLowerCase().endsWith('.db');
            const formData = new FormData();
            formData.append('file', file);
            
            if (isLegacy) {
                const name = await modal.prompt('New model name', '', { placeholder: 'Model name' });
                if (!name) return;
                formData.append('name', name);
                try {
                    const response = await fetch('/api/convert/legacy', { method: 'POST', body: formData });
                    const result = await response.json();
                    if (response.ok) {
                        await this.load();
                        await state.setCurrentModel(result.model_name);
                    } else {
                        error.alert(result.error || 'Conversion failed');
                    }
                } catch (err) {
                    error.alert(err.message);
                }
            } else {
                try {
                    const response = await fetch('/api/models/import', { method: 'POST', body: formData });
                    const result = await response.json();
                    if (response.ok) {
                        await this.load();
                        await state.setCurrentModel(result.model.name);
                    } else if (response.status === 409 && result.code === 'CONFLICT') {
                        const action = await this.showConflictDialog(result.existing_name, result.db_name);
                        if (!action) return;
                        const newFormData = new FormData();
                        newFormData.append('file', file);
                        newFormData.append('name', action.name);
                        if (action.overwrite) newFormData.append('overwrite', 'true');
                        const retryResponse = await fetch('/api/models/import', { method: 'POST', body: newFormData });
                        const retryResult = await retryResponse.json();
                        if (retryResponse.ok) {
                            await this.load();
                            await state.setCurrentModel(retryResult.model.name);
                        } else {
                            throw new Error(retryResult.error || 'Import failed');
                        }
                    } else {
                        throw new Error(result.error || 'Import failed');
                    }
                } catch (err) {
                    error.alert(err.message);
                }
            }
        };
        input.click();
    }

    showConflictDialog(existingName, dbName) {
        return new Promise((resolve) => {
            let modalId = null;
            const content = dom.createElement('div', {}, [
                dom.createElement('p', {}, [`A model named "${existingName}" already exists.`]),
                dom.createElement('p', {}, [`The database you're importing contains model "${dbName}".`]),
                dom.createElement('input', { id: 'newNameInput', type: 'text', placeholder: 'New model name', style: 'width:100%; margin:12px 0;' }),
            ]);
            modalId = modal.show({
                title: 'Model Already Exists',
                content,
                actions: [
                    { label: 'Cancel', variant: 'cancel', onClick: () => { modal.close(modalId); resolve(null); }, close: false },
                    { label: 'Overwrite', variant: 'save', onClick: () => { modal.close(modalId); resolve({ overwrite: true, name: existingName }); }, close: false },
                    { label: 'Rename', variant: 'save', onClick: () => {
                        const modalEl = document.getElementById(modalId);
                        if (!modalEl) return;
                        const newName = modalEl.querySelector('#newNameInput').value.trim();
                        if (newName) {
                            modal.close(modalId);
                            resolve({ overwrite: false, name: newName });
                        } else {
                            error.alert('Please enter a name');
                        }
                    }, close: false },
                ],
                size: 'medium',
                closable: false,
            });
        });
    }

    initEventListeners() {
        this.selectEl.addEventListener('change', (e) => this.switchModel(e.target.value));
        document.getElementById('createModelBtn')?.addEventListener('click', () => this.createModel());
        document.getElementById('editModelBtn')?.addEventListener('click', () => this.editModel());
        document.getElementById('deleteModelBtn')?.addEventListener('click', () => this.deleteModel());
        document.getElementById('exportBtn')?.addEventListener('click', () => this.exportModel());
        document.getElementById('importBtn')?.addEventListener('click', () => this.importModel());
    }
}
// components/ListEditor.js - Generic list editor for strings
import { dom } from '../lib/core/dom.js';
import { modal } from '../lib/ui/modal.js';
import { error } from '../lib/ui/error.js';

export class ListEditor {
    constructor(config) {
        this.container = config.container;
        this.items = config.items || [];
        this.placeholder = config.placeholder || 'Add item';
        this.onAdd = config.onAdd;
        this.onEdit = config.onEdit;
        this.onDelete = config.onDelete;
        this.validate = config.validate || (item => item.trim() ? null : 'Item cannot be empty');
        this.addButtonText = config.addButtonText || '+ Add';
        this.emptyText = config.emptyText || 'No items';
        this.multiline = config.multiline === true;

        this.render();
    }

    render() {
        this.container.innerHTML = '';
        const list = dom.createElement('ul', { class: 'qa-list' });
        if (this.items.length === 0) {
            const li = dom.createElement('li', { style: 'justify-content:center; color:#888;' }, [this.emptyText]);
            list.appendChild(li);
        } else {
            this.items.forEach((item, idx) => {
                const li = dom.createElement('li', {}, [
                    dom.createElement('span', { style: 'white-space: pre-wrap;' }, [dom.escapeHtml(item)]),
                    dom.createElement('span', {}, [
                        dom.createElement('button', { class: 'edit-item', 'data-idx': idx }, ['✎']),
                        dom.createElement('button', { class: 'delete-item', 'data-idx': idx }, ['🗑']),
                    ]),
                ]);
                list.appendChild(li);
            });
        }
        const addBtn = dom.createElement('button', { class: 'add-btn' }, [this.addButtonText]);
        this.container.appendChild(list);
        this.container.appendChild(addBtn);
        
        // Attach events after DOM is updated
        this.attachEvents();
    }

    attachEvents() {
        // Edit buttons
        this.container.querySelectorAll('.edit-item').forEach(btn => {
            btn.removeEventListener('click', this._editHandler);
            this._editHandler = (e) => {
                const idx = parseInt(btn.dataset.idx, 10);
                this.editItem(idx);
            };
            btn.addEventListener('click', this._editHandler);
        });
        
        // Delete buttons
        this.container.querySelectorAll('.delete-item').forEach(btn => {
            btn.removeEventListener('click', this._deleteHandler);
            this._deleteHandler = (e) => {
                const idx = parseInt(btn.dataset.idx, 10);
                this.deleteItem(idx);
            };
            btn.addEventListener('click', this._deleteHandler);
        });
        
        // Add button
        const addBtn = this.container.querySelector('.add-btn');
        if (addBtn) {
            addBtn.removeEventListener('click', this._addHandler);
            this._addHandler = () => this.addItem();
            addBtn.addEventListener('click', this._addHandler);
        }
    }

    async addItem() {
        const value = await this.promptForValue('Add Item', '', this.validate);
        if (value === null) return;
        if (this.onAdd) {
            const result = this.onAdd(value);
            if (result && result.then) await result;
        } else {
            this.items.push(value);
        }
        this.render();
    }

    async editItem(idx) {
        const oldValue = this.items[idx];
        const newValue = await this.promptForValue('Edit Item', oldValue, this.validate);
        if (newValue === null || newValue === oldValue) return;
        if (this.onEdit) {
            const result = this.onEdit(idx, oldValue, newValue);
            if (result && result.then) await result;
        } else {
            this.items[idx] = newValue;
        }
        this.render();
    }

    promptForValue(title, initialValue, validateFn) {
        return new Promise((resolve) => {
            let modalId = null;
            const isMultiline = this.multiline;

            const content = dom.createElement('div', {});
            let input;
            if (isMultiline) {
                input = dom.createElement('textarea', {
                    id: 'multilineInput',
                    rows: 4,
                    style: 'width:100%; padding:8px; font-family:monospace; resize:none; overflow-y:auto;'
                });
                input.value = initialValue;
                const autoExpand = () => {
                    input.style.height = 'auto';
                    const lineHeight = parseInt(window.getComputedStyle(input).lineHeight, 10);
                    const maxHeight = lineHeight * 8;
                    const newHeight = Math.min(input.scrollHeight, maxHeight);
                    input.style.height = newHeight + 'px';
                };
                input.addEventListener('input', autoExpand);
                setTimeout(autoExpand, 0);
            } else {
                input = dom.createElement('input', {
                    id: 'textInput',
                    type: 'text',
                    style: 'width:100%; padding:8px;'
                });
                input.value = initialValue;
            }
            content.appendChild(input);

            let okButton = null;

            const actions = [
                { label: 'Cancel', variant: 'cancel', onClick: () => resolve(null), close: true },
                {
                    label: 'OK',
                    variant: 'save',
                    close: false,
                    onClick: async (e) => {
                        if (okButton) okButton.disabled = true;
                        const val = isMultiline ? input.value : input.value.trim();
                        if (validateFn) {
                            const err = validateFn(val);
                            if (err) {
                                await error.alert(err);
                                if (okButton) okButton.disabled = false;
                                input.focus();
                                return;
                            }
                        }
                        resolve(val);
                        modal.close(modalId);
                    }
                }
            ];

            modalId = modal.show({
                title: title,
                content: content,
                actions: actions,
                size: isMultiline ? 'medium' : 'small',
                closable: false,
            });

            setTimeout(() => {
                const modalEl = document.getElementById(modalId);
                if (modalEl) {
                    okButton = modalEl.querySelector('.modal-actions .save');
                }
            }, 10);

            input.focus();
            if (isMultiline) {
                input.addEventListener('keydown', (e) => {
                    if (e.key === 'Enter' && !e.shiftKey) {
                        e.preventDefault();
                        const btn = document.querySelector(`#${modalId} .modal-actions .save`);
                        if (btn && !btn.disabled) btn.click();
                    }
                });
            } else {
                input.addEventListener('keypress', (e) => {
                    if (e.key === 'Enter') {
                        e.preventDefault();
                        const btn = document.querySelector(`#${modalId} .modal-actions .save`);
                        if (btn && !btn.disabled) btn.click();
                    }
                });
            }
        });
    }

    async deleteItem(idx) {
        const confirmed = await modal.confirm('Delete this item?');
        if (!confirmed) return;
        if (this.onDelete) {
            const result = this.onDelete(idx, this.items[idx]);
            if (result && result.then) await result;
        } else {
            this.items.splice(idx, 1);
        }
        this.render();
    }

    setItems(items) {
        this.items = items;
        this.render();
    }

    getItems() {
        return this.items;
    }

    destroy() {
        this.container.innerHTML = '';
    }
}
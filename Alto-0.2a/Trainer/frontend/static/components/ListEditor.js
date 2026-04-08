// components/ListEditor.js - Generic list editor for strings
import { dom } from '../lib/core/dom.js';
import { modal } from '../lib/ui/modal.js';

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

        this.render();
        this.attachEvents();
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
                    dom.createElement('span', {}, [dom.escapeHtml(item)]),
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
    }

    attachEvents() {
        this.container.querySelectorAll('.edit-item').forEach(btn => {
            btn.addEventListener('click', (e) => {
                const idx = parseInt(btn.dataset.idx, 10);
                this.editItem(idx);
            });
        });
        this.container.querySelectorAll('.delete-item').forEach(btn => {
            btn.addEventListener('click', (e) => {
                const idx = parseInt(btn.dataset.idx, 10);
                this.deleteItem(idx);
            });
        });
        const addBtn = this.container.querySelector('.add-btn');
        if (addBtn) addBtn.addEventListener('click', () => this.addItem());
    }

    async addItem() {
        const value = await modal.prompt('Add Item', '', { placeholder: this.placeholder });
        if (value === null) return;
        const error = this.validate(value);
        if (error) {
            modal.show({ title: 'Error', content: error, actions: [{ label: 'OK', variant: 'cancel' }], size: 'small' });
            return;
        }
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
        const newValue = await modal.prompt('Edit Item', oldValue, { placeholder: this.placeholder });
        if (newValue === null || newValue === oldValue) return;
        const error = this.validate(newValue);
        if (error) {
            modal.show({ title: 'Error', content: error, actions: [{ label: 'OK', variant: 'cancel' }], size: 'small' });
            return;
        }
        if (this.onEdit) {
            const result = this.onEdit(idx, oldValue, newValue);
            if (result && result.then) await result;
        } else {
            this.items[idx] = newValue;
        }
        this.render();
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
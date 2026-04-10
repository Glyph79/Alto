// lib/ui/modal.js - Modal stack manager
import { dom } from '../core/dom.js';

let modalStack = [];
let modalCounter = 0;
const modalContainer = document.getElementById('modalContainer') || (() => {
    const div = document.createElement('div');
    div.id = 'modalContainer';
    document.body.appendChild(div);
    return div;
})();

function createModal(id, title, content, actions, size, closable, modalClass) {
    const modalDiv = dom.createElement('div', { id, class: `modal ${size ? `modal-${size}` : ''} ${modalClass || ''}` });
    const contentDiv = dom.createElement('div', { class: 'modal-content' });
    contentDiv.appendChild(dom.createElement('h2', {}, [title]));
    if (typeof content === 'string') contentDiv.appendChild(dom.createElement('div', { class: 'modal-body' }, [content]));
    else contentDiv.appendChild(content);

    const actionsDiv = dom.createElement('div', { class: 'modal-actions' });
    actions.forEach(action => {
        const onClick = action.onClick || (() => {});
        const btn = dom.createElement('button', { class: action.variant || 'secondary' }, [action.label]);
        btn.addEventListener('click', (e) => {
            onClick(e);
            if (action.close !== false) modal.close(id);
        });
        actionsDiv.appendChild(btn);
    });
    contentDiv.appendChild(actionsDiv);
    
    if (closable === true && actions.length === 0) {
        const closeBtn = dom.createElement('button', { class: 'modal-close' }, ['×']);
        closeBtn.addEventListener('click', () => modal.close(id));
        contentDiv.appendChild(closeBtn);
    }
    
    modalDiv.appendChild(contentDiv);
    return modalDiv;
}

function updateBackdrops() {
    const modals = document.querySelectorAll('.modal');
    modals.forEach(modal => modal.classList.remove('modal-backdrop-hidden'));
    if (modalStack.length > 0) {
        for (let i = 0; i < modalStack.length - 1; i++) {
            const lowerModal = document.getElementById(modalStack[i]);
            if (lowerModal) lowerModal.classList.add('modal-backdrop-hidden');
        }
    }
}

export const modal = {
    show({ id, title, content, actions = [], size = 'medium', closable = false, modalClass = '' }) {
        const finalId = id || `modal_${++modalCounter}`;
        if (document.getElementById(finalId)) return finalId;
        const modalEl = createModal(finalId, title, content, actions, size, closable, modalClass);
        modalContainer.appendChild(modalEl);
        modalStack.push(finalId);
        updateBackdrops();
        setTimeout(() => modalEl.classList.add('visible'), 10);
        return finalId;
    },

    close(id) {
        const targetId = id || modalStack[modalStack.length - 1];
        if (!targetId) return;
        const modalEl = document.getElementById(targetId);
        if (!modalEl) return;
        modalEl.classList.remove('visible');
        modalEl.addEventListener('transitionend', () => {
            if (modalEl.parentNode) modalEl.remove();
            const idx = modalStack.indexOf(targetId);
            if (idx !== -1) modalStack.splice(idx, 1);
            updateBackdrops();
        }, { once: true });
    },

    closeAll() {
        [...modalStack].forEach(id => this.close(id));
    },

    confirm(message, options = {}) {
        return new Promise((resolve) => {
            const actions = [
                { label: options.cancelLabel || 'Cancel', variant: 'cancel', onClick: () => resolve(false), close: true },
                { label: options.confirmLabel || 'OK', variant: 'save', onClick: () => resolve(true), close: true },
            ];
            this.show({
                title: options.title || 'Confirm',
                content: message,
                actions,
                size: 'small',
                closable: false,
            });
        });
    },

    prompt(message, defaultValue = '', options = {}) {
        return new Promise((resolve) => {
            const input = dom.createElement('input', { type: 'text', value: defaultValue, placeholder: options.placeholder || '' });
            const content = dom.createElement('div', {}, [message, input]);
            const actions = [
                { label: 'Cancel', variant: 'cancel', onClick: () => resolve(null), close: true },
                { label: 'OK', variant: 'save', onClick: () => resolve(input.value), close: true },
            ];
            this.show({
                title: options.title || 'Input',
                content,
                actions,
                size: 'small',
                closable: false,
            });
        });
    },
};
// lib/core/dom.js - DOM utilities
export const dom = {
    escapeHtml(str) {
        // Safely handle undefined, null, numbers, etc.
        if (str === undefined || str === null) return '';
        const s = String(str);
        return s.replace(/[&<>]/g, function(m) {
            if (m === '&') return '&amp;';
            if (m === '<') return '&lt;';
            if (m === '>') return '&gt;';
            return m;
        });
    },

    $(selector, context = document) {
        return context.querySelector(selector);
    },

    $$(selector, context = document) {
        return context.querySelectorAll(selector);
    },

    on(element, event, handler, options = false) {
        const el = typeof element === 'string' ? this.$(element) : element;
        if (el) el.addEventListener(event, handler, options);
    },

    delegate(parent, selector, event, handler) {
        const parentEl = typeof parent === 'string' ? this.$(parent) : parent;
        if (!parentEl) return;
        parentEl.addEventListener(event, (e) => {
            const target = e.target.closest(selector);
            if (target) handler(e, target);
        });
    },

    createElement(tag, attrs = {}, children = []) {
        const el = document.createElement(tag);
        Object.entries(attrs).forEach(([k, v]) => el.setAttribute(k, v));
        children.forEach(child => {
            if (typeof child === 'string') el.appendChild(document.createTextNode(child));
            else el.appendChild(child);
        });
        return el;
    },

    show(el) {
        const element = typeof el === 'string' ? this.$(el) : el;
        if (element) element.style.display = '';
    },

    hide(el) {
        const element = typeof el === 'string' ? this.$(el) : el;
        if (element) element.style.display = 'none';
    },

    toggle(el) {
        const element = typeof el === 'string' ? this.$(el) : el;
        if (element) element.style.display = element.style.display === 'none' ? '' : 'none';
    },
};
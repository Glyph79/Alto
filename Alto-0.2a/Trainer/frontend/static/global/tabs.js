// global/tabs.js - Tab switching logic
import { state } from '../lib/core/state.js';   // was '../../lib/core/state.js'
import { dom } from '../lib/core/dom.js';       // was '../../lib/core/dom.js'
import { events } from '../lib/core/events.js'; // was '../../lib/core/events.js'

const tabs = {
    groups: { tabId: 'groupsTab', contentId: 'groupsContent', sidebarId: 'groupsSidebar' },
    sections: { tabId: 'sectionsTab', contentId: 'sectionsContent', sidebarId: 'sectionsSidebar' },
    topics: { tabId: 'topicsTab', contentId: 'topicsContent', sidebarId: 'topicsSidebar' },
    variants: { tabId: 'variantsTab', contentId: 'variantsContent', sidebarId: 'variantsSidebar' },
    fallbacks: { tabId: 'fallbacksTab', contentId: 'fallbacksContent', sidebarId: 'fallbacksSidebar' },
};

let currentTab = 'groups';

function resetFilters(tabName) {
    const manager = window.managers?.[tabName];
    if (manager && typeof manager.resetFilters === 'function') {
        manager.resetFilters();
    } else {
        const searchInput = document.getElementById(`${tabName}Search`);
        if (searchInput) searchInput.value = '';
        const sortSelect = document.getElementById(`${tabName}Sort`);
        if (sortSelect) sortSelect.value = 'name-asc';
        if (searchInput) searchInput.dispatchEvent(new Event('input', { bubbles: true }));
        if (sortSelect) sortSelect.dispatchEvent(new Event('change', { bubbles: true }));
    }
}

function switchTo(tabName) {
    if (currentTab === tabName) return;
    Object.values(tabs).forEach(t => {
        const tabEl = dom.$(`#${t.tabId}`);
        const contentEl = dom.$(`#${t.contentId}`);
        const sidebarEl = dom.$(`#${t.sidebarId}`);
        if (tabEl) tabEl.classList.remove('active');
        if (contentEl) contentEl.style.display = 'none';
        if (sidebarEl) sidebarEl.style.display = 'none';
    });
    const active = tabs[tabName];
    const activeTabEl = dom.$(`#${active.tabId}`);
    const activeContentEl = dom.$(`#${active.contentId}`);
    const activeSidebarEl = dom.$(`#${active.sidebarId}`);
    if (activeTabEl) activeTabEl.classList.add('active');
    if (activeContentEl) activeContentEl.style.display = 'block';
    if (activeSidebarEl) activeSidebarEl.style.display = 'block';
    currentTab = tabName;
    if (state.get('currentModel')) {
        resetFilters(tabName);
        events.emit('tab:changed', tabName);
    }
}

function setTabsEnabled(enabled) {
    Object.values(tabs).forEach(t => {
        const tabEl = dom.$(`#${t.tabId}`);
        if (tabEl) tabEl.disabled = !enabled;
    });
    if (!enabled && currentTab !== 'groups') switchTo('groups');
}

export function initTabs() {
    dom.on('#groupsTab', 'click', () => switchTo('groups'));
    dom.on('#sectionsTab', 'click', () => switchTo('sections'));
    dom.on('#topicsTab', 'click', () => switchTo('topics'));
    dom.on('#variantsTab', 'click', () => switchTo('variants'));
    dom.on('#fallbacksTab', 'click', () => switchTo('fallbacks'));

    events.on('state:currentModel:changed', ({ newValue }) => {
        setTabsEnabled(!!newValue);
        if (newValue) resetFilters(currentTab);
    });

    setTabsEnabled(!!state.get('currentModel'));
    switchTo('groups');
}
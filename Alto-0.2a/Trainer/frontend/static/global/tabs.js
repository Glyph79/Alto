// global/tabs.js - Tab switching logic
import { state } from '../lib/core/state.js';
import { dom } from '../lib/core/dom.js';
import { events } from '../lib/core/events.js';
import { updateSidebar, resetSidebarFilters } from './sidebar.js';

const tabs = {
    groups: { tabId: 'groupsTab', contentId: 'groupsContent' },
    sections: { tabId: 'sectionsTab', contentId: 'sectionsContent' },
    topics: { tabId: 'topicsTab', contentId: 'topicsContent' },
    variants: { tabId: 'variantsTab', contentId: 'variantsContent' },
    fallbacks: { tabId: 'fallbacksTab', contentId: 'fallbacksContent' },
};

let currentTab = null;

function switchTo(tabName) {
    if (currentTab === tabName) return;
    
    // Hide all content
    Object.values(tabs).forEach(t => {
        const tabEl = dom.$(`#${t.tabId}`);
        const contentEl = dom.$(`#${t.contentId}`);
        if (tabEl) tabEl.classList.remove('active');
        if (contentEl) contentEl.style.display = 'none';
    });
    
    // Show selected content
    const active = tabs[tabName];
    const activeTabEl = dom.$(`#${active.tabId}`);
    const activeContentEl = dom.$(`#${active.contentId}`);
    if (activeTabEl) activeTabEl.classList.add('active');
    if (activeContentEl) activeContentEl.style.display = 'block';
    
    currentTab = tabName;
    
    // Update sidebar for this tab
    updateSidebar(tabName);
    
    // Reset filters if model exists
    if (state.get('currentModel')) {
        resetSidebarFilters();
    }
    
    // Reload data for this tab's manager if model exists
    const manager = window.managers?.[tabName];
    if (manager && state.get('currentModel')) {
        manager.load();
    }
    
    events.emit('tab:changed', tabName);
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
        if (newValue) {
            const manager = window.managers?.[currentTab];
            if (manager) manager.load();
            resetSidebarFilters();
        } else {
            // No model: update sidebar to disable controls
            updateSidebar(currentTab);
        }
    });
    
    setTabsEnabled(!!state.get('currentModel'));
    switchTo('groups');
}
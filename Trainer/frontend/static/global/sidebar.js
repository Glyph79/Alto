// global/sidebar.js - Manage sidebar controls
import { state } from '../lib/core/state.js';
import { dom } from '../lib/core/dom.js';
import { events } from '../lib/core/events.js';
import { api } from '../lib/core/api.js';

const sortOptions = {
    groups: [
        { value: 'name-asc', label: 'Name (A-Z)' },
        { value: 'name-desc', label: 'Name (Z-A)' },
        { value: 'questions-desc', label: 'Most questions' },
        { value: 'questions-asc', label: 'Least questions' },
        { value: 'answers-desc', label: 'Most answers' },
        { value: 'answers-asc', label: 'Least answers' }
    ],
    topics: [
        { value: 'name-asc', label: 'Name (A-Z)' },
        { value: 'name-desc', label: 'Name (Z-A)' },
        { value: 'usage-desc', label: 'Most used' },
        { value: 'usage-asc', label: 'Least used' }
    ],
    variants: [
        { value: 'name-asc', label: 'Name (A-Z)' },
        { value: 'name-desc', label: 'Name (Z-A)' },
        { value: 'words-desc', label: 'Most words' },
        { value: 'words-asc', label: 'Least words' }
    ],
    fallbacks: [
        { value: 'name-asc', label: 'Name (A-Z)' },
        { value: 'name-desc', label: 'Name (Z-A)' },
        { value: 'usage-desc', label: 'Most used' },
        { value: 'usage-asc', label: 'Least used' },
        { value: 'answers-desc', label: 'Most answers' },
        { value: 'answers-asc', label: 'Least answers' }
    ]
};

let currentTab = null;
let currentManager = null;

async function ensureTopicsLoaded() {
    const currentModel = state.get('currentModel');
    if (!currentModel) return;
    let topics = state.get('topics');
    if (topics && topics.length > 0) return;
    // Use TopicManager to load if available
    if (window.managers && window.managers.topics) {
        await window.managers.topics.load(true);
    } else {
        // Fallback: fetch directly and extract array
        try {
            const response = await api.get(`/api/models/${currentModel}/topics?limit=100&offset=0`);
            const topicsArray = response.topics || [];
            state.set('topics', topicsArray);
        } catch (err) {
            console.error('Failed to load topics for sidebar:', err);
        }
    }
}

function updateSidebarForTab(tabName) {
    currentTab = tabName;
    currentManager = window.managers?.[tabName];
    
    const sortSelect = document.getElementById('sidebarSort');
    if (sortSelect && sortOptions[tabName]) {
        const currentValue = sortSelect.value;
        sortSelect.innerHTML = '';
        sortOptions[tabName].forEach(opt => {
            const option = dom.createElement('option', { value: opt.value }, [opt.label]);
            sortSelect.appendChild(option);
        });
        if (currentManager && currentManager._sortKey && sortOptions[tabName].some(o => o.value === currentManager._sortKey)) {
            sortSelect.value = currentManager._sortKey;
        } else {
            sortSelect.value = sortOptions[tabName][0].value;
            if (currentManager) currentManager.setSort(sortSelect.value);
        }
    }
    
    const topicContainer = document.getElementById('topicFilterContainer');
    if (topicContainer) {
        topicContainer.style.display = tabName === 'groups' ? 'flex' : 'none';
    }
    
    const addBtn = document.getElementById('sidebarAddBtn');
    if (addBtn) {
        const labels = {
            groups: '+ Add Group',
            topics: '+ Add Topic',
            variants: '+ Add Variant',
            fallbacks: '+ Add Fallback'
        };
        addBtn.textContent = labels[tabName] || '+ Add';
    }
    
    const hasModel = !!state.get('currentModel');
    const searchInput = document.getElementById('sidebarSearch');
    const sortSelectElem = document.getElementById('sidebarSort');
    const topicFilter = document.getElementById('topicFilter');
    const addButton = document.getElementById('sidebarAddBtn');
    
    if (searchInput) searchInput.disabled = !hasModel;
    if (sortSelectElem) sortSelectElem.disabled = !hasModel;
    if (topicFilter) topicFilter.disabled = !hasModel;
    if (addButton) addButton.disabled = !hasModel;
    
    if (tabName === 'groups' && hasModel) {
        // Ensure topics are loaded before populating the filter
        ensureTopicsLoaded().then(() => {
            populateTopicFilter();
        });
    }
    
    if (currentManager && currentManager._searchTerm && searchInput) {
        searchInput.value = currentManager._searchTerm;
    } else if (searchInput) {
        searchInput.value = '';
    }
    
    if (currentManager && currentManager._topicFilter && topicFilter) {
        topicFilter.value = currentManager._topicFilter;
    } else if (topicFilter) {
        topicFilter.value = '';
    }
}

function populateTopicFilter() {
    const topicSelect = document.getElementById('topicFilter');
    if (!topicSelect) return;
    let topics = state.get('topics');
    // Ensure topics is an array
    if (!topics || !Array.isArray(topics)) {
        topics = [];
    }
    let options = '<option value="">All Topics</option>';
    topics.forEach(topic => {
        const topicName = topic.name || topic; // handle both object and string
        options += `<option value="${dom.escapeHtml(topicName)}">${dom.escapeHtml(topicName)}</option>`;
    });
    options += '<option value="__NO_TOPIC__">(No Topic)</option>';
    topicSelect.innerHTML = options;
    if (currentManager && currentManager._topicFilter) {
        topicSelect.value = currentManager._topicFilter;
    }
}

function attachGlobalEvents() {
    const searchInput = document.getElementById('sidebarSearch');
    const sortSelect = document.getElementById('sidebarSort');
    const addBtn = document.getElementById('sidebarAddBtn');
    const topicFilter = document.getElementById('topicFilter');
    
    if (searchInput) {
        searchInput.removeEventListener('input', searchInput._listener);
        searchInput._listener = (e) => {
            if (currentManager && currentManager.setSearchTerm) {
                currentManager.setSearchTerm(e.target.value);
            }
        };
        searchInput.addEventListener('input', searchInput._listener);
    }
    
    if (sortSelect) {
        sortSelect.removeEventListener('change', sortSelect._listener);
        sortSelect._listener = (e) => {
            if (currentManager && currentManager.setSort) {
                currentManager.setSort(e.target.value);
            }
        };
        sortSelect.addEventListener('change', sortSelect._listener);
    }
    
    if (addBtn) {
        addBtn.removeEventListener('click', addBtn._listener);
        addBtn._listener = () => {
            if (currentManager && currentManager.openCreateModal) {
                currentManager.openCreateModal();
            }
        };
        addBtn.addEventListener('click', addBtn._listener);
    }
    
    if (topicFilter) {
        topicFilter.removeEventListener('change', topicFilter._listener);
        topicFilter._listener = (e) => {
            if (currentManager && currentManager.setTopicFilter) {
                currentManager.setTopicFilter(e.target.value);
            }
        };
        topicFilter.addEventListener('change', topicFilter._listener);
    }
}

export function resetSidebarFilters() {
    const searchInput = document.getElementById('sidebarSearch');
    if (searchInput) searchInput.value = '';
    const sortSelect = document.getElementById('sidebarSort');
    if (sortSelect && sortOptions[currentTab] && sortOptions[currentTab][0]) {
        sortSelect.value = sortOptions[currentTab][0].value;
        if (currentManager) currentManager.setSort(sortSelect.value);
    }
    const topicFilter = document.getElementById('topicFilter');
    if (topicFilter) {
        topicFilter.value = '';
        if (currentManager && currentManager.setTopicFilter) currentManager.setTopicFilter('');
    }
    if (currentManager && currentManager.setSearchTerm) currentManager.setSearchTerm('');
}

export function initSidebar() {
    attachGlobalEvents();
    events.on('state:currentModel:changed', () => {
        if (currentTab) {
            updateSidebarForTab(currentTab);
        }
    });
    // Also listen for topics loaded event in case they are loaded later
    events.on('state:topics:changed', () => {
        if (currentTab === 'groups') {
            populateTopicFilter();
        }
    });
}

export function updateSidebar(tabName) {
    updateSidebarForTab(tabName);
}
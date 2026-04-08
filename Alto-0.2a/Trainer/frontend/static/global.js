// global.js - Single entry point for all frontend modules
import { initTabs } from './global/tabs.js';
import { ModelManager } from './lib/managers/ModelManager.js';
import { GroupManager } from './lib/managers/GroupManager.js';
import { SectionManager } from './lib/managers/SectionManager.js';
import { TopicManager } from './lib/managers/TopicManager.js';
import { VariantManager } from './lib/managers/VariantManager.js';
import { FallbackManager } from './lib/managers/FallbackManager.js';
import GridRenderer from './lib/grid/GridRenderer.js';

// Make GridRenderer available globally
window.GridRenderer = GridRenderer;

// Initialize managers
window.managers = {
    models: new ModelManager(),
    groups: new GroupManager(),
    sections: new SectionManager(),
    topics: new TopicManager(),
    variants: new VariantManager(),
    fallbacks: new FallbackManager(),
};

// Initialize UI tabs
initTabs();

// Load models
window.managers.models.load();

// Also wire the "Create First Model" button (in case it's clicked before models load)
const createFirstBtn = document.getElementById('createFirstModelBtn');
if (createFirstBtn) createFirstBtn.onclick = () => window.managers.models.createModel();

// Wire "Add First Group" button (will be re-wired by GroupManager when needed, but ensure it's not null)
const createFirstGroupBtn = document.getElementById('createFirstGroupBtn');
if (createFirstGroupBtn) createFirstGroupBtn.onclick = () => window.managers.groups.openCreateModal();

// ========== Global helper functions for button disabling ==========
window.disableButtonsInContainer = function(container) {
    if (!container) return;
    const buttons = container.querySelectorAll('button, .add-btn, .save, #modalSaveBtn, #modalAddQuestionBtn, #modalAddAnswerBtn, #modalEditFollowupsBtn, #treeAddQuestionBtn, #treeAddAnswerBtn, #addRootBtn, #addChildBtn, #editNodeBtn, #deleteNodeBtn');
    buttons.forEach(btn => {
        if (btn.classList.contains('cancel') || btn.id === 'modalCancelBtn' || btn.id === 'treeModalCancelBtn') return;
        btn.disabled = true;
        btn.setAttribute('data-was-disabled', 'true');
    });
};

window.enableButtonsInContainer = function(container) {
    if (!container) return;
    const buttons = container.querySelectorAll('button, .add-btn, .save, #modalSaveBtn, #modalAddQuestionBtn, #modalAddAnswerBtn, #modalEditFollowupsBtn, #treeAddQuestionBtn, #treeAddAnswerBtn, #addRootBtn, #addChildBtn, #editNodeBtn, #deleteNodeBtn');
    buttons.forEach(btn => {
        if (btn.getAttribute('data-was-disabled') === 'true') {
            btn.disabled = false;
            btn.removeAttribute('data-was-disabled');
        }
    });
};
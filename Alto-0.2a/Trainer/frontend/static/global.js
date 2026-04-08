// global.js - Single entry point for all frontend modules
import { initTabs } from './global/tabs.js';
import { initSidebar } from './global/sidebar.js';
import { ModelManager } from './lib/managers/ModelManager.js';
import { GroupManager } from './lib/managers/GroupManager.js';
import { SectionManager } from './lib/managers/SectionManager.js';
import { TopicManager } from './lib/managers/TopicManager.js';
import { VariantManager } from './lib/managers/VariantManager.js';
import { FallbackManager } from './lib/managers/FallbackManager.js';
import GridRenderer from './lib/grid/GridRenderer.js';

window.GridRenderer = GridRenderer;

window.managers = {
    models: new ModelManager(),
    groups: new GroupManager(),
    sections: new SectionManager(),
    topics: new TopicManager(),
    variants: new VariantManager(),
    fallbacks: new FallbackManager(),
};

initTabs();
initSidebar();

window.managers.models.load();

const createFirstBtn = document.getElementById('createFirstModelBtn');
if (createFirstBtn) createFirstBtn.onclick = () => window.managers.models.createModel();

const createFirstGroupBtn = document.getElementById('createFirstGroupBtn');
if (createFirstGroupBtn) createFirstGroupBtn.onclick = () => window.managers.groups.openCreateModal();

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
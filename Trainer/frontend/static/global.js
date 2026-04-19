import { initTabs } from './global/tabs.js';
import { initSidebar } from './global/sidebar.js';
import { ModelManager } from './lib/managers/ModelManager.js';
import { GroupManager } from './lib/managers/GroupManager.js';
import { TopicManager } from './lib/managers/TopicManager.js';
import { VariantManager } from './lib/managers/VariantManager.js';
import { FallbackManager } from './lib/managers/FallbackManager.js';
import GridRenderer from './lib/grid/GridRenderer.js';
import { showConverterSettingsModal } from './components/ConverterSettingsModal.js';
import { checkLegacyModels } from './components/LegacyNotification.js';
import { error } from './lib/ui/error.js';

window.GridRenderer = GridRenderer;

// Install global error handler
error.installGlobalHandler();

window.managers = {
    models: new ModelManager(),
    groups: new GroupManager(),
    topics: new TopicManager(),
    variants: new VariantManager(),
    fallbacks: new FallbackManager(),
};

initTabs();
initSidebar();

document.getElementById('createFirstModelBtn')?.addEventListener('click', () => window.managers.models.createModel());
document.getElementById('createFirstGroupBtn')?.addEventListener('click', () => window.managers.groups.openCreateModal());
document.getElementById('createFirstTopicBtn')?.addEventListener('click', () => window.managers.topics.openCreateModal());
document.getElementById('createFirstVariantBtn')?.addEventListener('click', () => window.managers.variants.openCreateModal());
document.getElementById('createFirstFallbackBtn')?.addEventListener('click', () => window.managers.fallbacks.openCreateModal());

document.getElementById('converterSettingsBtn')?.addEventListener('click', showConverterSettingsModal);

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

window.managers.models.load().then(() => {
    checkLegacyModels();
});
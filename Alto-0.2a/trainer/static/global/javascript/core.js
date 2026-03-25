// static/global/javascript/core.js
// ========== Global State ==========
window.currentModel = null;
window.groups = [];
window.sections = [];

// ========== API Helpers ==========
window.apiGet = async function(url) {
    const r = await fetch(url);
    if (!r.ok) {
        const err = await r.json();
        throw new Error(err.error || `HTTP ${r.status}`);
    }
    return r.json();
};

window.apiPost = async function(url, data) {
    const r = await fetch(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data)
    });
    if (!r.ok) {
        const err = await r.json();
        throw new Error(err.error || `HTTP ${r.status}`);
    }
    return r.json();
};

window.apiPut = async function(url, data) {
    const r = await fetch(url, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data)
    });
    if (!r.ok) {
        const err = await r.json();
        throw new Error(err.error || `HTTP ${r.status}`);
    }
    return r.json();
};

window.apiDelete = async function(url) {
    const r = await fetch(url, { method: 'DELETE' });
    if (!r.ok) {
        const err = await r.json();
        throw new Error(err.error || `HTTP ${r.status}`);
    }
    return r.json();
};

// ========== UI Enable/Disable ==========
window.setControlsEnabled = function(enabled) {
    const modelDependentControls = [
        document.getElementById('modelSelect'),
        document.getElementById('editModelBtn'),
        document.getElementById('deleteModelBtn'),
        document.getElementById('exportBtn'),
        document.getElementById('addGroupBtn'),
        document.getElementById('createFirstGroupBtn'),
        document.getElementById('sectionFilter'),
        // Sections sidebar controls
        document.getElementById('sectionSearch'),
        document.getElementById('sectionSort'),
        document.getElementById('addSectionBtn'),
        // Topics sidebar controls
        document.getElementById('topicSearch'),
        document.getElementById('topicSectionFilter'),
        document.getElementById('topicFilter'),
        document.getElementById('topicSort'),
        document.getElementById('addTopicBtn'),
        // Variants sidebar controls
        document.getElementById('variantSearch'),
        document.getElementById('variantSectionFilter'),
        document.getElementById('variantSort'),
        document.getElementById('addVariantBtn')
    ];
    modelDependentControls.forEach(ctrl => { if (ctrl) ctrl.disabled = !enabled; });

    document.getElementById('importBtn').disabled = false;
    document.getElementById('createModelBtn').disabled = false;
    document.getElementById('createFirstModelBtn').disabled = false;
};
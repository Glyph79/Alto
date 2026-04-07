// fallbacks.js - using GridRenderer
let fallbacksGrid = null;
window.fallbacks = [];

window.loadFallbacks = async function() {
    if (!window.currentModel) return;
    try {
        window.fallbacks = await window.apiGet(`/api/models/${window.currentModel}/fallbacks`);
        renderFallbacksGrid();
        document.getElementById('fallbackSearch').disabled = false;
        document.getElementById('fallbackSort').disabled = false;
        document.getElementById('addFallbackBtn').disabled = false;
        if (typeof window.refreshGroupModalFallbackDropdown === 'function') {
            window.refreshGroupModalFallbackDropdown();
        }
        if (typeof window.refreshTreeModalFallbackDropdown === 'function') {
            window.refreshTreeModalFallbackDropdown();
        }
    } catch (err) {
        const container = document.getElementById('fallbacksGridContainer');
        window.showSimpleRetry(container, `Error loading fallbacks: ${err.message}`, async () => {
            await window.loadFallbacks();
        });
    }
};

function renderFallbacksGrid() {
    if (!fallbacksGrid) {
        fallbacksGrid = new GridRenderer({
            containerId: 'fallbacksGridContainer',
            items: window.fallbacks,
            renderItem: (fb, idx) => `
                <div class="fallback-card" data-card-index="${idx}" data-fallback-id="${fb.id}">
                    <div class="header">
                        <div style="display: flex; align-items: center; gap: 4px;">
                            <span class="fallback-name">${escapeHtml(fb.name)}</span>
                        </div>
                        <div class="card-actions">
                            <button class="card-edit" data-fallback-id="${fb.id}" title="Edit">✎</button>
                            <button class="card-delete" data-fallback-id="${fb.id}" title="Delete">🗑</button>
                        </div>
                    </div>
                    <div class="description">${escapeHtml(fb.description || '')}</div>
                    <div class="stats">
                        <span>📝 ${fb.answer_count} answer${fb.answer_count !== 1 ? 's' : ''}</span>
                        <span>🔗 ${fb.usage_count} group${fb.usage_count !== 1 ? 's' : ''}</span>
                    </div>
                </div>
            `,
            options: {
                searchInputId: 'fallbackSearch',
                searchFields: ['name', 'description'],
                sortSelectors: {
                    'name-asc': (a, b) => (a.name || '').localeCompare(b.name || ''),
                    'name-desc': (a, b) => (b.name || '').localeCompare(a.name || ''),
                    'usage-desc': (a, b) => (b.usage_count || 0) - (a.usage_count || 0),
                    'usage-asc': (a, b) => (a.usage_count || 0) - (b.usage_count || 0),
                    'answers-desc': (a, b) => (b.answer_count || 0) - (a.answer_count || 0),
                    'answers-asc': (a, b) => (a.answer_count || 0) - (b.answer_count || 0)
                },
                defaultSort: 'name-asc',
                emptyStateHtml: '<div class="empty-state">No fallbacks defined.</div>',
                onCardClick: (item) => editFallback(item.id),
                onCardEdit: (item) => editFallback(item.id),
                onCardDelete: (item) => deleteFallback(item.id)
            }
        });
    } else {
        fallbacksGrid.setItems(window.fallbacks);
    }
}

window.clearFallbacks = function() {
    if (fallbacksGrid) fallbacksGrid.destroy();
    fallbacksGrid = null;
    window.fallbacks = [];
};

let currentFallbackAnswers = [];
let isSavingFallback = false;

function openFallbackModal(title, fallback, onSave) {
    document.getElementById('fallbackModalTitle').textContent = title;
    document.getElementById('fallbackName').value = fallback?.name || '';
    document.getElementById('fallbackDescription').value = fallback?.description || '';
    currentFallbackAnswers = fallback?.answers ? [...fallback.answers] : [];
    renderFallbackAnswersList();
    window._fallbackModalOnSave = onSave;

    document.getElementById('fallbackAddAnswerBtn').onclick = addFallbackAnswer;
    document.getElementById('fallbackSaveBtn').onclick = () => saveFallbackModal();
    document.getElementById('fallbackCancelBtn').onclick = closeFallbackModal;

    const saveBtn = document.getElementById('fallbackSaveBtn');
    saveBtn.disabled = false;
    saveBtn.textContent = 'Save';

    window.pushModal('fallbackModal');
}

function closeFallbackModal() {
    window.popModal();
    window._fallbackModalOnSave = null;
    isSavingFallback = false;
    const saveBtn = document.getElementById('fallbackSaveBtn');
    if (saveBtn) {
        saveBtn.disabled = false;
        saveBtn.textContent = 'Save';
    }
}

function renderFallbackAnswersList() {
    const list = document.getElementById('fallbackAnswersList');
    list.innerHTML = '';
    currentFallbackAnswers.forEach((ans, idx) => {
        const li = document.createElement('li');
        li.innerHTML = `
            <span>${escapeHtml(ans)}</span>
            <span>
                <button class="edit-fallback-answer" data-idx="${idx}">✎</button>
                <button class="delete-fallback-answer" data-idx="${idx}">🗑</button>
            </span>
        `;
        list.appendChild(li);
    });
    list.querySelectorAll('.edit-fallback-answer').forEach(btn => {
        btn.addEventListener('click', () => editFallbackAnswer(parseInt(btn.dataset.idx)));
    });
    list.querySelectorAll('.delete-fallback-answer').forEach(btn => {
        btn.addEventListener('click', () => deleteFallbackAnswer(parseInt(btn.dataset.idx)));
    });
}

function addFallbackAnswer() {
    window.showSimpleModal('Add Answer', [{ name: 'text', label: 'Answer', value: '' }], (vals, errorDiv) => {
        const text = vals.text.trim();
        if (!text) {
            errorDiv.textContent = 'Answer cannot be empty.';
            errorDiv.style.display = 'block';
            return;
        }
        currentFallbackAnswers.push(text);
        renderFallbackAnswersList();
    }, 'Add');
}

function editFallbackAnswer(idx) {
    const old = currentFallbackAnswers[idx];
    window.showSimpleModal('Edit Answer', [{ name: 'text', label: 'Answer', value: old }], (vals, errorDiv) => {
        const newText = vals.text.trim();
        if (!newText) {
            errorDiv.textContent = 'Answer cannot be empty.';
            errorDiv.style.display = 'block';
            return;
        }
        currentFallbackAnswers[idx] = newText;
        renderFallbackAnswersList();
    }, 'Save');
}

function deleteFallbackAnswer(idx) {
    window.showConfirmModal('Delete this answer?', () => {
        currentFallbackAnswers.splice(idx, 1);
        renderFallbackAnswersList();
    });
}

async function saveFallbackModal() {
    if (isSavingFallback) return;
    const name = document.getElementById('fallbackName').value.trim();
    if (!name) {
        const modalContent = document.querySelector('#fallbackModal .modal-content');
        window.showSimpleRetry(modalContent, 'Fallback name is required.', () => {});
        return;
    }
    const description = document.getElementById('fallbackDescription').value.trim();
    if (currentFallbackAnswers.length === 0) {
        const modalContent = document.querySelector('#fallbackModal .modal-content');
        window.showSimpleRetry(modalContent, 'At least one answer is required.', () => {});
        return;
    }

    const isNew = !window._fallbackModalOnSave?.id;
    if (isNew && window.fallbacks.some(fb => fb.name.toLowerCase() === name.toLowerCase())) {
        const modalContent = document.querySelector('#fallbackModal .modal-content');
        window.showSimpleRetry(modalContent, `A fallback named "${name}" already exists.`, () => {});
        return;
    }

    const data = { name, description, answers: currentFallbackAnswers };
    const saveBtn = document.getElementById('fallbackSaveBtn');
    const originalText = saveBtn.textContent;
    saveBtn.disabled = true;
    saveBtn.textContent = 'Saving...';
    isSavingFallback = true;

    try {
        if (window._fallbackModalOnSave) {
            await window._fallbackModalOnSave(data);
        }
        resetFallbacksFilters();
        closeFallbackModal();
        await window.loadFallbacks();
    } catch (err) {
        const modalContent = document.querySelector('#fallbackModal .modal-content');
        window.showSimpleRetry(modalContent, `Error saving fallback: ${err.message}`, async () => {
            saveBtn.disabled = false;
            saveBtn.textContent = originalText;
            isSavingFallback = false;
            await saveFallbackModal();
        });
        return;
    } finally {
        saveBtn.disabled = false;
        saveBtn.textContent = originalText;
        isSavingFallback = false;
    }
}

function addFallback() {
    openFallbackModal('Add Fallback', null, async (data) => {
        await window.apiPost(`/api/models/${window.currentModel}/fallbacks`, data);
    });
}

async function editFallback(id) {
    const fallback = window.fallbacks.find(f => f.id == id);
    if (!fallback) return;
    const full = await window.apiGet(`/api/models/${window.currentModel}/fallbacks/${id}`);
    openFallbackModal('Edit Fallback', full, async (data) => {
        await window.apiPut(`/api/models/${window.currentModel}/fallbacks/${id}`, data);
    });
}

function deleteFallback(id) {
    window.showConfirmModal('Delete this fallback? Groups and nodes using it will have no fallback assigned.', async () => {
        try {
            await window.apiDelete(`/api/models/${window.currentModel}/fallbacks/${id}`);
            resetFallbacksFilters();
            await window.loadFallbacks();
        } catch (err) {
            const container = document.getElementById('fallbacksGridContainer');
            window.showSimpleRetry(container, `Failed to delete fallback: ${err.message}`, async () => {
                await deleteFallback(id);
            });
        }
    });
}

function resetFallbacksFilters() {
    const search = document.getElementById('fallbackSearch');
    if (search) search.value = '';
    const sort = document.getElementById('fallbackSort');
    if (sort) sort.value = 'name-asc';
    if (search) search.dispatchEvent(new Event('input', { bubbles: true }));
    if (sort) sort.dispatchEvent(new Event('change', { bubbles: true }));
}

document.getElementById('addFallbackBtn').addEventListener('click', addFallback);
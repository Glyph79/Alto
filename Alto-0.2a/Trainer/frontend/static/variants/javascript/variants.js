// ========== Variants State ==========
window.variants = [];
let variantCards = [];
let currentVariantId = null;
let currentVariantWords = [];
let currentVariantName = '';

// ========== Load Variants ==========
window.loadVariants = async function() {
    if (!window.currentModel) return;
    try {
        window.variants = await window.apiGet(`/api/models/${window.currentModel}/variants`);
        renderVariantsGrid();
        document.getElementById('variantSearch').disabled = false;
        document.getElementById('variantSectionFilter').disabled = false;
        document.getElementById('variantSort').disabled = false;
        document.getElementById('addVariantBtn').disabled = false;
    } catch (err) {
        console.error('Error loading variants:', err);
        const container = document.getElementById('variantsGridContainer');
        window.showSimpleRetry(container, `Error loading variants: ${err.message}`, async () => {
            await window.loadVariants();
        });
    }
};

window.clearVariants = function() {
    window.variants = [];
    const container = document.getElementById('variantsGridContainer');
    if (container) container.innerHTML = '';
    document.getElementById('variantSearch').disabled = true;
    document.getElementById('variantSectionFilter').disabled = true;
    document.getElementById('variantSort').disabled = true;
    document.getElementById('addVariantBtn').disabled = true;
    if (window.variantsManager) window.variantsManager.setCardArray([]);
};

function populateVariantFilters() {
    const sectionSelect = document.getElementById('variantSectionFilter');
    const sections = window.sections || [];
    const currentSection = sectionSelect.value;
    sectionSelect.innerHTML = '<option value="All Sections">All Sections</option>';
    sections.forEach(s => {
        const opt = document.createElement('option');
        opt.value = s;
        opt.textContent = s;
        sectionSelect.appendChild(opt);
    });
    if (sections.includes(currentSection)) {
        sectionSelect.value = currentSection;
    } else {
        sectionSelect.value = 'All Sections';
    }
}

function renderVariantsGrid() {
    const container = document.getElementById('variantsGridContainer');
    if (!container) return;

    let html = '<div class="variants-grid grid">';
    window.variants.forEach((v, idx) => {
        const section = v.section || 'Uncategorized';
        const wordCount = v.words.length;
        html += `
            <div class="variant-card" data-index="${idx}">
                <div class="header">
                    <span class="section-badge">${escapeHtml(section)}</span>
                    <div class="card-actions">
                        <button class="edit-variant" data-id="${v.id}" title="Edit">✎</button>
                        <button class="delete-variant" data-id="${v.id}" title="Delete">🗑</button>
                    </div>
                </div>
                <h4 class="variant-name">${escapeHtml(v.name || 'Unnamed')}</h4>
                <div class="stats">
                    <span>📝 ${wordCount} word${wordCount !== 1 ? 's' : ''}</span>
                </div>
            </div>
        `;
    });
    html += '</div>';
    container.innerHTML = html;

    if (window.variantsManager) {
        window.variantsManager.grid = container.querySelector('.grid') || container;
    }

    // Event delegation – single listener for all variant cards
    container.addEventListener('click', (e) => {
        const card = e.target.closest('.variant-card');
        if (!card) return;
        const idx = parseInt(card.dataset.index);
        const variantId = window.variants[idx]?.id;
        if (!variantId) return;
        if (e.target.closest('.edit-variant')) {
            editVariant(variantId);
        } else if (e.target.closest('.delete-variant')) {
            deleteVariant(variantId);
        } else {
            editVariant(variantId);
        }
    });

    variantCards = Array.from(document.querySelectorAll('.variant-card')).map(card => ({
        element: card,
        item: window.variants[parseInt(card.dataset.index)]
    }));

    populateVariantFilters();

    if (!window.variantsManager) {
        window.variantsManager = new window.SearchManager({
            containerId: 'variantsGridContainer',
            cardArray: variantCards,
            searchInputId: 'variantSearch',
            searchFields: ['name', 'words'],
            filterSelectors: {
                'variantSectionFilter': (item, value) => {
                    if (value === 'All Sections') return true;
                    const itemSection = item.section || 'Uncategorized';
                    return itemSection === value;
                }
            },
            sortSelectors: {
                'name-asc': (a, b) => (a.name || '').localeCompare(b.name || ''),
                'name-desc': (a, b) => (b.name || '').localeCompare(a.name || ''),
                'section-asc': (a, b) => (a.section || '').localeCompare(b.section || ''),
                'section-desc': (a, b) => (b.section || '').localeCompare(a.section || ''),
                'words-desc': (a, b) => b.words.length - a.words.length,
                'words-asc': (a, b) => a.words.length - b.words.length
            },
            defaultSort: 'name-asc'
        });
    } else {
        window.variantsManager.setCardArray(variantCards);
    }
}

function openVariantModal(title, name, section, words, onSave) {
    document.getElementById('variantModalTitle').textContent = title;
    document.getElementById('variantName').value = name || '';

    const sectionSelect = document.getElementById('variantSection');
    sectionSelect.innerHTML = '<option value="">(Uncategorized)</option>';
    (window.sections || []).forEach(s => {
        const opt = document.createElement('option');
        opt.value = s;
        opt.textContent = s;
        sectionSelect.appendChild(opt);
    });
    sectionSelect.value = section || '';

    currentVariantWords = words ? [...words] : [];
    renderVariantWordsList();

    window._variantModalOnSave = onSave;

    document.getElementById('variantAddWordBtn').onclick = addVariantWord;
    document.getElementById('variantSaveBtn').onclick = saveVariantModal;
    document.getElementById('variantCancelBtn').onclick = closeVariantModal;

    window.pushModal('variantModal');
}

function closeVariantModal() {
    window.popModal();
    window._variantModalOnSave = null;
}

function renderVariantWordsList() {
    const list = document.getElementById('variantWordsList');
    list.innerHTML = '';
    currentVariantWords.forEach((word, idx) => {
        const li = document.createElement('li');
        li.innerHTML = `
            <span>${escapeHtml(word)}</span>
            <span>
                <button class="edit-word" data-idx="${idx}">✎</button>
                <button class="delete-word" data-idx="${idx}">🗑</button>
            </span>
        `;
        list.appendChild(li);
    });
    list.querySelectorAll('.edit-word').forEach(btn => {
        btn.addEventListener('click', () => editVariantWord(parseInt(btn.dataset.idx)));
    });
    list.querySelectorAll('.delete-word').forEach(btn => {
        btn.addEventListener('click', () => deleteVariantWord(parseInt(btn.dataset.idx)));
    });
}

function addVariantWord() {
    window.showSimpleModal('Add Word', [{ name: 'word', label: 'Word', value: '' }], (vals, errorDiv) => {
        const word = vals.word.trim();
        if (!word) {
            errorDiv.textContent = 'Word cannot be empty.';
            errorDiv.style.display = 'block';
            return;
        }
        currentVariantWords.push(word);
        renderVariantWordsList();
    }, 'Add');
}

function editVariantWord(idx) {
    const oldWord = currentVariantWords[idx];
    window.showSimpleModal('Edit Word', [{ name: 'word', label: 'Word', value: oldWord }], (vals, errorDiv) => {
        const newWord = vals.word.trim();
        if (!newWord) {
            errorDiv.textContent = 'Word cannot be empty.';
            errorDiv.style.display = 'block';
            return;
        }
        currentVariantWords[idx] = newWord;
        renderVariantWordsList();
    }, 'Save');
}

function deleteVariantWord(idx) {
    window.showConfirmModal('Delete this word?', () => {
        currentVariantWords.splice(idx, 1);
        renderVariantWordsList();
    });
}

async function saveVariantModal() {
    const name = document.getElementById('variantName').value.trim();
    if (!name) {
        const modalContent = document.querySelector('#variantModal .modal-content');
        window.showSimpleRetry(modalContent, 'Variant name is required.', () => {});
        return;
    }
    const section = document.getElementById('variantSection').value || null;
    if (currentVariantWords.length === 0) {
        const modalContent = document.querySelector('#variantModal .modal-content');
        window.showSimpleRetry(modalContent, 'At least one word is required.', () => {});
        return;
    }

    const data = { name, words: currentVariantWords, section };

    try {
        if (window._variantModalOnSave) {
            await window._variantModalOnSave(data);
        }
        closeVariantModal();
        await window.loadVariants();
    } catch (err) {
        const modalContent = document.querySelector('#variantModal .modal-content');
        window.showSimpleRetry(modalContent, `Error saving variant: ${err.message}`, async () => {
            await saveVariantModal();
        });
    }
}

function addVariant() {
    openVariantModal('Add Variant', '', '', [], async (data) => {
        await window.apiPost(`/api/models/${window.currentModel}/variants`, data);
    });
}

function editVariant(id) {
    const variant = window.variants.find(v => v.id == id);
    if (!variant) return;
    openVariantModal('Edit Variant', variant.name, variant.section, variant.words, async (data) => {
        await window.apiPut(`/api/models/${window.currentModel}/variants/${id}`, data);
    });
}

function deleteVariant(id) {
    window.showConfirmModal('Delete this variant group?', async () => {
        try {
            await window.apiDelete(`/api/models/${window.currentModel}/variants/${id}`);
            await window.loadVariants();
        } catch (err) {
            const container = document.getElementById('variantsGridContainer');
            window.showSimpleRetry(container, `Failed to delete variant: ${err.message}`, async () => {
                await deleteVariant(id);
            });
        }
    });
}

document.getElementById('addVariantBtn').addEventListener('click', addVariant);
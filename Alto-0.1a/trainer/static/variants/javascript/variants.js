// ========== Variants State ==========
window.variants = [];
let variantCards = [];
let currentVariantId = null;          // null for new variant, else existing id
let currentVariantWords = [];          // array of words for the variant being edited

// ========== Load Variants ==========
window.loadVariants = async function() {
    if (!window.currentModel) return;
    try {
        window.variants = await window.apiGet(`/api/models/${window.currentModel}/variants`);
        renderVariantsGrid();
        document.getElementById('variantSearch').disabled = false;
        document.getElementById('variantTopicFilter').disabled = false;
        document.getElementById('addVariantBtn').disabled = false;
    } catch (err) {
        console.error('Error loading variants:', err);
    }
};

// ========== Clear Variants (when no model) ==========
window.clearVariants = function() {
    window.variants = [];
    const container = document.getElementById('variantsGridContainer');
    if (container) container.innerHTML = '';
    document.getElementById('variantSearch').disabled = true;
    document.getElementById('variantTopicFilter').disabled = true;
    document.getElementById('addVariantBtn').disabled = true;
};

function renderVariantsGrid() {
    const container = document.getElementById('variantsGridContainer');
    if (!container) return;

    let html = '<div class="variants-grid">';
    window.variants.forEach((v, idx) => {
        const topic = v.topic || 'Global';
        const words = v.words.join(', ');
        const wordCount = v.words.length;
        html += `
            <div class="variant-card" data-index="${idx}">
                <div class="header">
                    <span class="topic-badge">${topic}</span>
                    <div class="card-actions">
                        <button class="edit-variant" title="Edit">✎</button>
                        <button class="delete-variant" title="Delete">🗑</button>
                    </div>
                </div>
                <div class="words">${words}</div>
                <div class="stats">
                    <span>📝 ${wordCount} word${wordCount !== 1 ? 's' : ''}</span>
                </div>
            </div>
        `;
    });
    html += '</div>';
    container.innerHTML = html;

    // Attach handlers
    document.querySelectorAll('.variant-card').forEach(card => {
        const idx = parseInt(card.dataset.index);
        card.addEventListener('click', (e) => {
            if (e.target.closest('.card-actions')) return;
            editVariant(window.variants[idx].id);
        });
        card.querySelector('.edit-variant').addEventListener('click', (e) => {
            e.stopPropagation();
            editVariant(window.variants[idx].id);
        });
        card.querySelector('.delete-variant').addEventListener('click', (e) => {
            e.stopPropagation();
            deleteVariant(window.variants[idx].id);
        });
    });

    variantCards = Array.from(document.querySelectorAll('.variant-card')).map(card => ({
        element: card,
        item: window.variants[parseInt(card.dataset.index)]
    }));

    filterVariants();
}

function filterVariants() {
    const searchTerm = document.getElementById('variantSearch').value.toLowerCase();
    const topicFilter = document.getElementById('variantTopicFilter').value;
    const grid = document.querySelector('.variants-grid');
    if (!grid) return;

    window.filterCards(variantCards, (item) => {
        const wordsString = item.words.join(', ').toLowerCase();
        const matchesSearch = wordsString.includes(searchTerm);
        if (!matchesSearch) return false;
        if (topicFilter === 'All') return true;
        return (item.topic || 'Global') === topicFilter;
    }, null, grid);
}

// ========== Variant Modal Functions ==========
function openVariantModal(title, topic, words, onSave) {
    document.getElementById('variantModalTitle').textContent = title;
    document.getElementById('variantTopic').value = topic || '';
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
            <span>${word}</span>
            <span>
                <button onclick="editVariantWord(${idx})">✎</button>
                <button onclick="deleteVariantWord(${idx})">🗑</button>
            </span>
        `;
        list.appendChild(li);
    });
}

function addVariantWord() {
    window.showSimpleModal('Add Word', [{ name: 'word', label: 'Word', value: '' }], (vals) => {
        const word = vals.word.trim();
        if (!word) {
            alert('Word cannot be empty.');
            return;
        }
        currentVariantWords.push(word);
        renderVariantWordsList();
    }, 'Add');
}

window.editVariantWord = function(idx) {
    const oldWord = currentVariantWords[idx];
    window.showSimpleModal('Edit Word', [{ name: 'word', label: 'Word', value: oldWord }], (vals) => {
        const newWord = vals.word.trim();
        if (!newWord) {
            alert('Word cannot be empty.');
            return;
        }
        currentVariantWords[idx] = newWord;
        renderVariantWordsList();
    }, 'Save');
};

window.deleteVariantWord = function(idx) {
    window.showConfirmModal('Delete this word?', () => {
        currentVariantWords.splice(idx, 1);
        renderVariantWordsList();
    });
};

async function saveVariantModal() {
    const topic = document.getElementById('variantTopic').value.trim() || null;
    if (currentVariantWords.length === 0) {
        alert('At least one word is required.');
        return;
    }

    const data = { topic, words: currentVariantWords };
    try {
        if (window._variantModalOnSave) {
            await window._variantModalOnSave(data);
        }
        closeVariantModal();
        await window.loadVariants();
    } catch (err) {
        alert('Error saving variant: ' + err.message);
    }
}

// ========== Variant CRUD ==========
function addVariant() {
    openVariantModal('Add Variant', '', [], async (data) => {
        await window.apiPost(`/api/models/${window.currentModel}/variants`, data);
    });
}

function editVariant(id) {
    const variant = window.variants.find(v => v.id == id);
    if (!variant) return;
    openVariantModal('Edit Variant', variant.topic, variant.words, async (data) => {
        await window.apiPut(`/api/models/${window.currentModel}/variants/${id}`, data);
    });
}

function deleteVariant(id) {
    window.showConfirmModal('Delete this variant group?', async () => {
        await window.apiDelete(`/api/models/${window.currentModel}/variants/${id}`);
        await window.loadVariants();
    });
}

// Event listeners
document.getElementById('variantSearch').addEventListener('input', filterVariants);
document.getElementById('variantTopicFilter').addEventListener('change', filterVariants);
document.getElementById('addVariantBtn').addEventListener('click', addVariant);
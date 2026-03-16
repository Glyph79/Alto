// ========== Variants State ==========
window.variants = [];
let variantCards = [];

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

function renderVariantsGrid() {
    const container = document.getElementById('variantsGridContainer');
    if (!container) return;

    let html = '<div class="variants-grid">';
    window.variants.forEach(v => {
        const topic = v.topic || 'Global';
        const words = v.words.join(', ');
        html += `
            <div class="variant-card" data-id="${v.id}">
                <div class="header">
                    <span class="topic-badge">${topic}</span>
                    <div class="card-actions">
                        <button class="edit-variant" title="Edit">✎</button>
                        <button class="delete-variant" title="Delete">🗑</button>
                    </div>
                </div>
                <div class="words">${words}</div>
            </div>
        `;
    });
    html += '</div>';
    container.innerHTML = html;

    // Attach handlers
    document.querySelectorAll('.variant-card').forEach(card => {
        const id = card.dataset.id;
        card.addEventListener('click', (e) => {
            if (e.target.closest('.card-actions')) return;
            editVariant(id);
        });
        card.querySelector('.edit-variant').addEventListener('click', (e) => {
            e.stopPropagation();
            editVariant(id);
        });
        card.querySelector('.delete-variant').addEventListener('click', (e) => {
            e.stopPropagation();
            deleteVariant(id);
        });
    });

    variantCards = Array.from(document.querySelectorAll('.variant-card')).map(card => ({
        element: card,
        id: parseInt(card.dataset.id),
        topic: card.querySelector('.topic-badge').textContent,
        words: card.querySelector('.words').textContent
    }));

    filterVariants();
}

function filterVariants() {
    const searchTerm = document.getElementById('variantSearch').value.toLowerCase();
    const topicFilter = document.getElementById('variantTopicFilter').value;

    let visibleCards = variantCards.filter(card => {
        const matchesSearch = card.words.toLowerCase().includes(searchTerm);
        if (!matchesSearch) return false;
        if (topicFilter === 'All') return true;
        return card.topic === topicFilter;
    });

    const grid = document.querySelector('.variants-grid');
    visibleCards.forEach(card => grid.appendChild(card.element));
    variantCards.forEach(card => {
        card.element.style.display = visibleCards.includes(card) ? 'flex' : 'none';
    });
}

function populateVariantTopicFilter() {
    const select = document.getElementById('variantTopicFilter');
    select.innerHTML = '<option value="All">All Topics</option><option value="Global">Global</option>';
    window.sections.forEach(s => {
        const opt = document.createElement('option');
        opt.value = s;
        opt.textContent = s;
        select.appendChild(opt);
    });
}

// ========== Variant CRUD ==========
function addVariant() {
    window.showSimpleModal('Add Word Variants', [
        { name: 'topic', label: 'Topic (leave blank for global)', value: '' },
        { name: 'words', label: 'Words (comma separated)', value: '' }
    ], async (vals, errorDiv) => {
        const words = vals.words.split(',').map(w => w.trim()).filter(w => w);
        if (words.length === 0) {
            errorDiv.textContent = 'At least one word required.';
            errorDiv.style.display = 'block';
            return;
        }
        const topic = vals.topic || null;
        await window.apiPost(`/api/models/${window.currentModel}/variants`, { topic, words });
        await window.loadVariants();
    }, 'Add');
}

function editVariant(id) {
    const variant = window.variants.find(v => v.id == id);
    if (!variant) return;
    window.showSimpleModal('Edit Word Variants', [
        { name: 'topic', label: 'Topic (leave blank for global)', value: variant.topic || '' },
        { name: 'words', label: 'Words (comma separated)', value: variant.words.join(', ') }
    ], async (vals, errorDiv) => {
        const words = vals.words.split(',').map(w => w.trim()).filter(w => w);
        if (words.length === 0) {
            errorDiv.textContent = 'At least one word required.';
            errorDiv.style.display = 'block';
            return;
        }
        const topic = vals.topic || null;
        await window.apiPut(`/api/models/${window.currentModel}/variants/${id}`, { topic, words });
        await window.loadVariants();
    }, 'Save');
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
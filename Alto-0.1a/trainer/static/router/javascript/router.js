// ========== Router State ==========
window.routes = [];          // stores {id, module_name, variant_count}
let routeCards = [];
let currentRouteIndex = -1;
let currentRouteVariants = [];

// ========== Clear Routes (when no model) ==========
window.clearRoutes = function() {
    window.routes = [];
    const container = document.getElementById('routesGridContainer');
    if (container) container.innerHTML = '';
    document.getElementById('routeSearch').disabled = true;
    document.getElementById('routeSort').disabled = true;
    document.getElementById('addRouteBtn').disabled = true;
    if (window.routesManager) window.routesManager.setCardArray([]);
};

// ========== Load Route Summaries ==========
window.loadRouteSummaries = async function() {
    if (!window.currentModel) {
        window.clearRoutes();
        return;
    }
    try {
        window.routes = await window.apiGet(`/api/models/${window.currentModel}/routes/summaries`);
        renderRoutesGrid();
        document.getElementById('routeSearch').disabled = false;
        document.getElementById('routeSort').disabled = false;
        document.getElementById('addRouteBtn').disabled = false;
    } catch (err) {
        console.error('Error loading route summaries:', err);
        window.clearRoutes();
    }
};

function renderRoutesGrid() {
    const container = document.getElementById('routesGridContainer');
    if (!container) return;

    if (window.routes.length === 0) {
        container.innerHTML = '<div class="empty-state" style="padding: 40px;"><p>No routes defined.</p></div>';
        routeCards = [];
        if (window.routesManager) window.routesManager.setCardArray([]);
        return;
    }

    let html = '<div class="routes-grid grid">';
    window.routes.forEach((route, idx) => {
        const variantText = `${route.variant_count} variant${route.variant_count !== 1 ? 's' : ''}`;
        html += `
            <div class="route-card" data-index="${idx}">
                <div class="header">
                    <span class="module-badge">${route.module_name}</span>
                    <div class="card-actions">
                        <button class="edit-route" title="Edit">✎</button>
                        <button class="delete-route" title="Delete">🗑</button>
                    </div>
                </div>
                <div class="variants">${variantText}</div>
                <div class="stats">
                    <span>🔤 ${route.variant_count} variant${route.variant_count !== 1 ? 's' : ''}</span>
                </div>
            </div>
        `;
    });
    html += '</div>';
    container.innerHTML = html;

    // Update manager's grid reference
    if (window.routesManager) {
        window.routesManager.grid = container.querySelector('.grid') || container;
    }

    routeCards = Array.from(document.querySelectorAll('.route-card')).map(card => ({
        element: card,
        item: window.routes[parseInt(card.dataset.index)],
        index: parseInt(card.dataset.index)
    }));

    routeCards.forEach(card => {
        const index = card.index;
        card.element.addEventListener('click', (e) => {
            if (e.target.closest('.card-actions')) return;
            openRouteModal(index);
        });
        card.element.querySelector('.edit-route').addEventListener('click', (e) => {
            e.stopPropagation();
            openRouteModal(index);
        });
        card.element.querySelector('.delete-route').addEventListener('click', (e) => {
            e.stopPropagation();
            deleteRoute(index);
        });
    });

    if (!window.routesManager) {
        window.routesManager = new window.SearchManager({
            containerId: 'routesGridContainer',
            cardArray: routeCards,
            searchInputId: 'routeSearch',
            searchFields: ['module_name'],
            filterSelectors: {},
            sortSelectors: {
                'name-asc': (a, b) => a.module_name.localeCompare(b.module_name),
                'name-desc': (a, b) => b.module_name.localeCompare(a.module_name),
                'variants-desc': (a, b) => (b.variant_count || 0) - (a.variant_count || 0),
                'variants-asc': (a, b) => (a.variant_count || 0) - (b.variant_count || 0)
            },
            defaultSort: 'name-asc'
        });
    } else {
        window.routesManager.setCardArray(routeCards);
    }
}

// ========== Route Modal Functions ==========
function openRouteModal(index) {
    if (!window.currentModel) return;
    currentRouteIndex = index;
    const modal = document.getElementById('routeModal');
    const title = document.getElementById('routeModalTitle');
    const moduleInput = document.getElementById('routeModuleName');

    if (index === -1) {
        title.textContent = 'Add Route';
        moduleInput.value = '';
        currentRouteVariants = [];
        renderRouteVariantsList();
        attachRouteModalHandlers();
        window.pushModal('routeModal');
    } else {
        title.textContent = 'Edit Route';
        (async () => {
            try {
                const fullRoute = await window.apiGet(`/api/models/${window.currentModel}/routes/${index}/full`);
                moduleInput.value = fullRoute.module_name;
                currentRouteVariants = fullRoute.variants;
                renderRouteVariantsList();
                attachRouteModalHandlers();
                window.pushModal('routeModal');
            } catch (err) {
                alert('Error loading route details: ' + err.message);
            }
        })();
    }
}

function attachRouteModalHandlers() {
    document.getElementById('routeAddVariantBtn').onclick = addRouteVariant;
    document.getElementById('routeSaveBtn').onclick = saveRouteModal;
    document.getElementById('routeCancelBtn').onclick = closeRouteModal;
}

function closeRouteModal() {
    window.popModal();
    currentRouteIndex = -1;
    currentRouteVariants = [];
}

function renderRouteVariantsList() {
    const list = document.getElementById('routeVariantsList');
    list.innerHTML = '';
    currentRouteVariants.forEach((variant, idx) => {
        const li = document.createElement('li');
        li.innerHTML = `
            <span>${variant}</span>
            <span>
                <button onclick="editRouteVariant(${idx})">✎</button>
                <button onclick="deleteRouteVariant(${idx})">🗑</button>
            </span>
        `;
        list.appendChild(li);
    });
}

function addRouteVariant() {
    window.showSimpleModal('Add Variant Phrase', [{ name: 'phrase', label: 'Phrase', value: '' }], (vals) => {
        const phrase = vals.phrase.trim();
        if (!phrase) {
            alert('Phrase cannot be empty.');
            return;
        }
        currentRouteVariants.push(phrase);
        renderRouteVariantsList();
    }, 'Add');
}

window.editRouteVariant = function(idx) {
    const oldPhrase = currentRouteVariants[idx];
    window.showSimpleModal('Edit Variant Phrase', [{ name: 'phrase', label: 'Phrase', value: oldPhrase }], (vals) => {
        const newPhrase = vals.phrase.trim();
        if (!newPhrase) {
            alert('Phrase cannot be empty.');
            return;
        }
        currentRouteVariants[idx] = newPhrase;
        renderRouteVariantsList();
    }, 'Save');
};

window.deleteRouteVariant = function(idx) {
    window.showConfirmModal('Delete this variant phrase?', () => {
        currentRouteVariants.splice(idx, 1);
        renderRouteVariantsList();
    });
};

async function saveRouteModal() {
    if (!window.currentModel) return;
    const moduleName = document.getElementById('routeModuleName').value.trim();
    if (!moduleName) {
        alert('Module name is required.');
        return;
    }
    if (currentRouteVariants.length === 0) {
        alert('At least one variant phrase is required.');
        return;
    }

    const data = { module_name: moduleName, variants: currentRouteVariants };

    try {
        if (currentRouteIndex === -1) {
            await window.apiPost(`/api/models/${window.currentModel}/routes`, data);
        } else {
            await window.apiPut(`/api/models/${window.currentModel}/routes/${currentRouteIndex}`, data);
        }
        closeRouteModal();
        await window.loadRouteSummaries();
    } catch (err) {
        alert('Error saving route: ' + err.message);
    }
}

async function deleteRoute(index) {
    if (!window.currentModel) return;
    window.showConfirmModal('Delete this route?', async () => {
        await window.apiDelete(`/api/models/${window.currentModel}/routes/${index}`);
        await window.loadRouteSummaries();
    });
}

document.getElementById('addRouteBtn').addEventListener('click', () => openRouteModal(-1));
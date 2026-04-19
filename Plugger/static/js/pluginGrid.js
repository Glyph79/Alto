import { apiGet, apiDelete } from './api.js';
import { showAlertModal, showConfirmModal, escapeHtml } from './modals.js';
import { openPluginModal } from './pluginModal.js';

export let plugins = [];

export async function loadPlugins() {
    try {
        plugins = await apiGet('/api/plugins');
        renderPlugins();
    } catch (err) {
        showAlertModal('Error', 'Error loading plugins: ' + err.message);
    }
}

export function renderPlugins() {
    const searchTerm = document.getElementById('searchInput').value.toLowerCase();
    const sortBy = document.getElementById('sortSelect').value;
    const gridContainer = document.getElementById('pluginsGridContainer');
    const emptyState = document.getElementById('emptyState');

    let filtered = plugins.filter(p => p.name.toLowerCase().includes(searchTerm) ||
                                        (p.description && p.description.toLowerCase().includes(searchTerm)));

    filtered.sort((a, b) => {
        if (sortBy === 'name-asc') return a.name.localeCompare(b.name);
        if (sortBy === 'name-desc') return b.name.localeCompare(a.name);
        if (sortBy === 'version-desc') return b.version.localeCompare(a.version);
        if (sortBy === 'version-asc') return a.version.localeCompare(b.version);
        return 0;
    });

    if (filtered.length === 0) {
        gridContainer.innerHTML = '';
        emptyState.style.display = 'block';
        return;
    }
    emptyState.style.display = 'none';

    let html = '<div class="plugins-grid">';
    filtered.forEach(p => {
        html += `
            <div class="plugin-card" data-name="${escapeHtml(p.name)}">
                <div class="header">
                    <span class="version">v${escapeHtml(p.version)}</span>
                    <div class="card-actions">
                        <button class="edit-plugin" data-name="${escapeHtml(p.name)}" title="Edit">✎</button>
                        <button class="delete-plugin" data-name="${escapeHtml(p.name)}" title="Delete">🗑</button>
                    </div>
                </div>
                <h4>${escapeHtml(p.name)}</h4>
                <div class="description">${escapeHtml(p.description || '')}</div>
            </div>
        `;
    });
    html += '</div>';
    gridContainer.innerHTML = html;

    document.querySelectorAll('.plugin-card').forEach(card => {
        const name = card.dataset.name;
        card.addEventListener('click', (e) => {
            if (e.target.closest('.card-actions')) return;
            openPluginModal(name);
        });
    });
    document.querySelectorAll('.edit-plugin').forEach(btn => {
        btn.addEventListener('click', (e) => {
            e.stopPropagation();
            openPluginModal(btn.dataset.name);
        });
    });
    document.querySelectorAll('.delete-plugin').forEach(btn => {
        btn.addEventListener('click', (e) => {
            e.stopPropagation();
            deletePlugin(btn.dataset.name);
        });
    });
}

async function deletePlugin(name) {
    showConfirmModal(`Delete plugin "${name}"? This action cannot be undone.`, async () => {
        try {
            await apiDelete(`/api/plugins/${encodeURIComponent(name)}`);
            await loadPlugins();
        } catch (err) {
            showAlertModal('Error', 'Error deleting plugin: ' + err.message);
        }
    });
}
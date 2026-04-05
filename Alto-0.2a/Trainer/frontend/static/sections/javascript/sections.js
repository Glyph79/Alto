// ========== Sections State ==========
let sectionCards = [];

window.loadSections = async function() {
    if (!window.currentModel) return;
    await window.loadGroupsAndSections();
    renderSectionsGrid();
};

function renderSectionsGrid() {
    const container = document.getElementById('sectionsGridContainer');
    if (!container) return;

    const counts = {};
    window.groups.forEach(g => {
        const section = g.section || 'Uncategorized';
        counts[section] = (counts[section] || 0) + 1;
    });

    let sectionsList = [...window.sections];
    if (counts['Uncategorized'] && !sectionsList.includes('Uncategorized')) {
        sectionsList.push('Uncategorized');
    }

    if (sectionsList.length === 0) {
        container.innerHTML = '<div class="empty-state">No sections defined.</div>';
        sectionCards = [];
        if (window.sectionsManager) window.sectionsManager.setCardArray([]);
        return;
    }

    let html = '<div class="sections-grid grid">';
    sectionsList.forEach(section => {
        const count = counts[section] || 0;
        const hue = (section.split('').reduce((acc, char) => acc + char.charCodeAt(0), 0) * 7) % 360;
        html += `
            <div class="section-card" data-section="${escapeHtml(section)}" data-count="${count}">
                <div class="header">
                    <div style="display: flex; align-items: center; gap: 4px;">
                        <span class="section-color-dot" style="background-color: hsl(${hue}, 70%, 60%);"></span>
                        <span class="section-name">${escapeHtml(section)}</span>
                    </div>
                    <div class="card-actions">
                        <button class="edit-section" data-section="${escapeHtml(section)}" title="Edit">✎</button>
                        ${section !== 'Uncategorized' ? `<button class="delete-section" data-section="${escapeHtml(section)}" title="Delete">🗑</button>` : ''}
                    </div>
                </div>
                <div class="stats">
                    <span>📁 ${count} group${count !== 1 ? 's' : ''}</span>
                </div>
            </div>
        `;
    });
    html += '</div>';
    container.innerHTML = html;

    if (window.sectionsManager) {
        window.sectionsManager.grid = container.querySelector('.grid') || container;
    }

    // Event delegation – single listener for all section cards
    container.addEventListener('click', (e) => {
        const card = e.target.closest('.section-card');
        if (!card) return;
        const section = card.dataset.section;
        if (e.target.closest('.edit-section')) {
            editSection(section);
        } else if (e.target.closest('.delete-section')) {
            deleteSection(section);
        } else {
            editSection(section);
        }
    });

    sectionCards = Array.from(document.querySelectorAll('.section-card')).map(card => ({
        element: card,
        item: {
            section: card.dataset.section,
            count: parseInt(card.dataset.count, 10)
        }
    }));

    if (!window.sectionsManager) {
        window.sectionsManager = new window.SearchManager({
            containerId: 'sectionsGridContainer',
            cardArray: sectionCards,
            searchInputId: 'sectionSearch',
            searchFields: ['section'],
            filterSelectors: {},
            sortSelectors: {
                'name-asc': (a, b) => a.section.localeCompare(b.section),
                'name-desc': (a, b) => b.section.localeCompare(a.section),
                'groups-desc': (a, b) => b.count - a.count,
                'groups-asc': (a, b) => a.count - b.count
            },
            defaultSort: 'name-asc'
        });
    } else {
        window.sectionsManager.setCardArray(sectionCards);
    }
}

function addSection() {
    window.showSimpleModal('Add Section', [{ name: 'section', label: 'Section Name', value: '' }], async (vals, errorDiv) => {
        const name = vals.section.trim();
        if (!name) {
            errorDiv.textContent = 'Section name cannot be empty.';
            errorDiv.style.display = 'block';
            return;
        }
        if (name.toLowerCase() === 'uncategorized') {
            errorDiv.textContent = '"Uncategorized" is a reserved name.';
            errorDiv.style.display = 'block';
            return;
        }
        try {
            await window.apiPost(`/api/models/${window.currentModel}/sections`, { section: name });
            await window.loadSections();
        } catch (err) {
            errorDiv.textContent = err.message;
            errorDiv.style.display = 'block';
        }
    }, 'Add');
}

async function editSection(sectionName) {
    const modal = document.getElementById('simpleModal');
    const content = document.getElementById('simpleModalContent');

    const groupsInSection = window.groups.filter(g => (g.section || 'Uncategorized') === sectionName);

    let groupsHtml = '';
    if (groupsInSection.length === 0) {
        groupsHtml = '<li class="section-group-item" style="justify-content:center; color:#888;">No groups in this section</li>';
    } else {
        groupsInSection.forEach((g) => {
            groupsHtml += `
                <li class="section-group-item" data-group-id="${g.id}">
                    <span class="group-name">${escapeHtml(g.group_name || 'Unnamed')}</span>
                    <div class="section-group-actions">
                        <button class="edit-group-from-section" data-group-id="${g.id}" title="Edit Group">✎</button>
                        <button class="delete-group-from-section" data-group-id="${g.id}" title="Delete Group">🗑</button>
                    </div>
                </li>
            `;
        });
    }

    const isUncategorized = sectionName === 'Uncategorized';
    content.innerHTML = `
        <h2>${isUncategorized ? 'View Section' : 'Edit Section'}</h2>
        <div class="form-row">
            <label>Section Name</label>
            <input type="text" id="editSectionName" value="${escapeHtml(sectionName)}" ${isUncategorized ? 'disabled' : ''}>
        </div>
        <div class="form-row">
            <label>Groups in this section</label>
            <ul class="section-group-list">${groupsHtml}</ul>
        </div>
        <div class="modal-actions">
            <button class="cancel" id="editSectionCancelBtn">Close</button>
            ${!isUncategorized ? '<button class="save" id="editSectionSaveBtn">Save</button>' : ''}
        </div>
    `;
    window.pushModal('simpleModal');

    // Attach group action listeners
    document.querySelectorAll('.edit-group-from-section').forEach(btn => {
        btn.addEventListener('click', async (e) => {
            e.stopPropagation();
            const groupId = parseInt(btn.dataset.groupId);
            if (groupId) {
                const index = window.groups.findIndex(g => g.id == groupId);
                if (index !== -1) {
                    window.openGroupModal(index, () => editSection(sectionName));
                } else {
                    const modalContent = document.querySelector('#simpleModal .modal-content');
                    window.showSimpleRetry(modalContent, 'Group not found', () => {});
                }
            }
        });
    });

    document.querySelectorAll('.delete-group-from-section').forEach(btn => {
        btn.addEventListener('click', async (e) => {
            e.stopPropagation();
            const groupId = parseInt(btn.dataset.groupId);
            if (groupId) {
                window.showConfirmModal('Delete this group?', async () => {
                    const index = window.groups.findIndex(g => g.id == groupId);
                    if (index !== -1) {
                        try {
                            await window.apiDelete(`/api/models/${window.currentModel}/groups/${index}`);
                            await window.loadGroupsAndSections();
                            window.popModal();
                            window.popModal();
                            editSection(sectionName);
                        } catch (err) {
                            const modalContent = document.querySelector('#simpleModal .modal-content');
                            window.showSimpleRetry(modalContent, `Failed to delete group: ${err.message}`, async () => {
                                await window.apiDelete(`/api/models/${window.currentModel}/groups/${index}`);
                                await window.loadGroupsAndSections();
                                window.popModal();
                                window.popModal();
                                editSection(sectionName);
                            });
                        }
                    } else {
                        const modalContent = document.querySelector('#simpleModal .modal-content');
                        window.showSimpleRetry(modalContent, 'Group not found', () => {});
                    }
                });
            }
        });
    });

    document.getElementById('editSectionCancelBtn').onclick = () => window.popModal();

    if (!isUncategorized) {
        document.getElementById('editSectionSaveBtn').onclick = async () => {
            const newName = document.getElementById('editSectionName').value.trim();
            if (!newName) {
                const modalContent = document.querySelector('#simpleModal .modal-content');
                window.showSimpleRetry(modalContent, 'Section name cannot be empty.', () => {});
                return;
            }
            if (newName.toLowerCase() === 'uncategorized') {
                const modalContent = document.querySelector('#simpleModal .modal-content');
                window.showSimpleRetry(modalContent, '"Uncategorized" is a reserved name.', () => {});
                return;
            }
            if (newName === sectionName) {
                window.popModal();
                return;
            }
            try {
                await window.apiPut(`/api/models/${window.currentModel}/sections/${sectionName}`, { new_name: newName });
                await window.loadSections();
                window.popModal();
            } catch (err) {
                const modalContent = document.querySelector('#simpleModal .modal-content');
                window.showSimpleRetry(modalContent, `Failed to rename section: ${err.message}`, async () => {
                    await window.apiPut(`/api/models/${window.currentModel}/sections/${sectionName}`, { new_name: newName });
                    await window.loadSections();
                    window.popModal();
                });
            }
        };
    }
}

async function deleteSection(section) {
    if (section === 'Uncategorized') {
        const container = document.getElementById('sectionsGridContainer');
        window.showSimpleRetry(container, 'The "Uncategorized" pseudo‑section cannot be deleted.', () => {});
        return;
    }

    const groupsUsing = window.groups.filter(g => g.section === section).length;
    const message = groupsUsing > 0 
        ? `Section "${section}" is used by ${groupsUsing} group(s).` 
        : `Delete section "${section}"?`;

    const otherSections = window.sections.filter(s => s !== section);
    const hasOtherSections = otherSections.length > 0;

    const modal = document.getElementById('simpleModal');
    const content = document.getElementById('simpleModalContent');
    content.innerHTML = `
        <h2>Delete Section</h2>
        <p class="delete-message">${escapeHtml(message)}</p>
        ${groupsUsing > 0 ? `
        <div class="delete-section-options">
            ${hasOtherSections ? `
            <div class="option-row">
                <input type="radio" name="deleteAction" value="move" id="moveRadio" checked>
                <label for="moveRadio">Move groups to:</label>
                <select id="moveTarget" class="compact-select">
                    ${otherSections.map(s => `<option value="${escapeHtml(s)}">${escapeHtml(s)}</option>`).join('')}
                </select>
            </div>
            ` : ''}
            <div class="option-row">
                <input type="radio" name="deleteAction" value="uncategorized" id="uncatRadio" ${!hasOtherSections ? 'checked' : ''}>
                <label for="uncatRadio">Move groups to Uncategorized</label>
            </div>
            <div class="option-row">
                <input type="radio" name="deleteAction" value="delete" id="deleteRadio">
                <label for="deleteRadio">Delete all groups using this section</label>
            </div>
        </div>
        ` : ''}
        <div class="modal-actions">
            <button class="cancel" id="deleteCancelBtn">Cancel</button>
            <button class="save" id="deleteConfirmBtn">Delete</button>
        </div>
    `;
    window.pushModal('simpleModal');

    document.getElementById('deleteCancelBtn').onclick = () => window.popModal();
    document.getElementById('deleteConfirmBtn').onclick = async () => {
        let action = 'uncategorized';
        let target = null;
        if (groupsUsing > 0) {
            action = document.querySelector('input[name="deleteAction"]:checked').value;
            if (action === 'move') target = document.getElementById('moveTarget').value;
        }
        try {
            let url = `/api/models/${window.currentModel}/sections/${section}?action=${action}`;
            if (target !== null) url += `&target=${target}`;
            await window.apiDelete(url);
            await window.loadSections();
            window.popModal();
        } catch (err) {
            const modalContent = document.querySelector('#simpleModal .modal-content');
            window.showSimpleRetry(modalContent, `Failed to delete section: ${err.message}`, async () => {
                await deleteSection(section);
            });
        }
    };
}

document.getElementById('addSectionBtn').addEventListener('click', addSection);
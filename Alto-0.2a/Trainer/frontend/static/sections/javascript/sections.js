// sections.js - using GridRenderer
let sectionsGrid = null;

window.loadSections = async function() {
    if (!window.currentModel) return;
    await window.loadGroupsAndSections(); // ensures window.groups is fresh
    renderSectionsGrid();
};

function renderSectionsGrid() {
    const counts = {};
    window.groups.forEach(g => {
        const section = g.section || 'Uncategorized';
        counts[section] = (counts[section] || 0) + 1;
    });

    let sectionsList = [...window.sections];
    if (counts['Uncategorized'] && !sectionsList.includes('Uncategorized')) {
        sectionsList.push('Uncategorized');
    }

    const sectionItems = sectionsList.map(section => ({
        section: section,
        count: counts[section] || 0,
        isUncategorized: section === 'Uncategorized'
    }));

    if (!sectionsGrid) {
        sectionsGrid = new GridRenderer({
            containerId: 'sectionsGridContainer',
            items: sectionItems,
            renderItem: (item, idx) => {
                const hue = (item.section.split('').reduce((acc, char) => acc + char.charCodeAt(0), 0) * 7) % 360;
                return `
                    <div class="section-card" data-card-index="${idx}" data-section="${escapeHtml(item.section)}">
                        <div class="header">
                            <div style="display: flex; align-items: center; gap: 4px;">
                                <span class="section-color-dot" style="background-color: hsl(${hue}, 70%, 60%);"></span>
                                <span class="section-name">${escapeHtml(item.section)}</span>
                            </div>
                            <div class="card-actions">
                                <button class="card-edit" data-section="${escapeHtml(item.section)}" title="Edit">✎</button>
                                ${!item.isUncategorized ? `<button class="card-delete" data-section="${escapeHtml(item.section)}" title="Delete">🗑</button>` : ''}
                            </div>
                        </div>
                        <div class="stats">
                            <span>📁 ${item.count} group${item.count !== 1 ? 's' : ''}</span>
                        </div>
                    </div>
                `;
            },
            options: {
                searchInputId: 'sectionSearch',
                searchFields: ['section'],
                sortSelectors: {
                    'name-asc': (a, b) => a.section.localeCompare(b.section),
                    'name-desc': (a, b) => b.section.localeCompare(a.section),
                    'groups-desc': (a, b) => b.count - a.count,
                    'groups-asc': (a, b) => a.count - b.count
                },
                defaultSort: 'name-asc',
                emptyStateHtml: '<div class="empty-state">No sections defined.</div>',
                onCardClick: (item) => editSection(item.section),
                onCardEdit: (item) => editSection(item.section),
                onCardDelete: (item) => deleteSection(item.section)
            }
        });
    } else {
        sectionsGrid.setItems(sectionItems);
    }

    document.getElementById('sectionSearch').disabled = false;
    document.getElementById('sectionSort').disabled = false;
    document.getElementById('addSectionBtn').disabled = false;
}

function clearSections() {
    if (sectionsGrid) sectionsGrid.destroy();
    sectionsGrid = null;
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
            resetSectionsFilters();
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
                resetSectionsFilters();
                await window.loadSections();
                window.popModal();
            } catch (err) {
                const modalContent = document.querySelector('#simpleModal .modal-content');
                window.showSimpleRetry(modalContent, `Failed to rename section: ${err.message}`, async () => {
                    await window.apiPut(`/api/models/${window.currentModel}/sections/${sectionName}`, { new_name: newName });
                    resetSectionsFilters();
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
            resetSectionsFilters();
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

function resetSectionsFilters() {
    const search = document.getElementById('sectionSearch');
    if (search) search.value = '';
    const sort = document.getElementById('sectionSort');
    if (sort) sort.value = 'name-asc';
    if (search) search.dispatchEvent(new Event('input', { bubbles: true }));
    if (sort) sort.dispatchEvent(new Event('change', { bubbles: true }));
}

document.getElementById('addSectionBtn').addEventListener('click', addSection);
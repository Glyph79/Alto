// topics.js - using GridRenderer
let topicsGrid = null;
window.topicsList = [];

window.loadTopics = async function() {
    if (!window.currentModel) return;
    try {
        window.topicsList = await window.apiGet(`/api/models/${window.currentModel}/topics`);
        renderTopicsGrid();
        if (typeof window.refreshGroupModalTopicDropdown === 'function') {
            window.refreshGroupModalTopicDropdown();
        }
        populateTopicSectionFilter();
    } catch (err) {
        const container = document.getElementById('topicsGridContainer');
        window.showSimpleRetry(container, `Error loading topics: ${err.message}`, async () => {
            await window.loadTopics();
        });
    }
};

function populateTopicSectionFilter() {
    const select = document.getElementById('topicSectionFilter');
    select.innerHTML = '<option value="All Sections">All Sections</option>';
    window.sections.forEach(s => {
        const opt = document.createElement('option');
        opt.value = s;
        opt.textContent = s;
        select.appendChild(opt);
    });
}

function renderTopicsGrid() {
    const groupCounts = {};
    if (window.groups && window.groups.length) {
        window.groups.forEach(g => {
            const topic = g.topic;
            if (topic) groupCounts[topic] = (groupCounts[topic] || 0) + 1;
        });
    }
    const noTopicCount = window.groups ? window.groups.filter(g => !g.topic).length : 0;

    let topicItems = [];
    // Add the special "(No Topic)" pseudo-item
    topicItems.push({
        topic: '(No Topic)',
        count: noTopicCount,
        isNoTopic: true
    });
    window.topicsList.forEach(topic => {
        topicItems.push({
            topic: topic,
            count: groupCounts[topic] || 0,
            isNoTopic: false
        });
    });

    if (!topicsGrid) {
        topicsGrid = new GridRenderer({
            containerId: 'topicsGridContainer',
            items: topicItems,
            renderItem: (item, idx) => {
                const hue = item.isNoTopic ? 0 : (item.topic.split('').reduce((acc, char) => acc + char.charCodeAt(0), 0) * 7) % 360;
                return `
                    <div class="topic-card" data-card-index="${idx}" data-topic="${escapeHtml(item.topic)}">
                        <div class="header">
                            <div style="display: flex; align-items: center; gap: 4px;">
                                <span class="topic-color-dot" style="background-color: ${item.isNoTopic ? '#888' : `hsl(${hue}, 70%, 60%)`};"></span>
                                <span class="topic-name">${escapeHtml(item.topic)}</span>
                            </div>
                            <div class="card-actions">
                                <button class="card-edit" data-topic="${escapeHtml(item.topic)}" title="Edit">✎</button>
                                ${!item.isNoTopic ? `<button class="card-delete" data-topic="${escapeHtml(item.topic)}" title="Delete">🗑</button>` : ''}
                            </div>
                        </div>
                        <div class="stats">
                            <span>📊 ${item.count} group${item.count !== 1 ? 's' : ''}</span>
                        </div>
                    </div>
                `;
            },
            options: {
                searchInputId: 'topicSearch',
                searchFields: ['topic'],
                filterSelectors: {
                    'topicSectionFilter': (item, value) => {
                        if (value === 'All Sections') return true;
                        if (item.isNoTopic) return true;
                        const groupsForTopic = window.groups.filter(g => g.topic === item.topic);
                        if (groupsForTopic.length === 0) return false;
                        const sections = new Set(groupsForTopic.map(g => g.section).filter(s => s));
                        return sections.has(value);
                    },
                    'topicFilter': (item, value) => {
                        if (value === 'all') return true;
                        if (value === 'used') return item.count > 0;
                        if (value === 'unused') return item.count === 0;
                        return true;
                    }
                },
                sortSelectors: {
                    'name-asc': (a, b) => {
                        if (a.isNoTopic) return -1;
                        if (b.isNoTopic) return 1;
                        return a.topic.localeCompare(b.topic);
                    },
                    'name-desc': (a, b) => {
                        if (a.isNoTopic) return -1;
                        if (b.isNoTopic) return 1;
                        return b.topic.localeCompare(a.topic);
                    },
                    'usage-desc': (a, b) => b.count - a.count,
                    'usage-asc': (a, b) => a.count - b.count
                },
                defaultSort: 'name-asc',
                emptyStateHtml: '<div class="empty-state">No topics found.</div>',
                onCardClick: (item) => editTopic(item.topic),
                onCardEdit: (item) => editTopic(item.topic),
                onCardDelete: (item) => deleteTopic(item.topic)
            }
        });
    } else {
        topicsGrid.setItems(topicItems);
    }

    document.getElementById('topicSearch').disabled = false;
    document.getElementById('topicSectionFilter').disabled = false;
    document.getElementById('topicFilter').disabled = false;
    document.getElementById('topicSort').disabled = false;
    document.getElementById('addTopicBtn').disabled = false;
}

window.clearTopics = function() {
    if (topicsGrid) topicsGrid.destroy();
    topicsGrid = null;
    window.topicsList = [];
    const container = document.getElementById('topicsGridContainer');
    if (container) container.innerHTML = '';
};

function addTopic() {
    window.showSimpleModal('Add Topic', [{ name: 'topic', label: 'Topic Name', value: '' }], async (vals, errorDiv) => {
        const name = vals.topic.trim();
        if (!name) {
            errorDiv.textContent = 'Topic name cannot be empty.';
            errorDiv.style.display = 'block';
            return;
        }
        if (name.toLowerCase() === 'null' || name === '(No Topic)') {
            errorDiv.textContent = `"${name}" is a reserved name.`;
            errorDiv.style.display = 'block';
            return;
        }
        try {
            await window.apiPost(`/api/models/${window.currentModel}/topics`, { topic: name });
            resetTopicsFilters();
            await window.loadTopics();
        } catch (err) {
            errorDiv.textContent = err.message;
            errorDiv.style.display = 'block';
        }
    }, 'Add');
}

async function editTopic(topicName) {
    const isNoTopic = topicName === '(No Topic)';
    const modal = document.getElementById('simpleModal');
    const content = document.getElementById('simpleModalContent');

    content.innerHTML = `
        <h2>${isNoTopic ? 'View Topic' : 'Edit Topic'}</h2>
        <div class="form-row">
            <label>Topic Name</label>
            <input type="text" id="editTopicName" value="${escapeHtml(topicName)}" ${isNoTopic ? 'disabled' : ''}>
        </div>
        ${!isNoTopic ? `
        <div class="form-row">
            <label>Section</label>
            <select id="editTopicSection">
                <option value="">(Uncategorized)</option>
                ${window.sections.map(s => `<option value="${escapeHtml(s)}">${escapeHtml(s)}</option>`).join('')}
            </select>
        </div>
        ` : ''}
        <div class="form-row">
            <label>Groups using this topic</label>
            <ul class="group-usage-list" id="topicGroupList"></ul>
        </div>
        <div class="modal-actions">
            <button class="cancel" id="editTopicCancelBtn">Close</button>
            ${!isNoTopic ? '<button class="save" id="editTopicSaveBtn">Save</button>' : ''}
        </div>
    `;
    window.pushModal('simpleModal');

    if (!isNoTopic) {
        document.getElementById('editTopicSaveBtn').disabled = true;
    }

    let currentTopicFetchCleanup = null;
    const groupList = document.getElementById('topicGroupList');
    currentTopicFetchCleanup = window.showInlineLoading(groupList, "Loading groups");

    try {
        let groupsUsing = [];
        if (isNoTopic) {
            groupsUsing = window.groups.filter(g => !g.topic);
        } else {
            const result = await window.retryOperation(async () => {
                return await window.apiGet(`/api/models/${window.currentModel}/topics/${topicName}/groups`);
            });
            groupsUsing = result.groups || [];
        }

        if (currentTopicFetchCleanup) currentTopicFetchCleanup.clear();

        let groupsHtml = '';
        if (groupsUsing.length === 0) {
            groupsHtml = '<li class="group-usage-item" style="justify-content:center; color:#888;">No groups use this topic</li>';
        } else {
            groupsUsing.forEach((g) => {
                groupsHtml += `
                    <li class="group-usage-item" data-group-id="${g.id}">
                        <span class="group-name">${escapeHtml(g.group_name || 'Unnamed')}</span>
                        <div class="group-usage-actions">
                            <button class="edit-group-from-topic" data-group-id="${g.id}" title="Edit Group">✎</button>
                            <button class="delete-group-from-topic" data-group-id="${g.id}" title="Delete Group">🗑</button>
                        </div>
                    </li>
                `;
            });
        }
        groupList.innerHTML = groupsHtml;
        attachGroupHandlers(groupsUsing, topicName);

        document.getElementById('editTopicCancelBtn').onclick = () => window.popModal();
        if (!isNoTopic) {
            document.getElementById('editTopicSaveBtn').disabled = false;
            document.getElementById('editTopicSaveBtn').onclick = async () => {
                const newName = document.getElementById('editTopicName').value.trim();
                if (!newName) {
                    const modalContent = document.querySelector('#simpleModal .modal-content');
                    window.showSimpleRetry(modalContent, 'Topic name cannot be empty.', () => {});
                    return;
                }
                if (newName.toLowerCase() === 'null' || newName === '(No Topic)') {
                    const modalContent = document.querySelector('#simpleModal .modal-content');
                    window.showSimpleRetry(modalContent, `"${newName}" is a reserved name.`, () => {});
                    return;
                }
                if (newName === topicName) {
                    window.popModal();
                    return;
                }
                try {
                    await window.retryOperation(async () => {
                        await window.apiPut(`/api/models/${window.currentModel}/topics/${topicName}`, { new_name: newName });
                    });
                    resetTopicsFilters();
                    await window.loadTopics();
                    window.popModal();
                } catch (err) {
                    const modalContent = document.querySelector('#simpleModal .modal-content');
                    window.showSimpleRetry(modalContent, `Failed to rename topic: ${err.message}`, async () => {
                        await window.apiPut(`/api/models/${window.currentModel}/topics/${topicName}`, { new_name: newName });
                        resetTopicsFilters();
                        await window.loadTopics();
                        window.popModal();
                    });
                }
            };
        }
    } catch (err) {
        if (currentTopicFetchCleanup) currentTopicFetchCleanup.clear();
        window.showInlineListRetry(groupList, 'groups', async () => {
            await editTopic(topicName);
        });
        if (!isNoTopic) {
            document.getElementById('editTopicSaveBtn').disabled = true;
        }
    }

    function attachGroupHandlers(groups, topic) {
        document.querySelectorAll('.edit-group-from-topic').forEach(btn => {
            btn.addEventListener('click', async (e) => {
                e.stopPropagation();
                const groupId = parseInt(btn.dataset.groupId);
                if (groupId) {
                    if (!window.groups || window.groups.length === 0) await window.loadGroupsAndSections();
                    const index = window.groups.findIndex(g => g.id == groupId);
                    if (index !== -1) {
                        window.openGroupModal(index, () => editTopic(topic));
                    } else {
                        const modalContent = document.querySelector('#simpleModal .modal-content');
                        window.showSimpleRetry(modalContent, 'Group not found', () => {});
                    }
                }
            });
        });

        document.querySelectorAll('.delete-group-from-topic').forEach(btn => {
            btn.addEventListener('click', async (e) => {
                e.stopPropagation();
                const groupId = parseInt(btn.dataset.groupId);
                if (groupId) {
                    window.showConfirmModal('Delete this group?', async () => {
                        if (!window.groups || window.groups.length === 0) await window.loadGroupsAndSections();
                        const index = window.groups.findIndex(g => g.id == groupId);
                        if (index !== -1) {
                            try {
                                await window.apiDelete(`/api/models/${window.currentModel}/groups/${index}`);
                                await editTopic(topic);
                            } catch (err) {
                                const modalContent = document.querySelector('#simpleModal .modal-content');
                                window.showSimpleRetry(modalContent, `Failed to delete group: ${err.message}`, async () => {
                                    await window.apiDelete(`/api/models/${window.currentModel}/groups/${index}`);
                                    await editTopic(topic);
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
    }
}

function deleteTopic(topic) {
    if (topic === '(No Topic)') {
        const container = document.getElementById('topicsGridContainer');
        window.showSimpleRetry(container, 'The "(No Topic)" pseudo‑topic cannot be deleted.', () => {});
        return;
    }

    let groupsUsing = 0;
    if (window.groups && window.groups.length) {
        groupsUsing = window.groups.filter(g => g.topic === topic).length;
    }

    let message = `Delete topic "${topic}"?`;
    if (groupsUsing > 0) {
        message = `Topic "${topic}" is used by ${groupsUsing} group(s).`;
    }

    const otherTopics = window.topicsList.filter(t => t !== topic);
    let reassignOptions = '<option value="">(No Topic)</option>';
    reassignOptions += otherTopics.map(t => `<option value="${escapeHtml(t)}">${escapeHtml(t)}</option>`).join('');

    const modal = document.getElementById('simpleModal');
    const content = document.getElementById('simpleModalContent');
    content.innerHTML = `
        <h2>Delete Topic</h2>
        <p style="margin: 20px 0; color: #ccc;">${escapeHtml(message)}</p>
        ${groupsUsing > 0 ? `
        <div style="margin: 20px 0;">
            <label>
                <input type="radio" name="deleteAction" value="reassign" checked>
                Reassign groups to:
                <select id="reassignTarget">
                    ${reassignOptions}
                </select>
            </label>
            <br><br>
            <label>
                <input type="radio" name="deleteAction" value="delete_groups">
                Delete all groups using this topic
            </label>
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
        if (groupsUsing > 0) {
            const action = document.querySelector('input[name="deleteAction"]:checked').value;
            let target = null;
            if (action === 'reassign') {
                target = document.getElementById('reassignTarget').value;
            }
            try {
                let url = `/api/models/${window.currentModel}/topics/${topic}?action=${action}`;
                if (target !== null) url += `&target=${target}`;
                await window.apiDelete(url);
                resetTopicsFilters();
                await window.loadTopics();
                window.popModal();
            } catch (err) {
                const modalContent = document.querySelector('#simpleModal .modal-content');
                window.showSimpleRetry(modalContent, `Failed to delete topic: ${err.message}`, async () => {
                    await deleteTopic(topic);
                });
            }
        } else {
            try {
                await window.apiDelete(`/api/models/${window.currentModel}/topics/${topic}?action=reassign&target=`);
                resetTopicsFilters();
                await window.loadTopics();
                window.popModal();
            } catch (err) {
                const modalContent = document.querySelector('#simpleModal .modal-content');
                window.showSimpleRetry(modalContent, `Failed to delete topic: ${err.message}`, async () => {
                    await deleteTopic(topic);
                });
            }
        }
    };
}

function resetTopicsFilters() {
    const search = document.getElementById('topicSearch');
    if (search) search.value = '';
    const sectionFilter = document.getElementById('topicSectionFilter');
    if (sectionFilter) sectionFilter.value = 'All Sections';
    const usageFilter = document.getElementById('topicFilter');
    if (usageFilter) usageFilter.value = 'all';
    const sort = document.getElementById('topicSort');
    if (sort) sort.value = 'name-asc';
    if (search) search.dispatchEvent(new Event('input', { bubbles: true }));
    if (sectionFilter) sectionFilter.dispatchEvent(new Event('change', { bubbles: true }));
    if (usageFilter) usageFilter.dispatchEvent(new Event('change', { bubbles: true }));
    if (sort) sort.dispatchEvent(new Event('change', { bubbles: true }));
}

document.getElementById('addTopicBtn').addEventListener('click', addTopic);
// ========== Topics State ==========
window.topicsList = [];
let topicCards = [];
let topicsSectionFilter = 'All Sections';
let currentTopicFetchCleanup = null;

const NO_TOPIC = '(No Topic)';

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
        console.error('Error loading topics:', err);
        const container = document.getElementById('topicsGridContainer');
        window.showSimpleRetry(container, `Error loading topics: ${err.message}`, async () => {
            await window.loadTopics();
        });
    }
};

window.clearTopics = function() {
    window.topicsList = [];
    const container = document.getElementById('topicsGridContainer');
    if (container) container.innerHTML = '';
    document.getElementById('topicSearch').disabled = true;
    document.getElementById('topicSectionFilter').disabled = true;
    document.getElementById('topicFilter').disabled = true;
    document.getElementById('topicSort').disabled = true;
    document.getElementById('addTopicBtn').disabled = true;
    if (window.topicsManager) window.topicsManager.setCardArray([]);
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
    select.value = topicsSectionFilter;
}

function renderTopicsGrid() {
    const container = document.getElementById('topicsGridContainer');
    if (!container) return;

    const groupCounts = {};
    if (window.groups && window.groups.length) {
        window.groups.forEach(g => {
            const topic = g.topic;
            if (topic) groupCounts[topic] = (groupCounts[topic] || 0) + 1;
        });
    }
    const noTopicCount = window.groups ? window.groups.filter(g => !g.topic).length : 0;

    let html = '<div class="topics-grid grid">';

    html += `
        <div class="topic-card" data-topic="${NO_TOPIC}" data-count="${noTopicCount}" data-is-no-topic="true">
            <div class="header">
                <div style="display: flex; align-items: center; gap: 4px;">
                    <span class="topic-color-dot" style="background-color: #888;"></span>
                    <span class="topic-name">${NO_TOPIC}</span>
                </div>
                <div class="card-actions">
                    <button class="edit-topic" data-topic="${NO_TOPIC}" title="Edit">✎</button>
                </div>
            </div>
            <div class="stats">
                <span>📊 ${noTopicCount} group${noTopicCount !== 1 ? 's' : ''}</span>
            </div>
        </div>
    `;

    window.topicsList.forEach(topic => {
        const count = groupCounts[topic] || 0;
        const hue = (topic.split('').reduce((acc, char) => acc + char.charCodeAt(0), 0) * 7) % 360;
        html += `
            <div class="topic-card" data-topic="${topic}" data-count="${count}">
                <div class="header">
                    <div style="display: flex; align-items: center; gap: 4px;">
                        <span class="topic-color-dot" style="background-color: hsl(${hue}, 70%, 60%);"></span>
                        <span class="topic-name">${topic}</span>
                    </div>
                    <div class="card-actions">
                        <button class="edit-topic" data-topic="${topic}" title="Edit">✎</button>
                        <button class="delete-topic" data-topic="${topic}" title="Delete">🗑</button>
                    </div>
                </div>
                <div class="stats">
                    <span>📊 ${count} group${count !== 1 ? 's' : ''}</span>
                </div>
            </div>
        `;
    });
    html += '</div>';
    container.innerHTML = html;

    if (window.topicsManager) {
        window.topicsManager.grid = container.querySelector('.grid') || container;
    }

    document.querySelectorAll('.topic-card').forEach(card => {
        card.addEventListener('click', (e) => {
            if (e.target.closest('.card-actions')) return;
            editTopic(card.dataset.topic);
        });
    });

    document.querySelectorAll('.edit-topic').forEach(btn => {
        btn.addEventListener('click', (e) => {
            e.stopPropagation();
            editTopic(btn.dataset.topic);
        });
    });
    document.querySelectorAll('.delete-topic').forEach(btn => {
        btn.addEventListener('click', (e) => {
            e.stopPropagation();
            deleteTopic(btn.dataset.topic);
        });
    });

    topicCards = Array.from(document.querySelectorAll('.topic-card')).map(card => ({
        element: card,
        item: {
            topic: card.dataset.topic,
            count: parseInt(card.dataset.count, 10),
            isNoTopic: card.dataset.isNoTopic === 'true'
        }
    }));

    document.getElementById('topicSearch').disabled = false;
    document.getElementById('topicSectionFilter').disabled = false;
    document.getElementById('topicFilter').disabled = false;
    document.getElementById('topicSort').disabled = false;
    document.getElementById('addTopicBtn').disabled = false;

    if (!window.topicsManager) {
        window.topicsManager = new window.SearchManager({
            containerId: 'topicsGridContainer',
            cardArray: topicCards,
            searchInputId: 'topicSearch',
            searchFields: ['topic'],
            filterSelectors: {
                'topicSectionFilter': (item, value) => {
                    if (value === 'All Sections') return true;
                    if (item.isNoTopic) return true;
                    if (!window.groups) return true;
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
            defaultSort: 'name-asc'
        });
    } else {
        window.topicsManager.setCardArray(topicCards);
    }
}

function addTopic() {
    window.showSimpleModal('Add Topic', [{ name: 'topic', label: 'Topic Name', value: '' }], async (vals, errorDiv) => {
        const name = vals.topic.trim();
        if (!name) {
            errorDiv.textContent = 'Topic name cannot be empty.';
            errorDiv.style.display = 'block';
            return;
        }
        if (name.toLowerCase() === 'null' || name === NO_TOPIC) {
            errorDiv.textContent = `"${name}" is a reserved name.`;
            errorDiv.style.display = 'block';
            return;
        }
        try {
            await window.apiPost(`/api/models/${window.currentModel}/topics`, { topic: name });
            await window.loadTopics();
        } catch (err) {
            errorDiv.textContent = err.message;
            errorDiv.style.display = 'block';
        }
    }, 'Add');
}

async function editTopic(topicName) {
    const isNoTopic = topicName === NO_TOPIC;
    const modal = document.getElementById('simpleModal');
    const content = document.getElementById('simpleModalContent');

    content.innerHTML = `
        <h2>${isNoTopic ? 'View Topic' : 'Edit Topic'}</h2>
        <div class="form-row">
            <label>Topic Name</label>
            <input type="text" id="editTopicName" value="${topicName}" ${isNoTopic ? 'disabled' : ''}>
        </div>
        ${!isNoTopic ? `
        <div class="form-row">
            <label>Section</label>
            <select id="editTopicSection">
                <option value="">(Uncategorized)</option>
                ${window.sections.map(s => `<option value="${s}">${s}</option>`).join('')}
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

    if (currentTopicFetchCleanup) currentTopicFetchCleanup.clear();

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
                        <span class="group-name">${g.group_name || 'Unnamed'}</span>
                        <div class="group-usage-actions">
                            <button class="edit-group-from-topic" title="Edit Group">✎</button>
                            <button class="delete-group-from-topic" title="Delete Group">🗑</button>
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
                if (newName.toLowerCase() === 'null' || newName === NO_TOPIC) {
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
                    await window.loadTopics();
                    window.popModal();
                } catch (err) {
                    const modalContent = document.querySelector('#simpleModal .modal-content');
                    window.showSimpleRetry(modalContent, `Failed to rename topic: ${err.message}`, async () => {
                        await window.apiPut(`/api/models/${window.currentModel}/topics/${topicName}`, { new_name: newName });
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
                const li = e.target.closest('.group-usage-item');
                const groupId = li.dataset.groupId;
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
                const li = e.target.closest('.group-usage-item');
                const groupId = li.dataset.groupId;
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
    if (topic === NO_TOPIC) {
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
    reassignOptions += otherTopics.map(t => `<option value="${t}">${t}</option>`).join('');

    const modal = document.getElementById('simpleModal');
    const content = document.getElementById('simpleModalContent');
    content.innerHTML = `
        <h2>Delete Topic</h2>
        <p style="margin: 20px 0; color: #ccc;">${message}</p>
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

document.getElementById('addTopicBtn').addEventListener('click', addTopic);
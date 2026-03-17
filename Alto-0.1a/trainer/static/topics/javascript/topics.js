// ========== Topics State ==========
window.topicsList = [];
let topicCards = []; // Array of { element, item: { topic, count } }
let topicsSectionFilter = 'All Sections';

// ========== Load Topics ==========
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
    }
};

// ========== Clear Topics (when no model) ==========
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

    let html = '<div class="topics-grid grid">';
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

    // Attach click handlers to cards (excluding actions)
    document.querySelectorAll('.topic-card').forEach(card => {
        card.addEventListener('click', (e) => {
            if (e.target.closest('.card-actions')) return;
            const topic = card.dataset.topic;
            editTopic(topic);
        });
    });

    // Attach button handlers
    document.querySelectorAll('.edit-topic').forEach(btn => {
        btn.addEventListener('click', (e) => {
            e.stopPropagation();
            const topic = btn.dataset.topic;
            editTopic(topic);
        });
    });
    document.querySelectorAll('.delete-topic').forEach(btn => {
        btn.addEventListener('click', (e) => {
            e.stopPropagation();
            const topic = btn.dataset.topic;
            deleteTopic(topic);
        });
    });

    topicCards = Array.from(document.querySelectorAll('.topic-card')).map(card => ({
        element: card,
        item: {
            topic: card.dataset.topic,
            count: parseInt(card.dataset.count, 10)
        }
    }));

    document.getElementById('topicSearch').disabled = false;
    document.getElementById('topicSectionFilter').disabled = false;
    document.getElementById('topicFilter').disabled = false;
    document.getElementById('topicSort').disabled = false;
    document.getElementById('addTopicBtn').disabled = false;

    // Initialize or update manager
    if (!window.topicsManager) {
        window.topicsManager = new window.SearchManager({
            containerId: 'topicsGridContainer',
            cardArray: topicCards,
            searchInputId: 'topicSearch',
            searchFields: ['topic'],
            filterSelectors: {
                'topicSectionFilter': (item, value) => {
                    if (value === 'All Sections') return true;
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
                'name-asc': (a, b) => a.topic.localeCompare(b.topic),
                'name-desc': (a, b) => b.topic.localeCompare(a.topic),
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
        if (!vals.topic) {
            errorDiv.textContent = 'Topic name cannot be empty.';
            errorDiv.style.display = 'block';
            return;
        }
        if (vals.topic.toLowerCase() === 'null') {
            errorDiv.textContent = 'Topic name cannot be "null".';
            errorDiv.style.display = 'block';
            return;
        }
        try {
            await window.apiPost(`/api/models/${window.currentModel}/topics`, { topic: vals.topic });
            await window.loadTopics();
        } catch (err) {
            errorDiv.textContent = err.message;
            errorDiv.style.display = 'block';
        }
    }, 'Add');
}

// ========== Edit Topic with lazy loaded groups ==========
async function editTopic(oldName) {
    const modal = document.getElementById('simpleModal');
    const content = document.getElementById('simpleModalContent');
    content.innerHTML = `
        <h2>Edit Topic</h2>
        <div style="text-align:center; padding:20px;">Loading groups...</div>
    `;
    window.pushModal('simpleModal');

    try {
        const result = await window.apiGet(`/api/models/${window.currentModel}/topics/${oldName}/groups`);
        const groupsUsing = result.groups || [];

        let groupsHtml = '';
        if (groupsUsing.length === 0) {
            groupsHtml = '<li class="group-usage-item" style="justify-content:center; color:#888;">No groups use this topic</li>';
        } else {
            groupsUsing.forEach((g, idx) => {
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

        content.innerHTML = `
            <h2>Edit Topic</h2>
            <div class="form-row">
                <label>Topic Name</label>
                <input type="text" id="editTopicName" value="${oldName}">
            </div>
            <div class="form-row">
                <label>Used by groups</label>
                <ul class="group-usage-list">${groupsHtml}</ul>
            </div>
            <div class="modal-actions">
                <button class="cancel" id="editTopicCancelBtn">Cancel</button>
                <button class="save" id="editTopicSaveBtn">Save</button>
            </div>
        `;

        document.querySelectorAll('.edit-group-from-topic').forEach(btn => {
            btn.addEventListener('click', async (e) => {
                e.stopPropagation();
                const li = e.target.closest('.group-usage-item');
                const groupId = li.dataset.groupId;
                if (groupId) {
                    if (!window.groups || window.groups.length === 0) {
                        await window.loadGroupsAndSections();
                    }
                    const index = window.groups.findIndex(g => g.id == groupId);
                    if (index !== -1) {
                        window.openGroupModal(index, () => {});
                    } else {
                        alert('Group not found');
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
                        if (!window.groups || window.groups.length === 0) {
                            await window.loadGroupsAndSections();
                        }
                        const index = window.groups.findIndex(g => g.id == groupId);
                        if (index !== -1) {
                            await window.apiDelete(`/api/models/${window.currentModel}/groups/${index}`);
                            li.remove();
                            const currentTopicName = document.getElementById('editTopicName').value;
                            window.popModal();
                            editTopic(currentTopicName);
                        } else {
                            alert('Group not found');
                        }
                    });
                }
            });
        });

        document.getElementById('editTopicCancelBtn').onclick = () => {
            window.popModal();
        };
        document.getElementById('editTopicSaveBtn').onclick = async () => {
            const newName = document.getElementById('editTopicName').value.trim();
            if (!newName) {
                alert('Topic name cannot be empty.');
                return;
            }
            if (newName.toLowerCase() === 'null') {
                alert('Topic name cannot be "null".');
                return;
            }
            if (newName === oldName) {
                window.popModal();
                return;
            }
            try {
                await window.apiPut(`/api/models/${window.currentModel}/topics/${oldName}`, { new_name: newName });
                await window.loadTopics();
                window.popModal();
            } catch (err) {
                alert('Failed to rename topic: ' + err.message);
            }
        };
    } catch (err) {
        alert('Error loading groups for topic: ' + err.message);
        window.popModal();
    }
}

// ========== Delete Topic ==========
function deleteTopic(topic) {
    let groupsUsing = 0;
    if (window.groups && window.groups.length) {
        groupsUsing = window.groups.filter(g => g.topic === topic).length;
    } else {
        console.warn('Groups not loaded, assuming 0 groups using topic');
    }
    let message = `Delete topic "${topic}"?`;
    if (groupsUsing > 0) {
        message = `Topic "${topic}" is used by ${groupsUsing} group(s).`;
    }

    const otherTopics = window.topicsList.filter(t => t !== topic);
    let reassignOptions = '';
    if (otherTopics.length === 0) {
        reassignOptions = '<option value="">(No topic)</option>';
    } else {
        reassignOptions = otherTopics.map(t => `<option value="${t}">${t}</option>`).join('');
    }

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

    document.getElementById('deleteCancelBtn').onclick = () => {
        window.popModal();
    };
    document.getElementById('deleteConfirmBtn').onclick = async () => {
        if (groupsUsing > 0) {
            const action = document.querySelector('input[name="deleteAction"]:checked').value;
            const target = action === 'reassign' ? document.getElementById('reassignTarget').value : null;
            try {
                let url = `/api/models/${window.currentModel}/topics/${topic}?action=${action}`;
                if (target !== null) url += `&target=${target}`;
                await window.apiDelete(url);
                await window.loadTopics();
                window.popModal();
            } catch (err) {
                alert('Failed to delete topic: ' + err.message);
            }
        } else {
            try {
                await window.apiDelete(`/api/models/${window.currentModel}/topics/${topic}?action=reassign&target=`);
                await window.loadTopics();
                window.popModal();
            } catch (err) {
                alert('Failed to delete topic: ' + err.message);
            }
        }
    };
}

document.getElementById('addTopicBtn').addEventListener('click', addTopic);
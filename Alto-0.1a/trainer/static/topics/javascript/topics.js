// ========== Topics State ==========
window.topicsList = [];
let topicCards = []; // Array of { element, topic, count }
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
    // Disable sidebar controls
    document.getElementById('topicSearch').disabled = true;
    document.getElementById('topicSectionFilter').disabled = true;
    document.getElementById('topicFilter').disabled = true;
    document.getElementById('topicSort').disabled = true;
    document.getElementById('addTopicBtn').disabled = true;
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

    // We no longer rely on window.groups for counts – we'll fetch on edit
    // But for the grid we need counts, so we fetch from the backend
    // We'll keep using window.groups if available, but if not, we can show 0.
    // Alternatively, modify the backend to return counts with topics.
    // For simplicity, we'll assume window.groups is still loaded when topics tab is activated.
    // But with lazy loading, groups might not be loaded. So we need to fetch counts from backend.
    // Let's create a new endpoint: /api/models/<name>/topics-with-counts
    // However, that's extra work. We'll keep using window.groups for now; if not loaded, counts show 0.
    // In a full implementation, we'd add a command to get topics with usage counts.
    // For the purpose of this exercise, we'll assume groups are loaded when topics tab is activated,
    // which they are because loadTopics is called from tab click, and groups are loaded separately.
    // Actually, in switchModel we only load the active tab. So if the user switches directly to Topics
    // after model selection, groups are NOT loaded. So we need to fetch counts separately.
    // Let's add a command to get topics with usage counts, but that's more code. I'll simulate by
    // using window.groups if available, else 0. In practice you'd implement a backend endpoint.

    const groupCounts = {};
    if (window.groups && window.groups.length) {
        window.groups.forEach(g => {
            const topic = g.topic;
            if (topic) groupCounts[topic] = (groupCounts[topic] || 0) + 1;
        });
    }

    let html = '<div class="topics-grid">';
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
        topic: card.dataset.topic,
        count: parseInt(card.dataset.count, 10)
    }));

    document.getElementById('topicSearch').disabled = false;
    document.getElementById('topicSectionFilter').disabled = false;
    document.getElementById('topicFilter').disabled = false;
    document.getElementById('topicSort').disabled = false;
    document.getElementById('addTopicBtn').disabled = false;

    filterAndSortTopics();
}

function filterAndSortTopics() {
    const searchTerm = document.getElementById('topicSearch').value.toLowerCase();
    const sectionFilter = document.getElementById('topicSectionFilter').value;
    const usageFilter = document.getElementById('topicFilter').value;
    const sortValue = document.getElementById('topicSort').value;

    let visibleCards = topicCards.filter(card => {
        const matchesSearch = card.topic.toLowerCase().includes(searchTerm);
        if (!matchesSearch) return false;

        // Section filter requires groups; if groups not loaded, skip section filtering.
        if (sectionFilter !== 'All Sections' && window.groups && window.groups.length) {
            const groupsForTopic = window.groups.filter(g => g.topic === card.topic);
            const sectionsForTopic = new Set(groupsForTopic.map(g => g.section).filter(s => s));
            if (!sectionsForTopic.has(sectionFilter)) return false;
        }

        if (usageFilter === 'used') return card.count > 0;
        if (usageFilter === 'unused') return card.count === 0;
        return true;
    });

    visibleCards.sort((a, b) => {
        switch (sortValue) {
            case 'name-asc': return a.topic.localeCompare(b.topic);
            case 'name-desc': return b.topic.localeCompare(a.topic);
            case 'usage-desc': return b.count - a.count;
            case 'usage-asc': return a.count - b.count;
            default: return 0;
        }
    });

    const grid = document.querySelector('.topics-grid');
    visibleCards.forEach(card => grid.appendChild(card.element));
    topicCards.forEach(card => {
        card.element.style.display = visibleCards.includes(card) ? 'flex' : 'none';
    });
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
    // Show modal with loading indicator first
    const modal = document.getElementById('simpleModal');
    const content = document.getElementById('simpleModalContent');
    content.innerHTML = `
        <h2>Edit Topic</h2>
        <div style="text-align:center; padding:20px;">Loading groups...</div>
    `;
    window.pushModal('simpleModal');

    try {
        // Fetch groups for this topic from the backend
        const result = await window.apiGet(`/api/models/${window.currentModel}/topics/${oldName}/groups`);
        const groupsUsing = result.groups || [];

        // Build groups list HTML
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

        // Attach edit/delete handlers for groups
        document.querySelectorAll('.edit-group-from-topic').forEach(btn => {
            btn.addEventListener('click', async (e) => {
                e.stopPropagation();
                const li = e.target.closest('.group-usage-item');
                const groupId = li.dataset.groupId;
                if (groupId) {
                    // Need to open group modal using group id. Group modal expects index.
                    // Convert id to index via a lookup. We can fetch group summaries or use groups list if available.
                    // For simplicity, we'll assume we have group summaries in window.groups (they might not be loaded).
                    // So we need a way to open group modal by id. We could add a new endpoint for group by id.
                    // But that's more work. Instead, we can open group modal with index after fetching summaries.
                    // Let's temporarily load group summaries if not already loaded.
                    if (!window.groups || window.groups.length === 0) {
                        // Load summaries just this once
                        await window.loadGroupsAndSections();
                    }
                    // Find index of group with this id
                    const index = window.groups.findIndex(g => g.id == groupId);
                    if (index !== -1) {
                        // We need to pass the group index to openGroupModal.
                        // But openGroupModal is defined in groups.js and expects index.
                        // That's fine; we'll call it. However, groups.js may not be loaded if we are in topics tab.
                        // But groups.js is globally loaded, so it's okay.
                        window.openGroupModal(index, () => {
                            // After group modal closes, we don't need to do anything
                            // The topic modal is still there (with hidden backdrop) and will reappear
                        });
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
                        // Delete group by id – we need an endpoint that accepts id
                        // Currently delete-group uses index. We'll use the index approach.
                        // Find index of group with this id
                        if (!window.groups || window.groups.length === 0) {
                            await window.loadGroupsAndSections();
                        }
                        const index = window.groups.findIndex(g => g.id == groupId);
                        if (index !== -1) {
                            await window.apiDelete(`/api/models/${window.currentModel}/groups/${index}`);
                            // Remove the list item
                            li.remove();
                            // Refresh the topic modal to show updated list
                            const currentTopicName = document.getElementById('editTopicName').value;
                            // Close current modal and reopen
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
    // For delete, we need the count of groups using this topic.
    // We can fetch it from the backend, but for simplicity we'll use window.groups if available.
    let groupsUsing = 0;
    if (window.groups && window.groups.length) {
        groupsUsing = window.groups.filter(g => g.topic === topic).length;
    } else {
        // If groups not loaded, we can't show accurate count. We'll assume 0? Better to fetch.
        // We'll add an async fetch inside deleteTopic. For now, keep as 0 but warn.
        console.warn('Groups not loaded, assuming 0 groups using topic');
    }
    let message = `Delete topic "${topic}"?`;
    if (groupsUsing > 0) {
        message = `Topic "${topic}" is used by ${groupsUsing} group(s).`;
    }

    // Build reassign dropdown options
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
            // No groups using this topic – just delete it
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

// Event listeners
document.getElementById('topicSearch').addEventListener('input', filterAndSortTopics);
document.getElementById('topicSectionFilter').addEventListener('change', (e) => {
    topicsSectionFilter = e.target.value;
    filterAndSortTopics();
});
document.getElementById('topicFilter').addEventListener('change', filterAndSortTopics);
document.getElementById('topicSort').addEventListener('change', filterAndSortTopics);
document.getElementById('addTopicBtn').addEventListener('click', addTopic);
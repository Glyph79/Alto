// groups.js - using GridRenderer
let groupsGrid = null;

// ========== Load Groups & Sections ==========
window.loadGroupsAndSections = async function() {
    if (!window.currentModel) return;
    try {
        const data = await window.apiGet(`/api/models/${window.currentModel}/groups/summaries`);
        window.groups = data.groups || [];
        window.sections = data.sections || ["General", "Technical", "Creative"];
        
        // Populate section filter dropdown
        const sectionFilter = document.getElementById('sectionFilter');
        sectionFilter.innerHTML = '<option value="All Sections">All Sections</option><option value="Uncategorized">Uncategorized</option>';
        window.sections.forEach(s => {
            const opt = document.createElement('option');
            opt.value = s;
            opt.textContent = s;
            sectionFilter.appendChild(opt);
        });

        // Initialize or update grid renderer
        if (!groupsGrid) {
            groupsGrid = new GridRenderer({
                containerId: 'groupsGridContainer',
                items: window.groups,
                renderItem: (group, idx) => `
                    <div class="group-card" data-card-index="${idx}" data-group-id="${group.id}">
                        <div class="header">
                            <span class="section-badge">${escapeHtml(group.section || 'Uncategorized')}</span>
                            <div class="card-actions">
                                <button class="card-edit" data-group-id="${group.id}" title="Edit">✎</button>
                                <button class="card-delete" data-group-id="${group.id}" title="Delete">🗑</button>
                            </div>
                        </div>
                        <h4>${escapeHtml(group.group_name || 'Unnamed')}</h4>
                        <div class="description">${escapeHtml(group.group_description || '')}</div>
                        <div class="stats">
                            <span>❓ ${group.question_count || 0} question${group.question_count !== 1 ? 's' : ''}</span>
                            <span>💬 ${group.answer_count || 0} answer${group.answer_count !== 1 ? 's' : ''}</span>
                        </div>
                    </div>
                `,
                options: {
                    searchInputId: 'groupSearch',
                    searchFields: ['group_name', 'group_description'],
                    filterSelectors: {
                        'sectionFilter': (item, value) => {
                            if (value === 'All Sections') return true;
                            if (value === 'Uncategorized') return !item.section;
                            return item.section === value;
                        }
                    },
                    sortSelectors: {
                        'name-asc': (a, b) => (a.group_name || '').localeCompare(b.group_name || ''),
                        'name-desc': (a, b) => (b.group_name || '').localeCompare(a.group_name || ''),
                        'questions-desc': (a, b) => (b.question_count || 0) - (a.question_count || 0),
                        'questions-asc': (a, b) => (a.question_count || 0) - (b.question_count || 0),
                        'answers-desc': (a, b) => (b.answer_count || 0) - (a.answer_count || 0),
                        'answers-asc': (a, b) => (a.answer_count || 0) - (b.answer_count || 0)
                    },
                    defaultSort: 'name-asc',
                    emptyStateHtml: '<div class="empty-state">No groups match the current filters.</div>',
                    onCardClick: (group, idx) => openGroupModal(idx),
                    onCardEdit: (group, idx) => openGroupModal(idx),
                    onCardDelete: (group, idx) => deleteGroup(idx)
                }
            });
        } else {
            groupsGrid.setItems(window.groups);
        }

        document.getElementById('groupSearch').disabled = false;
        document.getElementById('sectionFilter').disabled = false;
        document.getElementById('groupSort').disabled = false;
        document.getElementById('addGroupBtn').disabled = false;
        document.getElementById('noGroupsEmptyState').style.display = window.groups.length ? 'none' : 'flex';
    } catch (err) {
        const container = document.getElementById('groupsGridContainer');
        window.showSimpleRetry(container, `Failed to load groups: ${err.message}`, async () => {
            await window.loadGroupsAndSections();
        });
    }
};

function clearGroups() {
    if (groupsGrid) groupsGrid.destroy();
    groupsGrid = null;
    window.groups = [];
}

// ========== Group Modal & Tree Editor ==========
window.selectedGroupIndex = -1;
let modalGroupCopy = null;
let currentGroupFetchCleanup = null;

function attachGroupModalHandlers() {
    document.getElementById('modalAddQuestionBtn').onclick = () => {
        if (!modalGroupCopy) return;
        window.showSimpleModal('Add Question', [{ name: 'text', label: 'Question', value: '' }], (vals, errorDiv) => {
            if (!vals.text) {
                errorDiv.textContent = 'Question cannot be empty.';
                errorDiv.style.display = 'block';
                return;
            }
            if (!modalGroupCopy.questions) modalGroupCopy.questions = [];
            modalGroupCopy.questions.push(vals.text);
            refreshModalLists();
        }, 'Add');
    };

    document.getElementById('modalAddAnswerBtn').onclick = () => {
        if (!modalGroupCopy) return;
        window.showSimpleModal('Add Answer', [{ name: 'text', label: 'Answer', value: '' }], (vals, errorDiv) => {
            if (!vals.text) {
                errorDiv.textContent = 'Answer cannot be empty.';
                errorDiv.style.display = 'block';
                return;
            }
            if (!modalGroupCopy.answers) modalGroupCopy.answers = [];
            modalGroupCopy.answers.push(vals.text);
            refreshModalLists();
        }, 'Add');
    };

    document.getElementById('modalSaveBtn').onclick = async () => {
        if (!modalGroupCopy) return;

        modalGroupCopy.group_name = document.getElementById('modalGroupName').value;
        modalGroupCopy.group_description = document.getElementById('modalGroupDesc').value;
        modalGroupCopy.topic = document.getElementById('modalGroupTopic').value;
        modalGroupCopy.section = document.getElementById('modalGroupSection').value;
        modalGroupCopy.fallback = document.getElementById('modalGroupFallback').value;

        try {
            if (window.selectedGroupIndex === null) {
                await window.apiPost(`/api/models/${window.currentModel}/groups`, modalGroupCopy);
            } else {
                await window.apiPut(`/api/models/${window.currentModel}/groups/${window.selectedGroupIndex}`, modalGroupCopy);
            }
            resetGroupsFilters();
            await window.loadGroupsAndSections();
            if (typeof window.loadTopics === 'function') await window.loadTopics();
            if (typeof window.loadSections === 'function') await window.loadSections();
            window.popModal();
            modalGroupCopy = null;
            if (window._groupModalOnSave) {
                window._groupModalOnSave();
                window._groupModalOnSave = null;
            }
        } catch (err) {
            const modalContent = document.querySelector('#groupModal .modal-content');
            window.showSimpleRetry(modalContent, `Save failed: ${err.message}`, async () => {
                document.getElementById('modalSaveBtn').click();
            });
        }
    };

    document.getElementById('modalCancelBtn').onclick = () => {
        if (currentGroupFetchCleanup) currentGroupFetchCleanup.clear();
        modalGroupCopy = null;
        window.popModal();
        window._groupModalOnSave = null;
    };

    document.getElementById('modalEditFollowupsBtn').onclick = async () => {
        if (window.selectedGroupIndex === null) {
            const modalContent = document.querySelector('#groupModal .modal-content');
            window.showSimpleRetry(modalContent, 'Cannot edit follow‑up tree for a group that hasn’t been saved yet. Please save the group first.', () => {});
            return;
        }
        window.openTreeModalForGroup(window.selectedGroupIndex);
    };
}

window.refreshGroupModalFallbackDropdown = function() {
    const select = document.getElementById('modalGroupFallback');
    if (!select) return;
    let options = '<option value="">(None)</option>';
    (window.fallbacks || []).forEach(fb => {
        options += `<option value="${escapeHtml(fb.name)}">${escapeHtml(fb.name)}</option>`;
    });
    select.innerHTML = options;
    if (modalGroupCopy && modalGroupCopy.fallback) {
        select.value = modalGroupCopy.fallback;
    } else {
        select.value = '';
    }
};

window.openGroupModal = async function(index, onSaveCallback) {
    window.selectedGroupIndex = index;
    const isNew = (index === null);

    const modal = document.getElementById('groupModal');
    const content = modal.querySelector('.modal-content');
    content.innerHTML = `
        <h2>${isNew ? 'Create Group' : 'Edit Group'}</h2>
        <div class="form-row">
            <label>Group Name</label>
            <input type="text" id="modalGroupName" value="">
        </div>
        <div class="form-row">
            <label>Description</label>
            <input type="text" id="modalGroupDesc" value="">
        </div>
        <div class="form-row" style="display: flex; gap: 16px;">
            <div style="flex:1;">
                <label>Topic</label>
                <select id="modalGroupTopic"><option value="">Loading...</option></select>
            </div>
            <div style="flex:1;">
                <label>Section</label>
                <select id="modalGroupSection"><option value="">Loading...</option></select>
            </div>
        </div>
        <div class="form-row">
            <label>Fallback (custom default response)</label>
            <select id="modalGroupFallback">
                <option value="">(None)</option>
            </select>
        </div>

        <div class="qa-section">
            <h3>Questions</h3>
            <ul class="qa-list" id="modalQuestionsList"></ul>
            <button class="add-btn" id="modalAddQuestionBtn">+ Add Question</button>
        </div>

        <div class="qa-section">
            <h3>Answers</h3>
            <ul class="qa-list" id="modalAnswersList"></ul>
            <button class="add-btn" id="modalAddAnswerBtn">+ Add Answer</button>
        </div>

        <div style="margin-top:16px;">
            <button id="modalEditFollowupsBtn" style="background:#a78bfa; color:white; border:none; padding:10px; border-radius:6px; width:100%;">🌳 Edit Follow-up Tree</button>
        </div>

        <div class="modal-actions">
            <button class="cancel" id="modalCancelBtn">Cancel</button>
            <button class="save" id="modalSaveBtn">Save Changes</button>
        </div>
    `;

    window.pushModal('groupModal');
    attachGroupModalHandlers();

    const modalContentDiv = document.querySelector('#groupModal .modal-content');
    window.disableButtonsInContainer(modalContentDiv);

    if (currentGroupFetchCleanup) currentGroupFetchCleanup.clear();

    const qList = document.getElementById('modalQuestionsList');
    const aList = document.getElementById('modalAnswersList');

    currentGroupFetchCleanup = window.showInlineLoading(qList, "Loading questions");
    const answersLoading = window.showInlineLoading(aList, "Loading answers");

    try {
        await ensureTopicsLoaded();
        if (isNew) {
            modalGroupCopy = {
                group_name: '',
                group_description: '',
                topic: '',
                section: '',
                fallback: '',
                questions: [],
                answers: []
            };
            document.getElementById('modalGroupName').value = '';
            document.getElementById('modalGroupDesc').value = '';

            const topicSelect = document.getElementById('modalGroupTopic');
            let topicOptions = '<option value="">(No Topic)</option>';
            if (window.topicsList && window.topicsList.length) {
                topicOptions += window.topicsList.map(t => `<option value="${escapeHtml(t)}">${escapeHtml(t)}</option>`).join('');
            } else {
                topicOptions += '<option value="general">general</option>';
            }
            topicSelect.innerHTML = topicOptions;
            topicSelect.value = '';

            const sectionSelect = document.getElementById('modalGroupSection');
            let sectionOptions = '<option value="">(Uncategorized)</option>';
            sectionOptions += window.sections.map(s => `<option value="${escapeHtml(s)}">${escapeHtml(s)}</option>`).join('');
            sectionSelect.innerHTML = sectionOptions;
            sectionSelect.value = '';

            window.refreshGroupModalFallbackDropdown();
            refreshModalLists();
            window._groupModalOnSave = onSaveCallback;
        } else {
            const fullGroup = await window.retryOperation(async () => {
                return await window.apiGet(`/api/models/${window.currentModel}/groups/${index}/full`);
            });
            modalGroupCopy = fullGroup;

            document.getElementById('modalGroupName').value = modalGroupCopy.group_name || '';
            document.getElementById('modalGroupDesc').value = modalGroupCopy.group_description || '';

            const topicSelect = document.getElementById('modalGroupTopic');
            let topicOptions = '<option value="">(No Topic)</option>';
            if (window.topicsList && window.topicsList.length) {
                topicOptions += window.topicsList.map(t => `<option value="${escapeHtml(t)}">${escapeHtml(t)}</option>`).join('');
            } else {
                topicOptions += '<option value="general">general</option>';
            }
            topicSelect.innerHTML = topicOptions;
            topicSelect.value = modalGroupCopy.topic || '';

            const sectionSelect = document.getElementById('modalGroupSection');
            let sectionOptions = '<option value="">(Uncategorized)</option>';
            sectionOptions += window.sections.map(s => `<option value="${escapeHtml(s)}">${escapeHtml(s)}</option>`).join('');
            sectionSelect.innerHTML = sectionOptions;
            sectionSelect.value = modalGroupCopy.section || '';

            window.refreshGroupModalFallbackDropdown();
            refreshModalLists();
            window._groupModalOnSave = onSaveCallback;
        }
        if (currentGroupFetchCleanup) currentGroupFetchCleanup.clear();
        answersLoading.clear();
        window.enableButtonsInContainer(modalContentDiv);
    } catch (err) {
        if (currentGroupFetchCleanup) currentGroupFetchCleanup.clear();
        answersLoading.clear();
        window.showInlineListRetry(qList, 'questions', async () => {
            await openGroupModal(index, onSaveCallback);
        });
        window.showInlineListRetry(aList, 'answers', async () => {
            await openGroupModal(index, onSaveCallback);
        });
    } finally {
        if (currentGroupFetchCleanup && !currentGroupFetchCleanup.interval) {
            currentGroupFetchCleanup.clear();
            currentGroupFetchCleanup = null;
        }
    }
};

window.refreshGroupModalTopicDropdown = function() {
    if (document.getElementById('groupModal').classList.contains('visible') && modalGroupCopy) {
        const topicSelect = document.getElementById('modalGroupTopic');
        let options = '<option value="">(No Topic)</option>';
        options += window.topicsList.map(t => `<option value="${escapeHtml(t)}">${escapeHtml(t)}</option>`).join('');
        topicSelect.innerHTML = options;
        if (window.topicsList.includes(modalGroupCopy.topic)) {
            topicSelect.value = modalGroupCopy.topic;
        } else {
            topicSelect.value = '';
            modalGroupCopy.topic = '';
        }
    }
};

function refreshModalLists() {
    const qList = document.getElementById('modalQuestionsList');
    qList.innerHTML = '';
    (modalGroupCopy.questions || []).forEach((q, i) => {
        const li = document.createElement('li');
        li.innerHTML = `<span>${escapeHtml(q)}</span> <span><button class="edit-question" data-idx="${i}">✎</button><button class="delete-question" data-idx="${i}">🗑</button></span>`;
        qList.appendChild(li);
    });
    qList.querySelectorAll('.edit-question').forEach(btn => {
        btn.addEventListener('click', () => editQuestion(parseInt(btn.dataset.idx)));
    });
    qList.querySelectorAll('.delete-question').forEach(btn => {
        btn.addEventListener('click', () => deleteQuestion(parseInt(btn.dataset.idx)));
    });

    const aList = document.getElementById('modalAnswersList');
    aList.innerHTML = '';
    (modalGroupCopy.answers || []).forEach((a, i) => {
        const li = document.createElement('li');
        li.innerHTML = `<span>${escapeHtml(a)}</span> <span><button class="edit-answer" data-idx="${i}">✎</button><button class="delete-answer" data-idx="${i}">🗑</button></span>`;
        aList.appendChild(li);
    });
    aList.querySelectorAll('.edit-answer').forEach(btn => {
        btn.addEventListener('click', () => editAnswer(parseInt(btn.dataset.idx)));
    });
    aList.querySelectorAll('.delete-answer').forEach(btn => {
        btn.addEventListener('click', () => deleteAnswer(parseInt(btn.dataset.idx)));
    });
}

function editQuestion(qIdx) {
    window.showSimpleModal('Edit Question', [{ name: 'text', label: 'Question', value: modalGroupCopy.questions[qIdx] }], (vals, errorDiv) => {
        if (!vals.text) {
            errorDiv.textContent = 'Question cannot be empty.';
            errorDiv.style.display = 'block';
            return;
        }
        modalGroupCopy.questions[qIdx] = vals.text;
        refreshModalLists();
    }, 'Save');
}

function deleteQuestion(qIdx) {
    window.showConfirmModal('Delete this question?', () => {
        modalGroupCopy.questions.splice(qIdx, 1);
        refreshModalLists();
    });
}

function editAnswer(aIdx) {
    window.showSimpleModal('Edit Answer', [{ name: 'text', label: 'Answer', value: modalGroupCopy.answers[aIdx] }], (vals, errorDiv) => {
        if (!vals.text) {
            errorDiv.textContent = 'Answer cannot be empty.';
            errorDiv.style.display = 'block';
            return;
        }
        modalGroupCopy.answers[aIdx] = vals.text;
        refreshModalLists();
    }, 'Save');
}

function deleteAnswer(aIdx) {
    window.showConfirmModal('Delete this answer?', () => {
        modalGroupCopy.answers.splice(aIdx, 1);
        refreshModalLists();
    });
}

async function ensureTopicsLoaded() {
    if (!window.currentModel) return;
    if (!window.topicsList || window.topicsList.length === 0) {
        try {
            window.topicsList = await window.apiGet(`/api/models/${window.currentModel}/topics`);
        } catch (err) {
            console.warn('Could not load topics:', err);
            window.topicsList = [];
        }
    }
}

async function deleteGroup(index, callback) {
    window.showConfirmModal('Are you sure you want to delete this group?', async () => {
        try {
            await window.apiDelete(`/api/models/${window.currentModel}/groups/${index}`);
            resetGroupsFilters();
            await window.loadGroupsAndSections();
            if (callback) callback();
        } catch (err) {
            const container = document.getElementById('groupsGridContainer');
            window.showSimpleRetry(container, `Failed to delete group: ${err.message}`, async () => {
                await deleteGroup(index, callback);
            });
        }
    });
}

async function createNewGroup() {
    if (!window.currentModel) {
        const container = document.getElementById('groupsGridContainer');
        window.showSimpleRetry(container, 'Please select or create a model first.', () => {});
        return;
    }
    await window.openGroupModal(null);
}

function resetGroupsFilters() {
    const search = document.getElementById('groupSearch');
    if (search) search.value = '';
    const sectionFilter = document.getElementById('sectionFilter');
    if (sectionFilter) sectionFilter.value = 'All Sections';
    const sort = document.getElementById('groupSort');
    if (sort) sort.value = 'name-asc';
    if (search) search.dispatchEvent(new Event('input', { bubbles: true }));
    if (sectionFilter) sectionFilter.dispatchEvent(new Event('change', { bubbles: true }));
    if (sort) sort.dispatchEvent(new Event('change', { bubbles: true }));
}

document.getElementById('addGroupBtn').onclick = createNewGroup;
document.getElementById('createFirstGroupBtn').onclick = createNewGroup;

attachGroupModalHandlers();
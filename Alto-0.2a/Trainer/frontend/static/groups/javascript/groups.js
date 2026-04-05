// ========== Load Groups & Sections ==========
window.loadGroupsAndSections = async function() {
    if (!window.currentModel) return;
    try {
        const data = await window.apiGet(`/api/models/${window.currentModel}/groups/summaries`);
        window.groups = data.groups || [];
        window.sections = data.sections || ["General", "Technical", "Creative"];
        renderGroups();
        renderSectionFilter();
        document.getElementById('groupModal').classList.remove('visible');
        document.getElementById('treeModal').classList.remove('visible');
        document.getElementById('groupSearch').disabled = false;
        document.getElementById('sectionFilter').disabled = false;
        document.getElementById('groupSort').disabled = false;
        document.getElementById('addGroupBtn').disabled = false;
    } catch (err) {
        const container = document.getElementById('groupsGridContainer');
        window.showSimpleRetry(container, `Failed to load groups: ${err.message}`, async () => {
            await window.loadGroupsAndSections();
        });
    }
};

let groupCards = [];

function renderSectionFilter() {
    const select = document.getElementById('sectionFilter');
    select.innerHTML = '<option value="All Sections">All Sections</option><option value="Uncategorized">Uncategorized</option>';
    window.sections.forEach(s => {
        const opt = document.createElement('option');
        opt.value = s;
        opt.textContent = s;
        select.appendChild(opt);
    });
}

function renderGroups() {
    const container = document.getElementById('groupsGridContainer');
    if (!container) return;
    if (window.groups.length === 0) {
        container.innerHTML = '';
        document.getElementById('noGroupsEmptyState').style.display = 'flex';
        groupCards = [];
        if (window.groupsManager) window.groupsManager.setCardArray([]);
        return;
    }
    document.getElementById('noGroupsEmptyState').style.display = 'none';

    let html = '<div class="groups-grid grid">';
    window.groups.forEach((g, idx) => {
        const section = g.section || 'Uncategorized';
        const qCount = g.question_count || 0;
        const aCount = g.answer_count || 0;
        html += `
            <div class="group-card" data-index="${idx}" data-name="${escapeHtml(g.group_name || '')}" data-desc="${escapeHtml(g.group_description || '')}">
                <div class="header">
                    <span class="section-badge">${escapeHtml(section)}</span>
                    <div class="card-actions">
                        <button class="edit-group" data-index="${idx}" title="Edit">✎</button>
                        <button class="delete-group" data-index="${idx}" title="Delete">🗑</button>
                    </div>
                </div>
                <h4>${escapeHtml(g.group_name || 'Unnamed')}</h4>
                <div class="description">${escapeHtml(g.group_description || '')}</div>
                <div class="stats">
                    <span>❓ ${qCount} question${qCount !== 1 ? 's' : ''}</span>
                    <span>💬 ${aCount} answer${aCount !== 1 ? 's' : ''}</span>
                </div>
            </div>
        `;
    });
    html += '</div>';
    container.innerHTML = html;

    if (window.groupsManager) {
        window.groupsManager.grid = container.querySelector('.grid') || container;
    }

    groupCards = Array.from(document.querySelectorAll('.group-card')).map(card => ({
        element: card,
        item: window.groups[parseInt(card.dataset.index)],
        index: parseInt(card.dataset.index)
    }));

    // Attach event listeners without inline onclick
    groupCards.forEach(card => {
        const index = card.index;
        card.element.addEventListener('click', (e) => {
            if (e.target.closest('.card-actions')) return;
            openGroupModal(index);
        });
        const editBtn = card.element.querySelector('.edit-group');
        if (editBtn) {
            editBtn.addEventListener('click', (e) => {
                e.stopPropagation();
                openGroupModal(index);
            });
        }
        const deleteBtn = card.element.querySelector('.delete-group');
        if (deleteBtn) {
            deleteBtn.addEventListener('click', (e) => {
                e.stopPropagation();
                deleteGroup(index);
            });
        }
    });

    if (!window.groupsManager) {
        window.groupsManager = new window.SearchManager({
            containerId: 'groupsGridContainer',
            cardArray: groupCards,
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
            defaultSort: 'name-asc'
        });
    } else {
        window.groupsManager.setCardArray(groupCards);
    }
}

async function deleteGroup(index, callback) {
    window.showConfirmModal('Are you sure you want to delete this group?', async () => {
        try {
            await window.apiDelete(`/api/models/${window.currentModel}/groups/${index}`);
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

// ========== Group Modal ==========
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

        try {
            if (window.selectedGroupIndex === null) {
                await window.apiPost(`/api/models/${window.currentModel}/groups`, modalGroupCopy);
            } else {
                await window.apiPut(`/api/models/${window.currentModel}/groups/${window.selectedGroupIndex}`, modalGroupCopy);
            }
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

async function createNewGroup() {
    if (!window.currentModel) {
        const container = document.getElementById('groupsGridContainer');
        window.showSimpleRetry(container, 'Please select or create a model first.', () => {});
        return;
    }
    await window.openGroupModal(null);
}

document.getElementById('addGroupBtn').onclick = createNewGroup;
document.getElementById('createFirstGroupBtn').onclick = createNewGroup;

attachGroupModalHandlers();
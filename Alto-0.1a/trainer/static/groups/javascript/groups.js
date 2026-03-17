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
        alert('Error loading groups: ' + err.message);
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
            <div class="group-card" data-index="${idx}" data-name="${g.group_name || ''}" data-desc="${g.group_description || ''}">
                <div class="header">
                    <span class="section-badge">${section}</span>
                    <div class="card-actions">
                        <button class="edit-group" title="Edit">✎</button>
                        <button class="delete-group" title="Delete">🗑</button>
                    </div>
                </div>
                <h4>${g.group_name || 'Unnamed'}</h4>
                <div class="description">${g.group_description || ''}</div>
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

    groupCards.forEach(card => {
        const index = card.index;
        card.element.addEventListener('click', (e) => {
            if (e.target.closest('.card-actions')) return;
            openGroupModal(index);
        });
        card.element.querySelector('.edit-group').addEventListener('click', (e) => {
            e.stopPropagation();
            openGroupModal(index);
        });
        card.element.querySelector('.delete-group').addEventListener('click', (e) => {
            e.stopPropagation();
            deleteGroup(index);
        });
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
        await window.apiDelete(`/api/models/${window.currentModel}/groups/${index}`);
        await window.loadGroupsAndSections();
        if (callback) callback();
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
let currentGroupFetchAnimation = null;

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
        if (window.selectedGroupIndex === -1 || !modalGroupCopy) return;

        modalGroupCopy.group_name = document.getElementById('modalGroupName').value;
        modalGroupCopy.group_description = document.getElementById('modalGroupDesc').value;
        modalGroupCopy.topic = document.getElementById('modalGroupTopic').value;
        modalGroupCopy.section = document.getElementById('modalGroupSection').value;

        await window.apiPut(`/api/models/${window.currentModel}/groups/${window.selectedGroupIndex}`, modalGroupCopy);
        
        // Refresh global groups and sections
        await window.loadGroupsAndSections();
        
        // Also refresh topics and sections data so that the topics/sections grids update immediately
        if (typeof window.loadTopics === 'function') {
            await window.loadTopics();
        }
        if (typeof window.loadSections === 'function') {
            await window.loadSections();
        }
        
        window.popModal();
        modalGroupCopy = null;

        if (window._groupModalOnSave) {
            window._groupModalOnSave();
            window._groupModalOnSave = null;
        }
    };

    document.getElementById('modalCancelBtn').onclick = () => {
        modalGroupCopy = null;
        window.popModal();
        window._groupModalOnSave = null;
    };

    document.getElementById('modalEditFollowupsBtn').onclick = async () => {
        if (typeof window.selectedGroupIndex === 'undefined' || window.selectedGroupIndex === -1) return;
        try {
            const treeData = await window.apiGet(`/api/models/${window.currentModel}/groups/${window.selectedGroupIndex}/followups`);
            if (window.openTreeModal) {
                window.openTreeModal(treeData);
            } else {
                console.error('Tree modal handler not available');
            }
        } catch (err) {
            alert('Error loading follow-up tree: ' + err.message);
        }
    };
}

window.openGroupModal = async function(index, onSaveCallback) {
    window.selectedGroupIndex = index;

    const modal = document.getElementById('groupModal');
    const content = modal.querySelector('.modal-content');
    // Build basic structure with placeholders
    content.innerHTML = `
        <h2>Edit Group</h2>
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
            <ul class="qa-list" id="modalQuestionsList"><li>Loading questions...</li></ul>
            <button class="add-btn" id="modalAddQuestionBtn">+ Add Question</button>
        </div>

        <div class="qa-section">
            <h3>Answers</h3>
            <ul class="qa-list" id="modalAnswersList"><li>Loading answers...</li></ul>
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

    if (currentGroupFetchAnimation) {
        clearTimeout(currentGroupFetchAnimation.timeout);
        clearInterval(currentGroupFetchAnimation.interval);
        currentGroupFetchAnimation = null;
    }

    let loadingTimeout = setTimeout(() => {
        const qList = document.getElementById('modalQuestionsList');
        const aList = document.getElementById('modalAnswersList');
        if (qList) qList.innerHTML = '<li>Loading questions</li>';
        if (aList) aList.innerHTML = '<li>Loading answers</li>';
        let dots = 0;
        const loadingInterval = setInterval(() => {
            dots = (dots + 1) % 4;
            const dotsStr = '.'.repeat(dots);
            if (qList) qList.innerHTML = `<li>Loading questions${dotsStr}</li>`;
            if (aList) aList.innerHTML = `<li>Loading answers${dotsStr}</li>`;
        }, 300);
        currentGroupFetchAnimation = { timeout: loadingTimeout, interval: loadingInterval };
    }, 300);

    let attempts = 0;
    const maxAttempts = 3;

    while (attempts < maxAttempts) {
        attempts++;
        try {
            await ensureTopicsLoaded();
            const fullGroup = await window.apiGet(`/api/models/${window.currentModel}/groups/${index}/full`);
            modalGroupCopy = fullGroup;

            if (currentGroupFetchAnimation) {
                clearTimeout(currentGroupFetchAnimation.timeout);
                clearInterval(currentGroupFetchAnimation.interval);
                currentGroupFetchAnimation = null;
            } else {
                clearTimeout(loadingTimeout);
            }

            document.getElementById('modalGroupName').value = modalGroupCopy.group_name || '';
            document.getElementById('modalGroupDesc').value = modalGroupCopy.group_description || '';

            const topicSelect = document.getElementById('modalGroupTopic');
            let topicOptions = '<option value="">(No Topic)</option>';
            if (window.topicsList && window.topicsList.length) {
                topicOptions += window.topicsList.map(t => `<option value="${t}">${t}</option>`).join('');
            } else {
                topicOptions += '<option value="general">general</option>';
            }
            topicSelect.innerHTML = topicOptions;
            topicSelect.value = modalGroupCopy.topic || '';

            const sectionSelect = document.getElementById('modalGroupSection');
            let sectionOptions = '<option value="">(Uncategorized)</option>';
            sectionOptions += window.sections.map(s => `<option value="${s}">${s}</option>`).join('');
            sectionSelect.innerHTML = sectionOptions;
            sectionSelect.value = modalGroupCopy.section || '';

            refreshModalLists();
            window._groupModalOnSave = onSaveCallback;
            return;
        } catch (err) {
            if (attempts < maxAttempts) {
                await new Promise(resolve => setTimeout(resolve, 200 * Math.pow(2, attempts - 1)));
            }
        }
    }

    if (currentGroupFetchAnimation) {
        clearTimeout(currentGroupFetchAnimation.timeout);
        clearInterval(currentGroupFetchAnimation.interval);
        currentGroupFetchAnimation = null;
    } else {
        clearTimeout(loadingTimeout);
    }
    document.getElementById('modalQuestionsList').innerHTML = '<li style="color: #ff6b9d;">Error loading questions</li>';
    document.getElementById('modalAnswersList').innerHTML = '<li style="color: #ff6b9d;">Error loading answers</li>';
    modalGroupCopy = { group_name: '', group_description: '', topic: '', section: '', questions: [], answers: [] };
};

window.refreshGroupModalTopicDropdown = function() {
    if (document.getElementById('groupModal').classList.contains('visible') && modalGroupCopy) {
        const topicSelect = document.getElementById('modalGroupTopic');
        let options = '<option value="">(No Topic)</option>';
        options += window.topicsList.map(t => `<option value="${t}">${t}</option>`).join('');
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
        li.innerHTML = `<span>${q}</span> <span><button onclick="editQuestion(${i})">✎</button><button onclick="deleteQuestion(${i})">🗑</button></span>`;
        qList.appendChild(li);
    });

    const aList = document.getElementById('modalAnswersList');
    aList.innerHTML = '';
    (modalGroupCopy.answers || []).forEach((a, i) => {
        const li = document.createElement('li');
        li.innerHTML = `<span>${a}</span> <span><button onclick="editAnswer(${i})">✎</button><button onclick="deleteAnswer(${i})">🗑</button></span>`;
        aList.appendChild(li);
    });
}

window.editQuestion = (qIdx) => {
    window.showSimpleModal('Edit Question', [{ name: 'text', label: 'Question', value: modalGroupCopy.questions[qIdx] }], (vals, errorDiv) => {
        if (!vals.text) {
            errorDiv.textContent = 'Question cannot be empty.';
            errorDiv.style.display = 'block';
            return;
        }
        modalGroupCopy.questions[qIdx] = vals.text;
        refreshModalLists();
    }, 'Save');
};

window.deleteQuestion = (qIdx) => {
    window.showConfirmModal('Delete this question?', () => {
        modalGroupCopy.questions.splice(qIdx, 1);
        refreshModalLists();
    });
};

window.editAnswer = (aIdx) => {
    window.showSimpleModal('Edit Answer', [{ name: 'text', label: 'Answer', value: modalGroupCopy.answers[aIdx] }], (vals, errorDiv) => {
        if (!vals.text) {
            errorDiv.textContent = 'Answer cannot be empty.';
            errorDiv.style.display = 'block';
            return;
        }
        modalGroupCopy.answers[aIdx] = vals.text;
        refreshModalLists();
    }, 'Save');
};

window.deleteAnswer = (aIdx) => {
    window.showConfirmModal('Delete this answer?', () => {
        modalGroupCopy.answers.splice(aIdx, 1);
        refreshModalLists();
    });
};

async function createNewGroup() {
    if (!window.currentModel) {
        alert('Please select or create a model first.');
        return;
    }
    const newGroup = {
        group_name: 'New Group',
        group_description: '',
        questions: [],
        answers: [],
        topic: '',
        section: ''
    };
    await window.apiPost(`/api/models/${window.currentModel}/groups`, newGroup);
    await window.loadGroupsAndSections();
}

document.getElementById('addGroupBtn').onclick = createNewGroup;
document.getElementById('createFirstGroupBtn').onclick = createNewGroup;

attachGroupModalHandlers();
// ========== Load Groups & Sections ==========
window.loadGroupsAndSections = async function() {
    if (!window.currentModel) return;
    try {
        const data = await window.apiGet(`/api/models/${window.currentModel}/groups`);
        window.groups = data.groups || [];
        window.sections = data.sections || ["General", "Technical", "Creative"];
        renderGroups();
        renderSectionFilter();
        document.getElementById('groupModal').style.display = 'none';
        document.getElementById('treeModal').style.display = 'none';
        document.getElementById('groupSearch').disabled = false;
        document.getElementById('sectionFilter').disabled = false;
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
        return;
    }
    document.getElementById('noGroupsEmptyState').style.display = 'none';

    let html = '<div class="groups-grid">';
    window.groups.forEach((g, idx) => {
        const section = g.section || 'Uncategorized';
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
                    <span>❓ ${g.questions?.length || 0}</span>
                    <span>💬 ${g.answers?.length || 0}</span>
                </div>
            </div>
        `;
    });
    html += '</div>';
    container.innerHTML = html;

    groupCards = Array.from(document.querySelectorAll('.group-card')).map(card => ({
        element: card,
        group: window.groups[parseInt(card.dataset.index)],
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

    filterAndSortGroups();
}

function filterAndSortGroups() {
    const searchTerm = document.getElementById('groupSearch').value.toLowerCase();
    const sectionFilter = document.getElementById('sectionFilter').value;

    let visibleCards = groupCards.filter(card => {
        const name = card.group.group_name || '';
        const desc = card.group.group_description || '';
        const matchesSearch = name.toLowerCase().includes(searchTerm) || desc.toLowerCase().includes(searchTerm);
        if (!matchesSearch) return false;

        if (sectionFilter === 'All Sections') return true;
        if (sectionFilter === 'Uncategorized') return !card.group.section;
        return card.group.section === sectionFilter;
    });

    const grid = document.querySelector('.groups-grid');
    visibleCards.forEach(card => grid.appendChild(card.element));
    groupCards.forEach(card => {
        card.element.style.display = visibleCards.includes(card) ? 'flex' : 'none';
    });
}

async function deleteGroup(index, callback) {
    window.showConfirmModal('Are you sure you want to delete this group?', async () => {
        await window.apiDelete(`/api/models/${window.currentModel}/groups/${index}`);
        await window.loadGroupsAndSections();
        if (callback) callback();
    });
}

// ========== Group Modal ==========
window.selectedGroupIndex = -1;
let modalGroupCopy = null;

window.openGroupModal = function(index, onSaveCallback) {
    window.selectedGroupIndex = index;
    const group = window.groups[index];
    if (!group) return;

    modalGroupCopy = JSON.parse(JSON.stringify(group));

    document.getElementById('modalGroupName').value = modalGroupCopy.group_name || '';
    document.getElementById('modalGroupDesc').value = modalGroupCopy.group_description || '';

    const sectionSelect = document.getElementById('modalGroupSection');
    sectionSelect.innerHTML = window.sections.map(s => `<option value="${s}">${s}</option>`).join('');
    sectionSelect.value = modalGroupCopy.section || window.sections[0] || '';

    const topicSelect = document.getElementById('modalGroupTopic');
    if (window.topicsList && window.topicsList.length) {
        topicSelect.innerHTML = window.topicsList.map(t => `<option value="${t}">${t}</option>`).join('');
        topicSelect.value = modalGroupCopy.topic || window.topicsList[0] || '';
    } else {
        topicSelect.innerHTML = '<option value="general">general</option>';
        topicSelect.value = modalGroupCopy.topic || 'general';
    }

    document.getElementById('modalGroupPriority').value = modalGroupCopy.priority || 'medium';

    refreshModalLists();
    document.getElementById('groupModal').style.display = 'flex';
    window.pushModal('groupModal');

    window._groupModalOnSave = onSaveCallback;
};

window.refreshGroupModalTopicDropdown = function() {
    if (document.getElementById('groupModal').style.display === 'flex' && modalGroupCopy) {
        const topicSelect = document.getElementById('modalGroupTopic');
        topicSelect.innerHTML = window.topicsList.map(t => `<option value="${t}">${t}</option>`).join('');
        if (window.topicsList.includes(modalGroupCopy.topic)) {
            topicSelect.value = modalGroupCopy.topic;
        } else {
            topicSelect.value = window.topicsList[0] || '';
            modalGroupCopy.topic = topicSelect.value;
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
        document.getElementById('simpleModal').style.display = 'none';
        window.popModal();
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
        document.getElementById('simpleModal').style.display = 'none';
        window.popModal();
    }, 'Save');
};

window.deleteAnswer = (aIdx) => {
    window.showConfirmModal('Delete this answer?', () => {
        modalGroupCopy.answers.splice(aIdx, 1);
        refreshModalLists();
    });
};

document.getElementById('modalAddQuestionBtn').onclick = () => {
    window.showSimpleModal('Add Question', [{ name: 'text', label: 'Question', value: '' }], (vals, errorDiv) => {
        if (!vals.text) {
            errorDiv.textContent = 'Question cannot be empty.';
            errorDiv.style.display = 'block';
            return;
        }
        if (!modalGroupCopy.questions) modalGroupCopy.questions = [];
        modalGroupCopy.questions.push(vals.text);
        refreshModalLists();
        document.getElementById('simpleModal').style.display = 'none';
        window.popModal();
    }, 'Add');
};

document.getElementById('modalAddAnswerBtn').onclick = () => {
    window.showSimpleModal('Add Answer', [{ name: 'text', label: 'Answer', value: '' }], (vals, errorDiv) => {
        if (!vals.text) {
            errorDiv.textContent = 'Answer cannot be empty.';
            errorDiv.style.display = 'block';
            return;
        }
        if (!modalGroupCopy.answers) modalGroupCopy.answers = [];
        modalGroupCopy.answers.push(vals.text);
        refreshModalLists();
        document.getElementById('simpleModal').style.display = 'none';
        window.popModal();
    }, 'Add');
};

document.getElementById('modalSaveBtn').onclick = async () => {
    if (window.selectedGroupIndex === -1 || !modalGroupCopy) return;

    modalGroupCopy.group_name = document.getElementById('modalGroupName').value;
    modalGroupCopy.group_description = document.getElementById('modalGroupDesc').value;
    modalGroupCopy.section = document.getElementById('modalGroupSection').value;
    modalGroupCopy.topic = document.getElementById('modalGroupTopic').value;
    modalGroupCopy.priority = document.getElementById('modalGroupPriority').value;

    await window.apiPut(`/api/models/${window.currentModel}/groups/${window.selectedGroupIndex}`, modalGroupCopy);
    await window.loadGroupsAndSections();
    document.getElementById('groupModal').style.display = 'none';
    window.popModal();
    modalGroupCopy = null;

    if (window._groupModalOnSave) {
        window._groupModalOnSave();
        window._groupModalOnSave = null;
    }
};

document.getElementById('modalCancelBtn').onclick = () => {
    modalGroupCopy = null;
    document.getElementById('groupModal').style.display = 'none';
    window.popModal();
    window._groupModalOnSave = null;
};

// Create new group
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
        topic: 'general',
        priority: 'medium',
        section: window.sections[0] || ''
    };
    await window.apiPost(`/api/models/${window.currentModel}/groups`, newGroup);
    await window.loadGroupsAndSections();
}

document.getElementById('addGroupBtn').onclick = createNewGroup;
document.getElementById('createFirstGroupBtn').onclick = createNewGroup;

document.getElementById('groupSearch').addEventListener('input', filterAndSortGroups);
document.getElementById('sectionFilter').onchange = filterAndSortGroups;
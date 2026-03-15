// ========== Modal Stack Management ==========
let modalStack = [];

window.pushModal = function(modalId) {
    if (!modalStack.includes(modalId)) {
        const wasEmpty = modalStack.length === 0;
        modalStack.push(modalId);
        updateModalBackdrops();

        const modal = document.getElementById(modalId);
        if (!modal) return;

        if (wasEmpty) {
            // First modal: animate in
            modal.classList.remove('no-transition');
            modal.classList.add('visible');
        } else {
            // Subsequent modal: appear instantly
            modal.classList.add('no-transition');
            modal.classList.add('visible');
            // Force reflow to skip transition
            void modal.offsetHeight;
            modal.classList.remove('no-transition');
        }
    }
};

window.popModal = function() {
    const closingId = modalStack.pop();
    updateModalBackdrops();

    if (closingId) {
        const modal = document.getElementById(closingId);
        if (!modal) return;

        const stillOpen = modalStack.length > 0;
        if (stillOpen) {
            // There are still modals open: disappear instantly
            modal.classList.add('no-transition');
            modal.classList.remove('visible');
            void modal.offsetHeight;
            modal.classList.remove('no-transition');
        } else {
            // Last modal: animate out
            modal.classList.remove('visible');
        }
    }
};

function updateModalBackdrops() {
    const modals = ['groupModal', 'treeModal', 'simpleModal'];
    modals.forEach(id => {
        const modal = document.getElementById(id);
        if (!modal) return;

        const stackIndex = modalStack.indexOf(id);
        if (stackIndex !== -1) {
            const baseZ = 1000;
            const topZ = baseZ + modalStack.length;
            if (stackIndex === modalStack.length - 1) {
                modal.style.zIndex = topZ;
                modal.classList.remove('modal-backdrop-hidden');
            } else {
                modal.style.zIndex = baseZ + stackIndex + 1;
                modal.classList.add('modal-backdrop-hidden');
            }
        } else {
            modal.style.zIndex = 1000;
            modal.classList.add('modal-backdrop-hidden');
        }
    });
}

// ========== Modal Helpers ==========
window.showSimpleModal = function(title, fields, onSave, buttonText = 'Save') {
    const modal = document.getElementById('simpleModal');
    const content = document.getElementById('simpleModalContent');
    let html = `<h2>${title}</h2>`;
    html += `<div id="simpleModalError" style="color: #ff6b9d; margin-bottom: 16px; display: none;"></div>`;
    fields.forEach(f => {
        if (f.type === 'textarea') {
            html += `<textarea id="simple_${f.name}" placeholder="${f.label}">${f.value || ''}</textarea>`;
        } else {
            html += `<input type="text" id="simple_${f.name}" placeholder="${f.label}" value="${f.value || ''}">`;
        }
    });
    html += `<div class="modal-actions">
                <button class="save" id="simpleSaveBtn">${buttonText}</button>
                <button class="cancel" id="simpleCancelBtn">Cancel</button>
            </div>`;
    content.innerHTML = html;
    window.pushModal('simpleModal');

    document.getElementById('simpleCancelBtn').onclick = () => {
        window.popModal();
    };
    document.getElementById('simpleSaveBtn').onclick = async () => {
        const values = {};
        fields.forEach(f => values[f.name] = document.getElementById(`simple_${f.name}`).value);
        const errorDiv = document.getElementById('simpleModalError');
        errorDiv.style.display = 'none';
        try {
            await onSave(values, errorDiv);
            if (errorDiv.style.display === 'none') {
                window.popModal();   // success – close
            }
        } catch (err) {
            errorDiv.textContent = err.message || 'An error occurred';
            errorDiv.style.display = 'block';
        }
    };
};

window.showConfirmModal = function(message, onConfirm) {
    const modal = document.getElementById('simpleModal');
    const content = document.getElementById('simpleModalContent');
    content.innerHTML = `
        <h2>Confirm</h2>
        <p style="margin: 20px 0; color: #ccc;">${message}</p>
        <div class="modal-actions">
            <button class="save" id="confirmYesBtn">Yes</button>
            <button class="cancel" id="confirmNoBtn">No</button>
        </div>
    `;
    window.pushModal('simpleModal');

    document.getElementById('confirmYesBtn').onclick = () => {
        window.popModal();
        onConfirm();
    };
    document.getElementById('confirmNoBtn').onclick = () => {
        window.popModal();
    };
};
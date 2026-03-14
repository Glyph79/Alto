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
    modal.style.display = 'flex';

    document.getElementById('simpleCancelBtn').onclick = () => { modal.style.display = 'none'; };
    document.getElementById('simpleSaveBtn').onclick = () => {
        const values = {};
        fields.forEach(f => values[f.name] = document.getElementById(`simple_${f.name}`).value);
        const errorDiv = document.getElementById('simpleModalError');
        errorDiv.style.display = 'none';
        onSave(values, errorDiv);
    };
};

window.showConfirmModal = function(message, onConfirm) {
    const modal = document.getElementById('simpleModal');
    const content = document.getElementById('simpleModalContent');
    content.innerHTML = `
        <h2>Confirm</h2>
        <p style="margin: 20px 0; color: #ccc;">${message}</p>
        <div class="modal-actions">
            <button class="cancel" id="confirmNoBtn">No</button>
            <button class="save" id="confirmYesBtn">Yes</button>
        </div>
    `;
    modal.style.display = 'flex';

    document.getElementById('confirmNoBtn').onclick = () => { modal.style.display = 'none'; };
    document.getElementById('confirmYesBtn').onclick = () => {
        modal.style.display = 'none';
        onConfirm();
    };
};
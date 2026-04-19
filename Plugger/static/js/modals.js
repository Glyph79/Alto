export function escapeHtml(str) {
    if (!str) return '';
    return str.replace(/[&<>]/g, function(m) {
        if (m === '&') return '&amp;';
        if (m === '<') return '&lt;';
        if (m === '>') return '&gt;';
        return m;
    });
}

export function showModal(id) {
    const el = document.getElementById(id);
    if (el) el.classList.add('visible');
}

export function hideModal(id) {
    const el = document.getElementById(id);
    if (el) el.classList.remove('visible');
}

export function showAlertModal(title, message) {
    const modal = document.getElementById('simpleModal');
    const content = document.getElementById('simpleModalContent');
    content.innerHTML = `
        <h2>${escapeHtml(title)}</h2>
        <p style="margin: 20px 0;">${escapeHtml(message)}</p>
        <div class="modal-actions">
            <button class="save" id="alertOkBtn">OK</button>
        </div>
    `;
    showModal('simpleModal');
    document.getElementById('alertOkBtn').onclick = () => hideModal('simpleModal');
}

export function showConfirmModal(message, onConfirm) {
    const modal = document.getElementById('simpleModal');
    const content = document.getElementById('simpleModalContent');
    content.innerHTML = `
        <h2>Confirm</h2>
        <p style="margin: 20px 0;">${escapeHtml(message)}</p>
        <div class="modal-actions">
            <button class="cancel" id="confirmCancel">Cancel</button>
            <button class="save" id="confirmOk">OK</button>
        </div>
    `;
    showModal('simpleModal');
    document.getElementById('confirmCancel').onclick = () => hideModal('simpleModal');
    document.getElementById('confirmOk').onclick = () => {
        hideModal('simpleModal');
        if (onConfirm) onConfirm();
    };
}

export function showTextInputModal(title, initialValue, onSave) {
    const modal = document.getElementById('simpleModal');
    const content = document.getElementById('simpleModalContent');
    content.innerHTML = `
        <h2>${escapeHtml(title)}</h2>
        <input type="text" id="modalInput" value="${escapeHtml(initialValue)}" style="width:100%; margin:16px 0;">
        <div class="modal-actions">
            <button class="cancel" id="modalCancel">Cancel</button>
            <button class="save" id="modalSave">Save</button>
        </div>
    `;
    showModal('simpleModal');
    const input = document.getElementById('modalInput');
    document.getElementById('modalSave').onclick = () => {
        const val = input.value.trim();
        if (val) onSave(val);
        hideModal('simpleModal');
    };
    document.getElementById('modalCancel').onclick = () => hideModal('simpleModal');
    input.focus();
}
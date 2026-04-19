import { api } from '../lib/core/api.js';
import { dom } from '../lib/core/dom.js';

let notificationElement = null;

export async function checkLegacyModels() {
    try {
        const response = await api.get('/api/legacy/scan');
        const legacy = response.legacy_models;
        if (!legacy || legacy.length === 0) return;
        showNotification(legacy, response.paths);
    } catch (err) {
        console.error('Failed to scan legacy models:', err);
    }
}

function showNotification(modelNames, paths) {
    if (notificationElement) notificationElement.remove();
    notificationElement = dom.createElement('div', { class: 'legacy-notification' }, [
        dom.createElement('div', { class: 'notification-header' }, [
            dom.createElement('span', {}, ['⚠️ Legacy models detected']),
            dom.createElement('button', { class: 'close-btn' }, ['×']),
        ]),
        dom.createElement('div', { class: 'notification-body' }, [
            dom.createElement('p', {}, ['The following models are in the old format (.db) and need to be converted:']),
            dom.createElement('ul', {}, modelNames.map(name => dom.createElement('li', {}, [name]))),
            dom.createElement('div', { class: 'notification-actions' }, [
                dom.createElement('label', {}, [
                    dom.createElement('input', { type: 'checkbox', id: 'backupCheckbox', checked: true }),
                    ' Backup original files to backup_models/',
                ]),
                dom.createElement('button', { id: 'convertLegacyBtn', class: 'convert-btn' }, ['Convert Now']),
            ]),
            dom.createElement('div', { id: 'conversionProgress', style: 'display:none; margin-top:12px;' }, [
                dom.createElement('progress', { id: 'progressBar', value: 0, max: 100, style: 'width:100%;' }),
                dom.createElement('span', { id: 'progressText' }, ['']),
            ]),
        ]),
    ]);
    document.body.appendChild(notificationElement);

    const closeBtn = notificationElement.querySelector('.close-btn');
    closeBtn.addEventListener('click', () => notificationElement.remove());

    const convertBtn = notificationElement.querySelector('#convertLegacyBtn');
    convertBtn.addEventListener('click', async () => {
        const backup = document.getElementById('backupCheckbox').checked;
        convertBtn.disabled = true;
        convertBtn.textContent = 'Converting...';
        const progressDiv = document.getElementById('conversionProgress');
        progressDiv.style.display = 'block';
        const progressBar = document.getElementById('progressBar');
        const progressText = document.getElementById('progressText');

        const startResponse = await api.post('/api/legacy/convert', { paths, backup });
        if (startResponse.status !== 'started') {
            alert('Failed to start conversion');
            return;
        }
        const pollInterval = setInterval(async () => {
            const status = await api.get('/api/legacy/status');
            if (!status.running) {
                clearInterval(pollInterval);
                progressBar.value = 100;
                progressText.textContent = `Completed ${status.completed} of ${status.total}.`;
                if (status.failed.length > 0) {
                    progressText.textContent += ` Failed: ${status.failed.map(f => f.file.split('/').pop()).join(', ')}`;
                }
                convertBtn.remove();
                const closeAll = dom.createElement('button', { class: 'close-notification' }, ['Close']);
                closeAll.addEventListener('click', () => notificationElement.remove());
                progressDiv.appendChild(closeAll);
                if (window.managers && window.managers.models) {
                    window.managers.models.load();
                }
            } else {
                const percent = (status.completed / status.total) * 100;
                progressBar.value = percent;
                progressText.textContent = `Converting... ${status.completed}/${status.total}`;
            }
        }, 1000);
    });
}
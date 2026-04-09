import { modal } from '../lib/ui/modal.js';
import { api } from '../lib/core/api.js';

export async function showConverterSettingsModal() {
    const settings = await api.get('/api/converter/settings');
    
    const content = document.createElement('div');
    
    const formRow1 = document.createElement('div');
    formRow1.className = 'form-row';
    const label1 = document.createElement('label');
    label1.textContent = 'Batch size (items per file)';
    formRow1.appendChild(label1);
    const slider = document.createElement('input');
    slider.type = 'range';
    slider.id = 'batchSizeSlider';
    slider.min = '10';
    slider.max = '500';
    slider.step = '10';
    slider.value = settings.batch_size;
    formRow1.appendChild(slider);
    const markersDiv = document.createElement('div');
    markersDiv.style.display = 'flex';
    markersDiv.style.justifyContent = 'space-between';
    markersDiv.style.marginTop = '4px';
    [10, 100, 200, 300, 400, 500].forEach(val => {
        const span = document.createElement('span');
        span.textContent = val;
        markersDiv.appendChild(span);
    });
    formRow1.appendChild(markersDiv);
    const currentDiv = document.createElement('div');
    currentDiv.style.marginTop = '8px';
    const currentSpan = document.createElement('span');
    currentSpan.textContent = 'Current: ';
    currentDiv.appendChild(currentSpan);
    const valueSpan = document.createElement('span');
    valueSpan.id = 'batchSizeValue';
    valueSpan.textContent = settings.batch_size;
    currentDiv.appendChild(valueSpan);
    formRow1.appendChild(currentDiv);
    const small1 = document.createElement('small');
    small1.style.cssText = 'color:#888; display: block; margin-top: 8px;';
    small1.textContent = 'Number of items per JSON batch file. Lower = less memory, higher = faster.';
    formRow1.appendChild(small1);
    content.appendChild(formRow1);
    
    // "Create missing topics/sections" checkbox removed – always enabled
    
    slider.addEventListener('input', () => {
        valueSpan.textContent = slider.value;
    });
    
    modal.show({
        title: 'Converter Settings',
        content,
        actions: [
            { label: 'Cancel', variant: 'cancel' },
            { label: 'Save', variant: 'save', onClick: async () => {
                const newSettings = {
                    batch_size: parseInt(slider.value, 10),
                    // create_missing is always true, no need to send
                };
                await api.post('/api/converter/settings', newSettings);
                modal.closeAll();
            } }
        ],
        size: 'medium'
    });
}
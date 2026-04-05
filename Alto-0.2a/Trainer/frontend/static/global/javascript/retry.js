// retry.js – universal retry and inline loading (no dead code)

window.RETRY_CONFIG = {
    maxAttempts: 3,
    baseDelayMs: 200,
    loadingDelayMs: 300,
    backoffFactor: 2,
};

function delay(ms) {
    return new Promise(resolve => setTimeout(resolve, ms));
}

window.retryOperation = async function(operation, options = {}) {
    const config = { ...window.RETRY_CONFIG, ...options };
    let lastError;
    for (let attempt = 1; attempt <= config.maxAttempts; attempt++) {
        try {
            return await operation();
        } catch (err) {
            lastError = err;
            if (attempt === config.maxAttempts) break;
            const wait = config.baseDelayMs * Math.pow(config.backoffFactor, attempt - 1);
            await delay(wait);
        }
    }
    throw lastError;
};

window.showInlineLoading = function(container, text = "Loading", delayMs = null) {
    const delayTime = delayMs !== null ? delayMs : window.RETRY_CONFIG.loadingDelayMs;
    let timeout = null;
    let loadingElement = null;

    const clear = () => {
        if (timeout) {
            clearTimeout(timeout);
            timeout = null;
        }
        if (loadingElement && loadingElement.parentNode) {
            loadingElement.remove();
            loadingElement = null;
        }
    };

    timeout = setTimeout(() => {
        loadingElement = document.createElement('div');
        loadingElement.className = 'inline-loading';
        loadingElement.innerHTML = `
            <div class="inline-spinner"></div>
            <span>${text}...</span>
        `;
        container.appendChild(loadingElement);
        timeout = null;
    }, delayTime);

    return { clear };
};

window.disableButtonsInContainer = function(container) {
    const buttons = container.querySelectorAll('button, .add-btn, .save, #modalSaveBtn, #modalAddQuestionBtn, #modalAddAnswerBtn, #modalEditFollowupsBtn, #treeAddQuestionBtn, #treeAddAnswerBtn, #addRootBtn, #addChildBtn, #editNodeBtn, #deleteNodeBtn');
    buttons.forEach(btn => {
        if (btn.classList.contains('cancel') || btn.id === 'modalCancelBtn' || btn.id === 'treeModalCancelBtn' || btn.id === 'editTopicCancelBtn' || btn.id === 'deleteCancelBtn') {
            return;
        }
        btn.disabled = true;
        btn.setAttribute('data-was-disabled', 'true');
    });
};

window.enableButtonsInContainer = function(container) {
    const buttons = container.querySelectorAll('button, .add-btn, .save, #modalSaveBtn, #modalAddQuestionBtn, #modalAddAnswerBtn, #modalEditFollowupsBtn, #treeAddQuestionBtn, #treeAddAnswerBtn, #addRootBtn, #addChildBtn, #editNodeBtn, #deleteNodeBtn');
    buttons.forEach(btn => {
        if (btn.getAttribute('data-was-disabled') === 'true') {
            btn.disabled = false;
            btn.removeAttribute('data-was-disabled');
        }
    });
};

window.showInlineListRetry = function(listElement, itemType, retryCallback) {
    listElement.innerHTML = '';
    const li = document.createElement('li');
    li.className = 'retry-list-item';
    li.innerHTML = `
        <span style="color:#ffaa66;">⚠️ Failed to load ${itemType}.</span>
        <button class="retry-list-btn" style="margin-left:12px; background:#6c63ff; border:none; border-radius:4px; padding:4px 12px; color:white; cursor:pointer;">Retry</button>
    `;
    const btn = li.querySelector('.retry-list-btn');
    btn.addEventListener('click', async (e) => {
        e.preventDefault();
        btn.disabled = true;
        btn.textContent = '...';
        try {
            await retryCallback();
        } catch (err) {
            btn.disabled = false;
            btn.textContent = 'Retry';
            const span = li.querySelector('span');
            span.textContent = `⚠️ Failed: ${err.message}`;
        }
    });
    listElement.appendChild(li);
};

// Only used by tree editor error display
window.showRetryError = function(container, message, retryCallback) {
    const existing = container.querySelector('.retry-error');
    if (existing) existing.remove();

    const errorDiv = document.createElement('div');
    errorDiv.className = 'retry-error';
    errorDiv.innerHTML = `
        <div class="error-icon">⚠️</div>
        <div class="error-message">${escapeHtml(message)}</div>
        <button class="retry-btn">Retry</button>
    `;
    const btn = errorDiv.querySelector('.retry-btn');
    btn.addEventListener('click', async (e) => {
        e.preventDefault();
        btn.disabled = true;
        btn.textContent = 'Retrying...';
        try {
            await retryCallback();
            errorDiv.remove();
        } catch (err) {
            btn.disabled = false;
            btn.textContent = 'Retry';
            const msgDiv = errorDiv.querySelector('.error-message');
            msgDiv.textContent = `Failed: ${err.message}`;
        }
    });
    container.appendChild(errorDiv);
    return errorDiv;
};

function escapeHtml(str) {
    if (!str) return '';
    return str.replace(/[&<>]/g, function(m) {
        if (m === '&') return '&amp;';
        if (m === '<') return '&lt;';
        if (m === '>') return '&gt;';
        return m;
    });
}

// Inject required styles once
if (!document.querySelector('#retry-styles')) {
    const style = document.createElement('style');
    style.id = 'retry-styles';
    style.textContent = `
        .retry-error {
            display: flex;
            flex-direction: column;
            align-items: center;
            gap: 12px;
            background: #2d2d5a;
            border: 1px solid #ff6b9d;
            border-radius: 8px;
            padding: 20px;
            margin: 20px;
            text-align: center;
            color: #ffe0e0;
        }
        .retry-error .error-icon { font-size: 32px; }
        .retry-error .error-message { font-size: 0.9rem; }
        .retry-error .retry-btn {
            background: #6c63ff;
            color: white;
            border: none;
            padding: 8px 16px;
            border-radius: 6px;
            cursor: pointer;
            font-size: 0.9rem;
        }
        .retry-error .retry-btn:hover { background: #5a52d5; }
        .retry-error .retry-btn:disabled { opacity: 0.6; cursor: not-allowed; }

        .inline-loading {
            display: flex;
            align-items: center;
            gap: 8px;
            padding: 8px;
            background: transparent;
            color: #aaa;
            font-size: 0.85rem;
        }
        .inline-spinner {
            width: 16px;
            height: 16px;
            border: 2px solid #6c63ff;
            border-top-color: transparent;
            border-radius: 50%;
            animation: spin 0.6s linear infinite;
        }
        @keyframes spin { to { transform: rotate(360deg); } }

        .retry-list-item {
            display: flex;
            align-items: center;
            justify-content: center;
            padding: 12px;
            background: #2d2d5a;
            border-radius: 6px;
            color: #ffe0e0;
        }
        .retry-list-btn {
            background: #6c63ff;
            border: none;
            border-radius: 4px;
            padding: 4px 12px;
            color: white;
            cursor: pointer;
            font-size: 0.8rem;
        }
        .retry-list-btn:hover { background: #5a52d5; }
        .retry-list-btn:disabled { opacity: 0.6; cursor: not-allowed; }
    `;
    document.head.appendChild(style);
}
// retry.js – universal retry, inline loading, and error display

// ----- Configuration (adjust globally) -----
window.RETRY_CONFIG = {
    maxAttempts: 3,
    baseDelayMs: 200,
    loadingDelayMs: 300,
    backoffFactor: 2,
};

function delay(ms) {
    return new Promise(resolve => setTimeout(resolve, ms));
}

/**
 * Retry an async operation with exponential backoff.
 */
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

/**
 * Show a simple inline loading indicator inside a list or container.
 * Returns an object with a `clear()` method to remove it.
 */
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

/**
 * Disable all action buttons inside a container, but NEVER disable cancel/close buttons.
 */
window.disableButtonsInContainer = function(container) {
    // Select all buttons that are NOT cancel/close
    const buttons = container.querySelectorAll('button, .add-btn, .save, #modalSaveBtn, #modalAddQuestionBtn, #modalAddAnswerBtn, #modalEditFollowupsBtn, #treeAddQuestionBtn, #treeAddAnswerBtn, #addRootBtn, #addChildBtn, #editNodeBtn, #deleteNodeBtn');
    buttons.forEach(btn => {
        // Skip any button that is clearly a cancel or close action
        if (btn.classList.contains('cancel') || btn.id === 'modalCancelBtn' || btn.id === 'treeModalCancelBtn' || btn.id === 'editTopicCancelBtn' || btn.id === 'deleteCancelBtn') {
            return;
        }
        btn.disabled = true;
        btn.setAttribute('data-was-disabled', 'true');
    });
};

/**
 * Re‑enable buttons that were previously disabled.
 */
window.enableButtonsInContainer = function(container) {
    const buttons = container.querySelectorAll('button, .add-btn, .save, #modalSaveBtn, #modalAddQuestionBtn, #modalAddAnswerBtn, #modalEditFollowupsBtn, #treeAddQuestionBtn, #treeAddAnswerBtn, #addRootBtn, #addChildBtn, #editNodeBtn, #deleteNodeBtn');
    buttons.forEach(btn => {
        if (btn.getAttribute('data-was-disabled') === 'true') {
            btn.disabled = false;
            btn.removeAttribute('data-was-disabled');
        }
    });
};

/**
 * Show an inline retry button inside a list (replaces loading text).
 */
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

// ----- Full‑size error prompt (only for tree editor) -----
function escapeHtml(str) {
    if (!str) return '';
    return str.replace(/[&<>]/g, function(m) {
        if (m === '&') return '&amp;';
        if (m === '<') return '&lt;';
        if (m === '>') return '&gt;';
        return m;
    });
}

window.showRetryError = function(container, message, retryCallback) {
    window.clearRetryError(container);
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

window.showSimpleRetry = function(container, message, retryCallback) {
    window.clearRetryError(container);
    const wrapper = document.createElement('div');
    wrapper.className = 'simple-retry';
    wrapper.innerHTML = `
        <span class="simple-retry-message">⚠️ ${escapeHtml(message)}</span>
        <button class="simple-retry-btn">Retry</button>
    `;
    const btn = wrapper.querySelector('.simple-retry-btn');
    btn.addEventListener('click', async (e) => {
        e.preventDefault();
        btn.disabled = true;
        btn.textContent = '...';
        try {
            await retryCallback();
            wrapper.remove();
        } catch (err) {
            btn.disabled = false;
            btn.textContent = 'Retry';
            const msgSpan = wrapper.querySelector('.simple-retry-message');
            msgSpan.textContent = `⚠️ Failed: ${err.message}`;
        }
    });
    container.appendChild(wrapper);
    return wrapper;
};

window.clearRetryError = function(container) {
    const existing = container.querySelector('.retry-error, .simple-retry');
    if (existing) existing.remove();
};

// Inject styles once
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

        .simple-retry {
            display: flex;
            align-items: center;
            justify-content: center;
            gap: 12px;
            background: #2d2d5a;
            border: 1px solid #ffaa66;
            border-radius: 6px;
            padding: 8px 16px;
            margin: 16px;
            font-size: 0.85rem;
            color: #ffe0e0;
        }
        .simple-retry-message { color: #ffaa66; }
        .simple-retry-btn {
            background: #6c63ff;
            color: white;
            border: none;
            padding: 4px 12px;
            border-radius: 4px;
            cursor: pointer;
            font-size: 0.8rem;
        }
        .simple-retry-btn:hover { background: #5a52d5; }
        .simple-retry-btn:disabled { opacity: 0.6; cursor: not-allowed; }

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
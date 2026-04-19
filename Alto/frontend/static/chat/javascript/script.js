// DOM elements
const chat = document.getElementById('chat');
const input = document.getElementById('message');
const sendBtn = document.querySelector('button[onclick="sendMessage(false)"]');
const typingHTML = '<div class="typing-indicator"><span></span><span></span><span></span></div>';

// State
let lastUserMessage = '';
let lastErrorBubbles = []; // [bubble1, bubble2]
let isWaiting = false;

// Constants
const SCROLL_THRESHOLD = 5;
const ERROR_TITLE = 'Network error';
const ERROR_DETAIL = 'Unable to reach server. Please check your internet connection or server status.';

// Helper to escape HTML and convert newlines to <br>
function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

function formatForHTML(text) {
    return escapeHtml(text).replace(/\n/g, '<br>');
}

// Logout
document.getElementById('logoutBtn').addEventListener('click', async () => {
    await fetch('/api/logout', { method: 'POST' });
    window.location.href = '/';
});

// Scroll helpers
const isAtBottom = () => {
    const scrollPos = chat.scrollTop + chat.clientHeight;
    return chat.scrollHeight - scrollPos <= SCROLL_THRESHOLD;
};

const scrollToBottom = () => chat.scrollTop = chat.scrollHeight;

const maybeScroll = (wasAtBottom) => {
    if (wasAtBottom) scrollToBottom();
};

// Message addition
function addMessage(type, content) {
    const wasAtBottom = isAtBottom();
    const div = document.createElement('div');
    div.className = `message ${type}`;
    div.innerHTML = content;
    chat.appendChild(div);
    maybeScroll(wasAtBottom);
    return div;
}

// Waiting state
function setWaiting(waiting) {
    isWaiting = waiting;
    sendBtn.disabled = waiting;
}

// Error UI creation
function createErrorBubbles(message) {
    const wasAtBottom = isAtBottom();
    const bubbles = [];

    // First bubble: simple network error
    const titleBubble = document.createElement('div');
    titleBubble.className = 'message bot';
    titleBubble.textContent = ERROR_TITLE;
    bubbles.push(titleBubble);

    // Second bubble: detailed error + retry button
    const detailBubble = document.createElement('div');
    detailBubble.className = 'message bot red';

    const detail = document.createElement('div');
    detail.className = 'error-detail';
    detail.textContent = ERROR_DETAIL;

    const btn = document.createElement('button');
    btn.className = 'retry-btn';
    btn.textContent = 'Try again';
    btn.setAttribute('data-message', message.replace(/"/g, '&quot;'));

    btn.addEventListener('click', function onClick(e) {
        e.preventDefault();
        if (btn.disabled) return;
        btn.disabled = true;

        // Remove detail bubble
        if (bubbles[1]) bubbles[1].remove();

        // Convert title bubble to typing indicator
        titleBubble.innerHTML = typingHTML;
        titleBubble.className = 'message bot';

        // Retry
        sendMessage(true, titleBubble);
    });

    detailBubble.appendChild(detail);
    detailBubble.appendChild(btn);
    bubbles.push(detailBubble);

    // Append both
    bubbles.forEach(b => chat.appendChild(b));
    maybeScroll(wasAtBottom);

    return bubbles;
}

// Core send function
async function sendMessage(isRetry = false, reuseBubble = null) {
    if (isWaiting) return;

    // Remove existing detail bubble on manual send
    if (!isRetry && lastErrorBubbles.length === 2) {
        const wasAtBottom = isAtBottom();
        lastErrorBubbles[1].remove();
        lastErrorBubbles = [];
        maybeScroll(wasAtBottom);
    }

    const message = isRetry ? lastUserMessage : input.value.trim();
    if (!message) return;

    if (!isRetry) {
        input.value = '';
        addMessage('user', message);
        lastUserMessage = message;
    }

    setWaiting(true);

    const botDiv = reuseBubble || addMessage('bot', typingHTML);

    try {
        const response = await fetch('/chat', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ message })
        });

        if (!response.ok) {
            // Check if it's JSON with invalid_user error
            const contentType = response.headers.get('content-type');
            if (contentType && contentType.includes('application/json')) {
                const errorData = await response.json();
                if (errorData.error === 'invalid_user') {
                    // Redirect to login
                    window.location.href = '/';
                    return;
                }
            }
            botDiv.remove();
            const newBubbles = createErrorBubbles(message);
            lastErrorBubbles = newBubbles;
            setWaiting(false);
            return;
        }

        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let firstChunk = true;

        while (true) {
            const { done, value } = await reader.read();
            if (done) break;

            const chunk = decoder.decode(value);
            const wasAtBottom = isAtBottom();

            if (firstChunk) {
                botDiv.innerHTML = '';
                firstChunk = false;
            }
            // Convert newlines to <br> and escape HTML
            botDiv.insertAdjacentHTML('beforeend', formatForHTML(chunk));

            maybeScroll(wasAtBottom);
        }

        setWaiting(false);
    } catch (err) {
        botDiv.remove();
        const newBubbles = createErrorBubbles(message);
        lastErrorBubbles = newBubbles;
        setWaiting(false);
    }
}

// Event listeners
input.addEventListener('keypress', e => {
    if (e.key === 'Enter') {
        e.preventDefault();
        if (!isWaiting) sendMessage(false);
    }
});

sendBtn.onclick = () => {
    if (!isWaiting) sendMessage(false);
};
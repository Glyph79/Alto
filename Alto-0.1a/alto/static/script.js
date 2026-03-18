const chat = document.getElementById('chat');
const input = document.getElementById('message');
const sendBtn = document.querySelector('button[onclick="sendMessage(false)"]');
const typingHTML = '<div class="typing-indicator"><span></span><span></span><span></span></div>';

let lastUserMessage = '';
let lastErrorBubbles = []; // [bubble1, bubble2]
let isWaiting = false;

const scrollToBottom = () => chat.scrollTop = chat.scrollHeight;

function setWaiting(waiting) {
    isWaiting = waiting;
    sendBtn.disabled = waiting;
    // Input remains enabled, but sending is prevented by isWaiting check
}

function addMessage(type, content) {
    const div = document.createElement('div');
    div.className = `message ${type}`;
    div.innerHTML = content;
    chat.appendChild(div);
    scrollToBottom();
    return div;
}

function createErrorBubbles(message) {
    const bubbles = [];

    // First bubble: simple network error (standard bot style)
    const errorTitleBubble = document.createElement('div');
    errorTitleBubble.className = 'message bot';
    errorTitleBubble.textContent = 'Network error';
    bubbles.push(errorTitleBubble);

    // Second bubble: detailed message + retry button (red)
    const detailBubble = document.createElement('div');
    detailBubble.className = 'message bot red';

    const detail = document.createElement('div');
    detail.className = 'error-detail';
    detail.textContent = 'Unable to reach server. Please check your internet connection or server status.';

    const btn = document.createElement('button');
    btn.className = 'retry-btn';
    btn.textContent = 'Try again';
    btn.setAttribute('data-message', message.replace(/"/g, '&quot;'));
    btn.addEventListener('click', (e) => {
        e.preventDefault();
        if (btn.disabled) return;
        btn.disabled = true;

        // Remove the red detail bubble (keeps first bubble)
        if (bubbles[1]) bubbles[1].remove();
        // Clear first bubble and turn it into a typing indicator
        const firstBubble = bubbles[0];
        firstBubble.innerHTML = typingHTML;
        firstBubble.className = 'message bot'; // ensure it's a bot bubble

        // Retry sending
        sendMessage(true, firstBubble);
    });

    detailBubble.appendChild(detail);
    detailBubble.appendChild(btn);
    bubbles.push(detailBubble);

    return bubbles;
}

async function sendMessage(isRetry = false, reuseBubble = null) {
    if (isWaiting) return;

    // If this is a new message (not a retry), remove only the detail bubble if it exists
    if (!isRetry && lastErrorBubbles.length === 2) {
        // Remove the second bubble (red detail bubble)
        lastErrorBubbles[1].remove();
        // Clear the array – the first bubble stays as a static message
        lastErrorBubbles = [];
    }

    const message = isRetry ? lastUserMessage : input.value.trim();
    if (!message) return;

    if (!isRetry) {
        input.value = '';
        addMessage('user', message);
        lastUserMessage = message;
    }

    setWaiting(true);

    // If we're retrying, we already have a bubble to reuse (passed as reuseBubble)
    let botDiv;
    if (isRetry && reuseBubble) {
        botDiv = reuseBubble;
    } else {
        botDiv = addMessage('bot', typingHTML);
    }

    try {
        const response = await fetch('/chat', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ message })
        });

        if (!response.ok) {
            // If this was a retry and we reused a bubble, we need to replace it with error UI
            if (isRetry && reuseBubble) {
                reuseBubble.remove(); // remove the typing bubble
                // Create fresh error UI
                const newBubbles = createErrorBubbles(message);
                newBubbles.forEach(b => chat.appendChild(b));
                lastErrorBubbles = newBubbles;
            } else {
                // First failure: replace typing indicator with error UI
                botDiv.remove();
                const newBubbles = createErrorBubbles(message);
                newBubbles.forEach(b => chat.appendChild(b));
                lastErrorBubbles = newBubbles;
            }
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
            if (firstChunk) {
                botDiv.innerHTML = '';
                firstChunk = false;
            }
            botDiv.innerHTML += chunk;
            scrollToBottom();
        }

        setWaiting(false);
    } catch (err) {
        // Network error – same handling as HTTP error
        if (isRetry && reuseBubble) {
            reuseBubble.remove();
            const newBubbles = createErrorBubbles(message);
            newBubbles.forEach(b => chat.appendChild(b));
            lastErrorBubbles = newBubbles;
        } else {
            botDiv.remove();
            const newBubbles = createErrorBubbles(message);
            newBubbles.forEach(b => chat.appendChild(b));
            lastErrorBubbles = newBubbles;
        }
        setWaiting(false);
    }
}

input.addEventListener('keypress', e => {
    if (e.key === 'Enter') {
        e.preventDefault();
        if (!isWaiting) sendMessage(false);
    }
});

// Also update the send button's onclick handler
sendBtn.onclick = () => {
    if (!isWaiting) sendMessage(false);
};
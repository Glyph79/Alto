const chat = document.getElementById('chat');
const input = document.getElementById('message');
const typingHTML = '<div class="typing-indicator"><span></span><span></span><span></span></div>';

const scrollToBottom = () => chat.scrollTop = chat.scrollHeight;

function addMessage(type, content) {
    const div = document.createElement('div');
    div.className = `message ${type}`;
    div.innerHTML = content;
    chat.appendChild(div);
    scrollToBottom();
    return div;
}

async function sendMessage() {
    const msg = input.value.trim();
    if (!msg) return;
    
    input.value = '';
    addMessage('user', msg);
    const botDiv = addMessage('bot', typingHTML);

    try {
        const response = await fetch('/chat', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ message: msg })
        });

        if (!response.ok) {
            botDiv.innerHTML = 'Error: Could not get response.';
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
    } catch (err) {
        botDiv.innerHTML = 'Network error. Please try again.';
    }
}

input.addEventListener('keypress', e => {
    if (e.key === 'Enter') {
        e.preventDefault();
        sendMessage();
    }
});
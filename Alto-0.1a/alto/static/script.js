async function sendMessage() {
    const input = document.getElementById('message');
    const msg = input.value.trim();
    if (!msg) return;
    input.value = '';

    const chat = document.getElementById('chat');
    const userDiv = document.createElement('div');
    userDiv.className = 'message user';
    userDiv.textContent = msg;
    chat.appendChild(userDiv);
    chat.scrollTop = chat.scrollHeight;

    const botDiv = document.createElement('div');
    botDiv.className = 'message bot';
    botDiv.innerHTML = '';
    chat.appendChild(botDiv);

    try {
        const response = await fetch('/chat', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ message: msg })
        });

        if (!response.ok) {
            botDiv.textContent = 'Error: Could not get response.';
            return;
        }

        const reader = response.body.getReader();
        const decoder = new TextDecoder();

        while (true) {
            const { done, value } = await reader.read();
            if (done) break;
            const chunk = decoder.decode(value);
            botDiv.innerHTML += chunk;
            chat.scrollTop = chat.scrollHeight;
        }
    } catch (err) {
        botDiv.textContent = 'Network error. Please try again.';
    }
}

document.getElementById('message').addEventListener('keypress', function (e) {
    if (e.key === 'Enter') {
        e.preventDefault();
        sendMessage();
    }
});
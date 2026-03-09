from quart import Quart, request, Response, render_template_string
import layer

app = Quart(__name__)

# Modern minimal UI (same as before)
HTML_PAGE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Alto 0.1a · minimal</title>
    <style>
        * {
            box-sizing: border-box;
            margin: 0;
            padding: 0;
        }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
            background: #ffffff;
            height: 100vh;
            display: flex;
            flex-direction: column;
            color: #1a1a1a;
        }
        .chat-header {
            padding: 16px 20px 8px 20px;
            border-bottom: 1px solid #f0f0f0;
            flex-shrink: 0;
        }
        .chat-header h2 {
            font-size: 1.3rem;
            font-weight: 400;
            color: #000;
            letter-spacing: -0.01em;
        }
        .chat-header p {
            font-size: 0.75rem;
            color: #aaa;
            margin-top: 2px;
            font-weight: 300;
            text-transform: uppercase;
            letter-spacing: 0.3px;
        }
        .messages {
            flex: 1;
            overflow-y: auto;
            padding: 16px 20px;
            display: flex;
            flex-direction: column;
            gap: 12px;
            background: #fff;
        }
        .message {
            max-width: 70%;
            padding: 10px 14px;
            font-size: 0.95rem;
            line-height: 1.4;
            word-wrap: break-word;
            animation: fadeIn 0.15s ease;
            border-radius: 18px;
        }
        @keyframes fadeIn {
            from { opacity: 0; transform: translateY(3px); }
            to { opacity: 1; transform: translateY(0); }
        }
        .message.user {
            background: #e4e4e4;
            color: #1a1a1a;
            align-self: flex-end;
            border-bottom-right-radius: 4px;
        }
        .message.bot {
            background: transparent;
            color: #1a1a1a;
            align-self: flex-start;
            padding-left: 0;
            padding-right: 0;
        }
        .input-area {
            display: flex;
            padding: 12px 20px 20px 20px;
            background: white;
            border-top: 1px solid #f0f0f0;
            gap: 8px;
            flex-shrink: 0;
        }
        #message {
            flex: 1;
            padding: 12px 16px;
            border: none;
            border-radius: 30px;
            font-size: 0.95rem;
            outline: none;
            background: #f4f4f4;
            transition: background 0.2s;
        }
        #message:focus {
            background: #eaeaea;
        }
        button {
            background: none;
            color: #007aff;
            border: none;
            border-radius: 30px;
            padding: 0 16px;
            font-size: 0.95rem;
            font-weight: 500;
            cursor: pointer;
            transition: opacity 0.2s;
            white-space: nowrap;
        }
        button:hover {
            opacity: 0.7;
        }
        button:active {
            opacity: 0.5;
        }
        .messages::-webkit-scrollbar {
            width: 4px;
        }
        .messages::-webkit-scrollbar-track {
            background: transparent;
        }
        .messages::-webkit-scrollbar-thumb {
            background: #ddd;
            border-radius: 20px;
        }
        .messages::-webkit-scrollbar-thumb:hover {
            background: #ccc;
        }
    </style>
</head>
<body>
    <div class="chat-header">
        <h2>Alto 0.1a</h2>
        <p>pipeline · streams</p>
    </div>
    <div class="messages" id="chat"></div>
    <div class="input-area">
        <input type="text" id="message" placeholder="message" autofocus>
        <button onclick="sendMessage()">send</button>
    </div>

    <script>
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

            const response = await fetch('/chat', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ message: msg })
            });

            const reader = response.body.getReader();
            const decoder = new TextDecoder();

            while (true) {
                const { done, value } = await reader.read();
                if (done) break;
                const chunk = decoder.decode(value);
                botDiv.innerHTML += chunk;
                chat.scrollTop = chat.scrollHeight;
            }
        }

        document.getElementById('message').addEventListener('keypress', function (e) {
            if (e.key === 'Enter') {
                e.preventDefault();
                sendMessage();
            }
        });
    </script>
</body>
</html>
"""

@app.route('/')
async def index():
    return await render_template_string(HTML_PAGE)

@app.route('/chat', methods=['POST'])
async def chat():
    data = await request.get_json()
    user_message = data.get('message', '')
    # layer.process_message is a generator; we wrap it in an async generator
    async def generate():
        for chunk in layer.process_message(user_message):
            yield chunk
    return Response(generate(), mimetype='text/plain')

if __name__ == '__main__':
    app.run(debug=True)
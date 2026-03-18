from quart import Quart, request, Response, render_template
import uuid
from alto.layer.layer import process_message

app = Quart(__name__, template_folder='templates', static_folder='static')

@app.route('/')
async def index():
    return await render_template('index.html')

@app.route('/chat', methods=['POST'])
async def chat():
    data = await request.get_json()
    user_message = data.get('message', '').strip()
    if not user_message:
        return Response('', status=400)

    session_id = request.cookies.get('session_id')
    if not session_id:
        session_id = str(uuid.uuid4())

    async def generate():
        async for chunk in process_message(user_message, session_id):
            yield chunk

    response = Response(generate(), mimetype='text/plain')
    response.set_cookie('session_id', session_id)
    return response

if __name__ == '__main__':
    app.run(debug=True)
from quart import Quart, request, Response, send_from_directory, redirect, url_for
import uuid
import json
from alto.layer.layer import process_message
from alto.auth.auth import register_user, authenticate_user, user_exists

app = Quart(__name__, static_folder='static')

# Serve chat page
@app.route('/chat')
async def chat_page():
    return await send_from_directory('static/chat', 'index.html')

# Serve login page (root)
@app.route('/')
async def login_page():
    return await send_from_directory('static/login', 'index.html')

# Serve static files from chat and login subfolders
@app.route('/static/chat/<path:filename>')
async def chat_static(filename):
    return await send_from_directory('static/chat', filename)

@app.route('/static/login/<path:filename>')
async def login_static(filename):
    return await send_from_directory('static/login', filename)

# Authentication endpoints
@app.route('/api/register', methods=['POST'])
async def register():
    data = await request.get_json()
    username = data.get('username')
    password = data.get('password')
    if not username or not password:
        return {"error": "Username and password required"}, 400
    success, message = register_user(username, password)
    if success:
        return {"message": message}, 201
    else:
        return {"error": message}, 400

@app.route('/api/login', methods=['POST'])
async def login():
    data = await request.get_json()
    username = data.get('username')
    password = data.get('password')
    if not username or not password:
        return {"error": "Username and password required"}, 400
    user_id = authenticate_user(username, password)
    if user_id:
        session_id = str(uuid.uuid4())
        response_data = {"message": "Login successful"}
        resp = Response(json.dumps(response_data), status=200, mimetype='application/json')
        resp.set_cookie('session_id', session_id)
        resp.set_cookie('user_id', str(user_id))
        return resp
    else:
        return {"error": "Invalid credentials"}, 401

@app.route('/api/logout', methods=['POST'])
async def logout():
    response_data = {"message": "Logged out"}
    resp = Response(json.dumps(response_data), status=200, mimetype='application/json')
    resp.set_cookie('session_id', '', expires=0)
    resp.set_cookie('user_id', '', expires=0)
    return resp

# Chat endpoint (POST)
@app.route('/chat', methods=['POST'])
async def chat():
    data = await request.get_json()
    user_message = data.get('message', '').strip()
    if not user_message:
        return Response('', status=400)

    session_id = request.cookies.get('session_id')
    if not session_id:
        session_id = str(uuid.uuid4())
    
    user_id = request.cookies.get('user_id')
    if user_id:
        user_id = int(user_id)
        # Validate that the user still exists
        if not user_exists(user_id):
            # Invalid user, clear cookies and return 401 with special flag
            response_data = {"error": "invalid_user"}
            resp = Response(json.dumps(response_data), status=401, mimetype='application/json')
            resp.set_cookie('session_id', '', expires=0)
            resp.set_cookie('user_id', '', expires=0)
            return resp
    else:
        user_id = None

    async def generate():
        async for chunk in process_message(user_message, session_id, user_id):
            yield chunk

    response = Response(generate(), mimetype='text/plain')
    response.set_cookie('session_id', session_id)
    if user_id:
        response.set_cookie('user_id', str(user_id))
    return response

if __name__ == '__main__':
    app.run(debug=True)
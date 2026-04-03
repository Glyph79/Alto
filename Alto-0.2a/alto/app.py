import os
from quart import Quart, request, Response, send_from_directory, redirect, url_for
import uuid
import json
from alto.layer.layer import process_message
from alto.auth.auth import register_user, authenticate_user, user_exists

# Absolute path to the directory containing this file
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Absolute paths to static subdirectories
STATIC_CHAT_DIR = os.path.join(BASE_DIR, 'static', 'chat')
STATIC_LOGIN_DIR = os.path.join(BASE_DIR, 'static', 'login')

# Use absolute static_folder for Quart's default static handling
app = Quart(__name__, static_folder=os.path.join(BASE_DIR, 'static'))

# Serve chat page – only if authenticated
@app.route('/chat')
async def chat_page():
    user_id = request.cookies.get('user_id')
    if user_id and user_id.isdigit():
        if user_exists(int(user_id)):
            return await send_from_directory(STATIC_CHAT_DIR, 'index.html')
    # Not authenticated → redirect to login
    return redirect('/')

# Serve login page (root)
@app.route('/')
async def login_page():
    return await send_from_directory(STATIC_LOGIN_DIR, 'index.html')

# Serve static files from chat and login subfolders
@app.route('/static/chat/<path:filename>')
async def chat_static(filename):
    return await send_from_directory(STATIC_CHAT_DIR, filename)

@app.route('/static/login/<path:filename>')
async def login_static(filename):
    return await send_from_directory(STATIC_LOGIN_DIR, filename)

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

# Optional endpoint for client‑side session checks (e.g., during long‑lived sessions)
@app.route('/api/check-session', methods=['GET'])
async def check_session():
    user_id = request.cookies.get('user_id')
    if user_id and user_id.isdigit():
        if user_exists(int(user_id)):
            return {"valid": True}, 200
    return {"valid": False}, 401

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

# ========== Network Visualizer ==========
@app.route('/network')
async def network_page():
    return await send_from_directory(os.path.join(BASE_DIR, 'static', 'network'), 'index.html')

@app.route('/api/network')
async def network_data():
    from alto.core.ai_engine import _get_db_path
    from alto.config import config
    import sqlite3

    model_name = config.get('DEFAULT', 'default_model')
    db_path = _get_db_path(model_name)
    if not db_path:
        return {"error": f"Model '{model_name}' not found"}, 404

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    nodes = []
    links = []
    node_ids = set()

    def add_node(nid, name, node_type, topic='', section=''):
        if nid in node_ids:
            return
        node_ids.add(nid)
        nodes.append({
            "id": nid,
            "name": name,
            "type": node_type,
            "topic": topic,
            "section": section
        })

    # Groups as nodes
    cur = conn.execute("""
        SELECT g.id, g.group_name, COALESCE(t.name, '') as topic, COALESCE(s.name, '') as section
        FROM groups g
        LEFT JOIN topics t ON g.topic_id = t.id
        LEFT JOIN sections s ON g.section_id = s.id
        ORDER BY g.id
    """)
    groups = []
    for row in cur:
        group_id = f"group_{row['id']}"
        add_node(group_id, row['group_name'], 'group', row['topic'], row['section'])
        groups.append((row['id'], group_id))

    # Follow-up nodes and links
    cur = conn.execute("""
        SELECT id, group_id, parent_id, branch_name
        FROM followup_nodes
        ORDER BY id
    """)
    followup_nodes = {}
    for row in cur:
        node_id = f"node_{row['id']}"
        parent_id = f"node_{row['parent_id']}" if row['parent_id'] else None
        group_id = f"group_{row['group_id']}"
        node_type = 'root' if parent_id is None else 'followup'
        add_node(node_id, row['branch_name'] or 'Unnamed', node_type)
        followup_nodes[row['id']] = (node_id, group_id, parent_id)

    # Create links: group -> root nodes, and parent -> child
    for fn_id, (node_id, group_id, parent_id) in followup_nodes.items():
        if parent_id is None:
            links.append({"source": group_id, "target": node_id})
        else:
            links.append({"source": parent_id, "target": node_id})

    conn.close()
    return {"nodes": nodes, "links": links}

if __name__ == '__main__':
    app.run(debug=True)
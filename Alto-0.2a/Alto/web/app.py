# web/app.py
import sys
import os

# Add the project root to Python's path so that 'web' and 'alto' are importable
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from quart import Quart, request, Response, send_from_directory, redirect
import uuid
import json
from web.layer.layer import process_message
from web.auth.auth import register_user, authenticate_user, user_exists
from alto.config import config
from alto.core.adapters import get_adapter

SERVE_WEBUI = config.getboolean('DEFAULT', 'serve_webui', fallback=True)
FRONTEND_DIR = os.path.join(PROJECT_ROOT, 'frontend')

app = Quart(__name__, static_folder=None)

# ---------- API endpoints (always available) ----------
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
        resp.set_cookie('session_id', session_id, path='/', httponly=False, samesite='Lax', max_age=2592000)
        resp.set_cookie('user_id', str(user_id), path='/', httponly=False, samesite='Lax', max_age=2592000)
        return resp
    else:
        return {"error": "Invalid credentials"}, 401

@app.route('/api/logout', methods=['POST'])
async def logout():
    response_data = {"message": "Logged out"}
    resp = Response(json.dumps(response_data), status=200, mimetype='application/json')
    resp.set_cookie('session_id', '', expires=0, path='/')
    resp.set_cookie('user_id', '', expires=0, path='/')
    return resp

@app.route('/api/check-session', methods=['GET'])
async def check_session():
    user_id = request.cookies.get('user_id')
    if user_id and user_id.isdigit():
        if user_exists(int(user_id)):
            return {"valid": True}, 200
    return {"valid": False}, 401

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
        if not user_exists(user_id):
            response_data = {"error": "invalid_user"}
            resp = Response(json.dumps(response_data), status=401, mimetype='application/json')
            resp.set_cookie('session_id', '', expires=0, path='/')
            resp.set_cookie('user_id', '', expires=0, path='/')
            return resp
    else:
        user_id = None

    async def generate():
        async for chunk in process_message(user_message, session_id, user_id):
            yield chunk

    response = Response(generate(), mimetype='text/plain')
    response.set_cookie('session_id', session_id, path='/', httponly=False, samesite='Lax', max_age=2592000)
    if user_id:
        response.set_cookie('user_id', str(user_id), path='/', httponly=False, samesite='Lax', max_age=2592000)
    return response

# ========== Network visualizer endpoint ==========
@app.route('/api/network')
async def network_data():
    import sqlite3
    model_name = config.get('DEFAULT', 'default_model')
    try:
        adapter = get_adapter(model_name)
        conn = adapter.get_connection(model_name)
    except FileNotFoundError:
        return {
            "nodes": [],
            "links": [],
            "message": "No model found. Please create a model using the Alto Trainer."
        }
    except Exception as e:
        return {
            "nodes": [],
            "links": [],
            "message": f"Error loading model: {str(e)}"
        }

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

    cur = conn.execute("""
        SELECT g.id, g.group_name, COALESCE(t.name, '') as topic, COALESCE(s.name, '') as section
        FROM groups g
        LEFT JOIN topics t ON g.topic_id = t.id
        LEFT JOIN sections s ON g.section_id = s.id
        ORDER BY g.id
    """)
    for row in cur:
        group_id = f"group_{row['id']}"
        add_node(group_id, row['group_name'], 'group', row['topic'], row['section'])

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

    for (node_id, group_id, parent_id) in followup_nodes.values():
        if parent_id is None:
            links.append({"source": group_id, "target": node_id})
        else:
            links.append({"source": parent_id, "target": node_id})

    return {"nodes": nodes, "links": links, "message": None}

# ---------- Web UI routes (conditional) ----------
if SERVE_WEBUI:
    @app.route('/')
    async def login_page():
        return await send_from_directory(os.path.join(FRONTEND_DIR, 'static', 'login'), 'index.html')

    @app.route('/chat', methods=['GET'])
    async def chat_page():
        user_id = request.cookies.get('user_id')
        if user_id and user_id.isdigit():
            if user_exists(int(user_id)):
                return await send_from_directory(os.path.join(FRONTEND_DIR, 'static', 'chat'), 'index.html')
        return redirect('/')

    @app.route('/network')
    async def network_page():
        return await send_from_directory(os.path.join(FRONTEND_DIR, 'static', 'network'), 'index.html')

    @app.route('/static/chat/<path:filename>')
    async def chat_static(filename):
        return await send_from_directory(os.path.join(FRONTEND_DIR, 'static', 'chat'), filename)

    @app.route('/static/login/<path:filename>')
    async def login_static(filename):
        return await send_from_directory(os.path.join(FRONTEND_DIR, 'static', 'login'), filename)

    @app.route('/static/network/<path:filename>')
    async def network_static(filename):
        return await send_from_directory(os.path.join(FRONTEND_DIR, 'static', 'network'), filename)

else:
    BLANK_HTML = '<!DOCTYPE html><html><head><title></title></head><body></body></html>'

    @app.route('/')
    async def login_page():
        return Response(BLANK_HTML, status=200, mimetype='text/html')

    @app.route('/chat', methods=['GET'])
    async def chat_page():
        return Response(BLANK_HTML, status=200, mimetype='text/html')

    @app.route('/network')
    async def network_page():
        return Response(BLANK_HTML, status=200, mimetype='text/html')

if __name__ == '__main__':
    app.run(debug=True)
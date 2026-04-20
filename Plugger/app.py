#!/usr/bin/env python3
import os
from quart import Quart, request, jsonify, send_from_directory, Response
from plugin_manager import list_plugins, create_plugin, get_plugin, update_plugin, delete_plugin

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
app = Quart(__name__, static_folder=os.path.join(BASE_DIR, 'static'))

@app.route('/favicon.ico')
async def favicon():
    favicon_path = os.path.join(BASE_DIR, 'static', 'favicon.ico')
    if not os.path.exists(favicon_path):
        return Response('', status=204)
    return await send_from_directory(os.path.join(BASE_DIR, 'static'), 'favicon.ico', mimetype='image/vnd.microsoft.icon')

@app.route('/')
async def index():
    return await send_from_directory(os.path.join(BASE_DIR, 'static'), 'index.html')

@app.route('/api/plugins', methods=['GET'])
async def api_list_plugins():
    result = list_plugins()
    if "error" in result:
        return jsonify(result), 500
    return jsonify(result)

@app.route('/api/plugins', methods=['POST'])
async def api_create_plugin():
    data = await request.get_json()
    code = data.get('code', '')
    if not code:
        return jsonify({'error': 'Plugin code is required'}), 400
    result = create_plugin(code)
    if "error" in result:
        return jsonify(result), 400
    return jsonify({'status': 'ok', 'name': result['name']}), 201

@app.route('/api/plugins/<string:name>', methods=['GET'])
async def api_get_plugin(name):
    result = get_plugin(name)
    if "error" in result:
        return jsonify(result), 404
    return jsonify(result)

@app.route('/api/plugins/<string:name>', methods=['PUT'])
async def api_update_plugin(name):
    data = await request.get_json()
    code = data.get('code', '')
    if not code:
        return jsonify({'error': 'Plugin code is required'}), 400
    result = update_plugin(name, code)
    if "error" in result:
        return jsonify(result), 400
    return jsonify(result)

@app.route('/api/plugins/<string:name>', methods=['DELETE'])
async def api_delete_plugin(name):
    result = delete_plugin(name)
    if "error" in result:
        return jsonify(result), 404
    return jsonify(result)

if __name__ == '__main__':
    app.run(debug=True, port=5002)
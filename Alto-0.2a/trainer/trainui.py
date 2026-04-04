from quart import Quart, request, jsonify, send_file, send_from_directory
import asyncio
import json
import os
import sys
import tempfile
from config import config

app = Quart(__name__, static_folder="static")

TRAINER_CLI = os.path.join(os.path.dirname(__file__), "RuleTrainer.py")
trainer_process = None
trainer_stdin = None
trainer_stdout = None
_trainer_lock = asyncio.Lock()

async def log_trainer_stderr():
    global trainer_process
    while trainer_process and trainer_process.stderr:
        line = await trainer_process.stderr.readline()
        if not line:
            break
        print(f"[trainer stderr] {line.decode().strip()}")

async def start_trainer():
    global trainer_process, trainer_stdin, trainer_stdout
    cmd = [sys.executable, TRAINER_CLI, "--interactive"]
    trainer_process = await asyncio.create_subprocess_exec(
        *cmd,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE
    )
    trainer_stdin = trainer_process.stdin
    trainer_stdout = trainer_process.stdout
    asyncio.create_task(log_trainer_stderr())

async def stop_trainer():
    global trainer_process
    if trainer_process:
        trainer_process.terminate()
        await trainer_process.wait()
        trainer_process = None

async def send_command(command, **kwargs):
    global trainer_process, trainer_stdin, trainer_stdout
    async with _trainer_lock:
        if not trainer_process or trainer_process.returncode is not None:
            await start_trainer()
        request_data = {"command": command, "args": kwargs}
        line = json.dumps(request_data, separators=(',', ':')) + "\n"
        trainer_stdin.write(line.encode())
        await trainer_stdin.drain()
        response_line = await trainer_stdout.readline()
        if not response_line:
            await stop_trainer()
            await start_trainer()
            trainer_stdin.write(line.encode())
            await trainer_stdin.drain()
            response_line = await trainer_stdout.readline()
            if not response_line:
                return {"error": "Trainer process unavailable"}
        try:
            return json.loads(response_line.decode())
        except json.JSONDecodeError:
            return {"error": "Invalid JSON from trainer"}

# ========== Routes ==========

@app.route('/')
async def index():
    return await app.send_static_file('index.html')

@app.route('/static/<path:filename>')
async def serve_static(filename):
    return await send_from_directory('static', filename)

@app.route('/api/models', methods=['GET'])
async def list_models():
    result = await send_command("list-models")
    if "error" in result:
        return jsonify(result), 500
    return jsonify(result)

@app.route('/api/models', methods=['POST'])
async def create_model():
    data = await request.get_json()
    name = data.get('name')
    description = data.get('description', '')
    author = data.get('author', '')
    version = data.get('version', '1.0.0')
    result = await send_command("create-model", name=name, description=description,
                                author=author, version=version)
    if "error" in result:
        return jsonify(result), 400
    return jsonify({"status": "ok"})

@app.route('/api/models/<name>', methods=['GET'])
async def get_model(name):
    result = await send_command("get-model", name=name)
    if "error" in result:
        return jsonify(result), 404
    return jsonify(result)

@app.route('/api/models/<name>', methods=['PUT'])
async def update_model(name):
    data = await request.get_json()
    kwargs = {"name": name}
    if data.get('description') is not None:
        kwargs["description"] = data['description']
    if data.get('author') is not None:
        kwargs["author"] = data['author']
    if data.get('version') is not None:
        kwargs["version"] = data['version']
    result = await send_command("update-model", **kwargs)
    if "error" in result:
        return jsonify(result), 400
    return jsonify({"status": "ok"})

@app.route('/api/models/<name>', methods=['DELETE'])
async def delete_model(name):
    result = await send_command("delete-model", name=name)
    if "error" in result:
        return jsonify(result), 404
    return jsonify({"status": "ok"})

@app.route('/api/models/<name>/rename', methods=['POST'])
async def rename_model(name):
    data = await request.get_json()
    new_name = data.get('new_name')
    if not new_name:
        return jsonify({"error": "New name required"}), 400
    result = await send_command("rename-model", name=name, new_name=new_name)
    if "error" in result:
        return jsonify(result), 400
    return jsonify({"status": "ok", "new_name": new_name})

# ========== Group endpoints ==========
@app.route('/api/models/<name>/groups', methods=['POST'])
async def add_group(name):
    data = await request.get_json()
    result = await send_command("add-group", name=name,
                                data=json.dumps(data, separators=(',', ':')))
    if "error" in result:
        return jsonify(result), 400
    return jsonify({"status": "ok"})

@app.route('/api/models/<name>/groups/<int:index>', methods=['PUT'])
async def update_group(name, index):
    data = await request.get_json()
    result = await send_command("update-group", name=name, index=index,
                                data=json.dumps(data, separators=(',', ':')))
    if "error" in result:
        return jsonify(result), 400
    return jsonify({"status": "ok"})

@app.route('/api/models/<name>/groups/<int:index>', methods=['DELETE'])
async def delete_group(name, index):
    result = await send_command("delete-group", name=name, index=index)
    if "error" in result:
        return jsonify(result), 400
    return jsonify({"status": "ok"})

@app.route('/api/models/<name>/groups/<int:group_index>/followups', methods=['GET'])
async def get_followups(name, group_index):
    result = await send_command("get-followups", name=name, index=group_index)
    if "error" in result:
        return jsonify(result), 400
    return jsonify(result)

@app.route('/api/models/<name>/groups/<int:group_index>/followups', methods=['PUT'])
async def save_followups(name, group_index):
    data = await request.get_json()
    result = await send_command("save-followups", name=name, index=group_index,
                                data=json.dumps(data, separators=(',', ':')))
    if "error" in result:
        return jsonify(result), 400
    return jsonify({"status": "ok"})

@app.route('/api/models/<name>/groups/<int:group_index>/nodes/<int:node_id>', methods=['GET'])
async def get_node_details(name, group_index, node_id):
    result = await send_command("get-node-details", name=name, index=group_index, node_id=node_id)
    if "error" in result:
        return jsonify(result), 400
    return jsonify(result)

# ========== Lightweight group routes ==========
@app.route('/api/models/<name>/groups/summaries', methods=['GET'])
async def get_group_summaries(name):
    result = await send_command("get-group-summaries", name=name)
    if "error" in result:
        return jsonify(result), 404
    return jsonify(result)

@app.route('/api/models/<name>/groups/<int:index>/full', methods=['GET'])
async def get_group_full(name, index):
    result = await send_command("get-group-full", name=name, index=index)
    if "error" in result:
        return jsonify(result), 404
    return jsonify(result)

# ========== Section endpoints ==========
@app.route('/api/models/<name>/sections', methods=['POST'])
async def add_section(name):
    data = await request.get_json()
    section = data.get('section')
    if not section:
        return jsonify({"error": "Section name required"}), 400
    result = await send_command("add-section", name=name, section=section)
    if "error" in result:
        return jsonify(result), 400
    return jsonify({"status": "ok"})

@app.route('/api/models/<name>/sections/<old_name>', methods=['PUT'])
async def rename_section(name, old_name):
    data = await request.get_json()
    new_name = data.get('new_name')
    if not new_name:
        return jsonify({"error": "New name required"}), 400
    result = await send_command("rename-section", name=name, old=old_name, new=new_name)
    if "error" in result:
        return jsonify(result), 400
    return jsonify({"status": "ok"})

@app.route('/api/models/<name>/sections/<section>', methods=['DELETE'])
async def delete_section(name, section):
    action = request.args.get('action', 'uncategorized')
    target = request.args.get('target')
    kwargs = {"name": name, "section": section, "action": action}
    if target:
        kwargs["target"] = target
    result = await send_command("delete-section", **kwargs)
    if "error" in result:
        return jsonify(result), 400
    return jsonify({"status": "ok"})

# ========== Topic endpoints ==========
@app.route('/api/models/<name>/topics', methods=['GET'])
async def get_topics(name):
    result = await send_command("get-topics", name=name)
    if "error" in result:
        return jsonify(result), 400
    return jsonify(result)

@app.route('/api/models/<name>/topics', methods=['POST'])
async def add_topic(name):
    data = await request.get_json()
    topic = data.get('topic')
    if not topic:
        return jsonify({"error": "Topic name required"}), 400
    result = await send_command("add-topic", name=name, topic=topic)
    if "error" in result:
        return jsonify(result), 400
    return jsonify(result)

@app.route('/api/models/<name>/topics/<old_name>', methods=['PUT'])
async def rename_topic(name, old_name):
    data = await request.get_json()
    new_name = data.get('new_name')
    if not new_name:
        return jsonify({"error": "New name required"}), 400
    result = await send_command("rename-topic", name=name, old=old_name, new=new_name)
    if "error" in result:
        return jsonify(result), 400
    return jsonify(result)

@app.route('/api/models/<name>/topics/<topic>/groups', methods=['GET'])
async def get_topic_groups(name, topic):
    result = await send_command("get-topic-groups", name=name, topic=topic)
    if "error" in result:
        return jsonify(result), 404
    return jsonify(result)

@app.route('/api/models/<name>/topics/<topic>', methods=['DELETE'])
async def delete_topic(name, topic):
    action = request.args.get('action', 'reassign')
    target = request.args.get('target')
    kwargs = {"name": name, "topic": topic, "action": action}
    if target:
        kwargs["target"] = target
    result = await send_command("delete-topic", **kwargs)
    if "error" in result:
        return jsonify(result), 400
    return jsonify({"status": "ok"})

# ========== Variant endpoints ==========
@app.route('/api/models/<name>/variants', methods=['GET'])
async def get_variants(name):
    result = await send_command("get-variants", name=name)
    if "error" in result:
        return jsonify(result), 400
    return jsonify(result)

@app.route('/api/models/<name>/variants', methods=['POST'])
async def add_variant(name):
    data = await request.get_json()
    result = await send_command("add-variant", name=name,
                                data=json.dumps(data, separators=(',', ':')))
    if "error" in result:
        return jsonify(result), 400
    return jsonify(result)

@app.route('/api/models/<name>/variants/<int:variant_id>', methods=['PUT'])
async def update_variant(name, variant_id):
    data = await request.get_json()
    result = await send_command("update-variant", name=name, variant_id=variant_id,
                                data=json.dumps(data, separators=(',', ':')))
    if "error" in result:
        return jsonify(result), 400
    return jsonify(result)

@app.route('/api/models/<name>/variants/<int:variant_id>', methods=['DELETE'])
async def delete_variant(name, variant_id):
    result = await send_command("delete-variant", name=name, variant_id=variant_id)
    if "error" in result:
        return jsonify(result), 400
    return jsonify({"status": "ok"})

# ========== Import/Export ==========
@app.route('/api/models/import', methods=['POST'])
async def import_model():
    """Import a .db or .rbm file."""
    files = await request.files
    if 'file' not in files:
        return jsonify({'error': 'No file uploaded'}), 400
    file = files['file']
    filename = file.filename.lower()
    if not (filename.endswith('.db') or filename.endswith('.rbm')):
        return jsonify({'error': 'File must be .db or .rbm'}), 400

    form = await request.form
    custom_name = form.get('name', '').strip()
    overwrite = form.get('overwrite', '').lower() == 'true'

    with tempfile.NamedTemporaryFile(delete=False, suffix=os.path.splitext(filename)[1]) as tmp:
        content = file.read()
        tmp.write(content)
        tmp_path = tmp.name

    if filename.endswith('.rbm'):
        result = await send_command("import-rbm", file=tmp_path, name=custom_name, overwrite=overwrite)
    else:
        result = await send_command("import-db", file=tmp_path, name=custom_name, overwrite=overwrite)

    os.unlink(tmp_path)

    if "error" in result:
        status = 409 if result.get("code") == "CONFLICT" else 500
        return jsonify(result), status
    return jsonify(result)

@app.route('/api/models/<name>/export', methods=['GET'])
async def export_model(name):
    """Export the full .rbm container."""
    result = await send_command("get-model-container-path", name=name)
    if "error" in result:
        return jsonify(result), 404
    container_path = result["path"]
    return await send_file(
        container_path,
        mimetype='application/x-tar',
        attachment_filename=f'{name}.rbm',
        as_attachment=True
    )

@app.before_serving
async def startup():
    await start_trainer()

@app.after_serving
async def shutdown():
    await stop_trainer()

if __name__ == '__main__':
    app.run(
        debug=config.getboolean('DEFAULT', 'debug'),
        port=config.getint('DEFAULT', 'port')
    )
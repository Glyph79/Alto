from quart import Quart, request, jsonify, send_file, render_template, send_from_directory
import asyncio
import json
import os
import sys
import tempfile

app = Quart(__name__, template_folder="templates", static_folder="static")

TRAINER_CLI = os.path.join(os.path.dirname(__file__), "trainer.py")
trainer_process = None
trainer_stdin = None
trainer_stdout = None

async def log_trainer_stderr():
    """Read and print trainer's stderr to the console."""
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
        stderr=asyncio.subprocess.PIPE   # capture stderr
    )
    trainer_stdin = trainer_process.stdin
    trainer_stdout = trainer_process.stdout
    # Start a background task to log stderr
    asyncio.create_task(log_trainer_stderr())

async def stop_trainer():
    global trainer_process
    if trainer_process:
        trainer_process.terminate()
        await trainer_process.wait()
        trainer_process = None

async def send_command(command, **kwargs):
    global trainer_process, trainer_stdin, trainer_stdout
    if not trainer_process or trainer_process.returncode is not None:
        await start_trainer()
    request_data = {"command": command, "args": kwargs}
    line = json.dumps(request_data, separators=(',', ':')) + "\n"
    trainer_stdin.write(line.encode())
    await trainer_stdin.drain()
    response_line = await trainer_stdout.readline()
    if not response_line:
        # Process died, restart and retry once
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

# ----------------------------------------------------------------------
# API routes (unchanged)
# ----------------------------------------------------------------------
@app.route('/static/<path:filename>')
async def serve_static(filename):
    return await send_from_directory('static', filename)

@app.route('/')
async def index():
    return await render_template('index.html')

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

@app.route('/api/models/<name>/groups', methods=['GET'])
async def get_groups(name):
    result = await send_command("get-model", name=name)
    if "error" in result:
        return jsonify(result), 404
    return jsonify({
        "groups": result.get("qa_groups", []),
        "sections": result.get("sections", [])
    })

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

@app.route('/api/models/<name>/groups/<int:group_index>/questions', methods=['POST'])
async def add_question(name, group_index):
    data = await request.get_json()
    question = data.get('question')
    if not question:
        return jsonify({"error": "Question text required"}), 400
    result = await send_command("add-question", name=name, index=group_index, text=question)
    if "error" in result:
        return jsonify(result), 400
    return jsonify({"status": "ok"})

@app.route('/api/models/<name>/groups/<int:group_index>/questions/<int:q_index>', methods=['PUT'])
async def update_question(name, group_index, q_index):
    data = await request.get_json()
    question = data.get('question')
    if not question:
        return jsonify({"error": "Question text required"}), 400
    result = await send_command("update-question", name=name, index=group_index,
                                qidx=q_index, text=question)
    if "error" in result:
        return jsonify(result), 400
    return jsonify({"status": "ok"})

@app.route('/api/models/<name>/groups/<int:group_index>/questions/<int:q_index>', methods=['DELETE'])
async def delete_question(name, group_index, q_index):
    result = await send_command("delete-question", name=name, index=group_index, qidx=q_index)
    if "error" in result:
        return jsonify(result), 400
    return jsonify({"status": "ok"})

@app.route('/api/models/<name>/groups/<int:group_index>/answers', methods=['POST'])
async def add_answer(name, group_index):
    data = await request.get_json()
    answer = data.get('answer')
    if not answer:
        return jsonify({"error": "Answer text required"}), 400
    result = await send_command("add-answer", name=name, index=group_index, text=answer)
    if "error" in result:
        return jsonify(result), 400
    return jsonify({"status": "ok"})

@app.route('/api/models/<name>/groups/<int:group_index>/answers/<int:a_index>', methods=['PUT'])
async def update_answer(name, group_index, a_index):
    data = await request.get_json()
    answer = data.get('answer')
    if not answer:
        return jsonify({"error": "Answer text required"}), 400
    result = await send_command("update-answer", name=name, index=group_index,
                                aidx=a_index, text=answer)
    if "error" in result:
        return jsonify(result), 400
    return jsonify({"status": "ok"})

@app.route('/api/models/<name>/groups/<int:group_index>/answers/<int:a_index>', methods=['DELETE'])
async def delete_answer(name, group_index, a_index):
    result = await send_command("delete-answer", name=name, index=group_index, aidx=a_index)
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

# -------------------- Native .db import (creates new model) --------------------
@app.route('/api/models/import-db', methods=['POST'])
async def import_db():
    files = await request.files
    if 'file' not in files:
        return jsonify({'error': 'No file uploaded'}), 400
    file = files['file']
    if not file.filename.endswith('.db'):
        return jsonify({'error': 'File must be a .db file'}), 400

    form = await request.form
    custom_name = form.get('name', '').strip()
    overwrite = form.get('overwrite', '').lower() == 'true'

    print(f"[import_db] Received name='{custom_name}', overwrite={overwrite}")
    print(f"[import_db] form keys: {list(form.keys())}")

    with tempfile.NamedTemporaryFile(delete=False, suffix='.db') as tmp:
        content = file.read()
        tmp.write(content)
        tmp_path = tmp.name

    result = await send_command("import-db", file=tmp_path, name=custom_name, overwrite=overwrite)
    os.unlink(tmp_path)

    if "error" in result:
        status = 409 if result.get("code") == "CONFLICT" else 500
        return jsonify(result), status
    return jsonify(result)

# -------------------- Native .db export (download current model's db) ---------
@app.route('/api/models/<name>/export-db', methods=['GET'])
async def export_db(name):
    result = await send_command("get-model-db-path", name=name)
    if "error" in result:
        return jsonify(result), 404
    db_path = result["path"]
    return await send_file(
        db_path,
        mimetype='application/vnd.sqlite3',
        attachment_filename=f'{name}.db',
        as_attachment=True
    )

@app.before_serving
async def startup():
    await start_trainer()

@app.after_serving
async def shutdown():
    await stop_trainer()

if __name__ == '__main__':
    app.run(debug=True, port=5001)
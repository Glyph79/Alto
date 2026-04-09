#!/usr/bin/env python3
from quart import Quart, request, jsonify, send_file, send_from_directory, Response
import asyncio
import json
import os
import sys
import tempfile
import time
from pathlib import Path
from backend.config import config
from convert.converter import get_converter_settings, update_converter_settings, convert_legacy_db_to_rbm
from backend.legacy_scanner import scan_legacy_models, convert_legacy_model

app = Quart(__name__, static_folder=None)

SERVE_WEBUI = config.getboolean('DEFAULT', 'serve_webui', fallback=True)

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
FRONTEND_DIR = os.path.join(PROJECT_ROOT, 'frontend')

TRAINER_CLI = os.path.join(PROJECT_ROOT, "RuleTrainer.py")
trainer_process = None
trainer_stdin = None
trainer_stdout = None
_trainer_lock = asyncio.Lock()

# Favicon route
@app.route('/favicon.ico')
async def favicon():
    favicon_path = os.path.join(FRONTEND_DIR, 'static', 'favicon.ico')
    if not os.path.exists(favicon_path):
        return Response('', status=204)
    return await send_from_directory(os.path.join(FRONTEND_DIR, 'static'), 'favicon.ico', mimetype='image/vnd.microsoft.icon')

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
        try:
            response_line = await asyncio.wait_for(trainer_stdout.readline(), timeout=30.0)
        except asyncio.TimeoutError:
            await stop_trainer()
            await start_trainer()
            trainer_stdin.write(line.encode())
            await trainer_stdin.drain()
            try:
                response_line = await asyncio.wait_for(trainer_stdout.readline(), timeout=30.0)
            except asyncio.TimeoutError:
                return {"error": "Trainer process timed out after restart"}
        if not response_line:
            return {"error": "Trainer process unavailable"}
        try:
            return json.loads(response_line.decode())
        except json.JSONDecodeError:
            return {"error": "Invalid JSON from trainer"}

# ========== API routes (always available) ==========

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

# Group endpoints
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

# Lightweight group routes
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

# Section endpoints
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

# Topic endpoints
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
    return jsonify({"status": "ok"})

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

# Variant endpoints
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

# Fallback endpoints
@app.route('/api/models/<name>/fallbacks', methods=['GET'])
async def list_fallbacks(name):
    result = await send_command("list-fallbacks", name=name)
    if "error" in result:
        return jsonify(result), 500
    return jsonify(result)

@app.route('/api/models/<name>/fallbacks', methods=['POST'])
async def create_fallback(name):
    data = await request.get_json()
    result = await send_command("create-fallback", name=name, data=json.dumps(data))
    if "error" in result:
        return jsonify(result), 400
    return jsonify({"status": "ok", "id": result.get("id")})

@app.route('/api/models/<name>/fallbacks/<int:fallback_id>', methods=['GET'])
async def get_fallback(name, fallback_id):
    result = await send_command("get-fallback", name=name, fallback_id=fallback_id)
    if "error" in result:
        return jsonify(result), 404
    return jsonify(result)

@app.route('/api/models/<name>/fallbacks/<int:fallback_id>', methods=['PUT'])
async def update_fallback(name, fallback_id):
    data = await request.get_json()
    result = await send_command("update-fallback", name=name, fallback_id=fallback_id, data=json.dumps(data))
    if "error" in result:
        return jsonify(result), 400
    return jsonify({"status": "ok"})

@app.route('/api/models/<name>/fallbacks/<int:fallback_id>', methods=['DELETE'])
async def delete_fallback(name, fallback_id):
    result = await send_command("delete-fallback", name=name, fallback_id=fallback_id)
    if "error" in result:
        return jsonify(result), 400
    return jsonify({"status": "ok"})

@app.route('/api/models/<name>/fallbacks/<int:fallback_id>/groups', methods=['GET'])
async def get_fallback_groups(name, fallback_id):
    result = await send_command("get-fallback-groups", name=name, fallback_id=fallback_id)
    if "error" in result:
        return jsonify(result), 404
    return jsonify(result)

# ========== Import/Export (fixed: .db files use converter, no name prompt) ==========
@app.route('/api/models/import', methods=['POST'])
async def import_model():
    files = await request.files
    if 'file' not in files:
        return jsonify({'error': 'No file uploaded'}), 400
    file = files['file']
    filename = file.filename.lower()
    
    # For .rbm files, use the existing import-rbm command
    if filename.endswith('.rbm'):
        form = await request.form
        custom_name = form.get('name', '').strip()
        overwrite = form.get('overwrite', '').lower() == 'true'
        with tempfile.NamedTemporaryFile(delete=False, suffix='.rbm') as tmp:
            content = file.read()
            tmp.write(content)
            tmp_path = tmp.name
        result = await send_command("import-rbm", file=tmp_path, name=custom_name, overwrite=overwrite)
        # Retry deletion if file locked
        for _ in range(5):
            try:
                os.unlink(tmp_path)
                break
            except PermissionError:
                time.sleep(0.1)
        else:
            print(f"Warning: could not delete temp file {tmp_path}")
        if "error" in result:
            status = 409 if result.get("code") == "CONFLICT" else 500
            return jsonify(result), status
        return jsonify(result)
    
    # For .db files, use the converter – read model name from database, don't ask user
    if filename.endswith('.db'):
        with tempfile.NamedTemporaryFile(delete=False, suffix='.db') as tmp:
            content = file.read()
            tmp.write(content)
            tmp_path = tmp.name
        try:
            models_dir = config.get('DEFAULT', 'models_dir')
            container_path = convert_legacy_db_to_rbm(Path(tmp_path), new_model_name=None, models_dir=Path(models_dir))
            # Extract the actual model name from the container manifest
            from backend.utils.file_helpers import read_manifest
            manifest = read_manifest(container_path)
            model_name = manifest["name"] if manifest else Path(tmp_path).stem
            return jsonify({'status': 'ok', 'model': {'name': model_name}, 'path': str(container_path)})
        except Exception as e:
            return jsonify({'error': str(e)}), 500
        finally:
            # Retry deletion if file locked
            for _ in range(5):
                try:
                    os.unlink(tmp_path)
                    break
                except PermissionError:
                    time.sleep(0.1)
            else:
                print(f"Warning: could not delete temp file {tmp_path}")
    
    return jsonify({'error': 'File must be .db or .rbm'}), 400

@app.route('/api/models/<name>/export', methods=['GET'])
async def export_model(name):
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

# ========== Converter API routes ==========
@app.route('/api/converter/settings', methods=['GET'])
async def api_get_converter_settings():
    return jsonify(get_converter_settings())

@app.route('/api/converter/settings', methods=['POST'])
async def api_set_converter_settings():
    data = await request.get_json()
    update_converter_settings(
        batch_size=data.get('batch_size'),
        # create_missing is ignored; always True
    )
    return jsonify({'status': 'ok'})

@app.route('/api/convert/legacy', methods=['POST'])
async def api_convert_legacy():
    files = await request.files
    if 'file' not in files:
        return jsonify({'error': 'No file uploaded'}), 400
    file = files['file']
    if not file.filename.lower().endswith('.db'):
        return jsonify({'error': 'Only .db files are supported'}), 400

    with tempfile.NamedTemporaryFile(delete=False, suffix='.db') as tmp:
        content = file.read()
        tmp.write(content)
        tmp_path = tmp.name

    try:
        models_dir = config.get('DEFAULT', 'models_dir')
        container_path = convert_legacy_db_to_rbm(Path(tmp_path), new_model_name=None, models_dir=Path(models_dir))
        from backend.utils.file_helpers import read_manifest
        manifest = read_manifest(container_path)
        model_name = manifest["name"] if manifest else Path(tmp_path).stem
        return jsonify({'status': 'ok', 'model_name': model_name, 'path': str(container_path)})
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        # Retry deletion if file locked
        for _ in range(5):
            try:
                os.unlink(tmp_path)
                break
            except PermissionError:
                time.sleep(0.1)
        else:
            print(f"Warning: could not delete temp file {tmp_path}")

# ========== Legacy model scanner and batch conversion ==========
conversion_status = {
    "running": False,
    "total": 0,
    "completed": 0,
    "failed": [],
    "backup_dir": None
}

@app.route('/api/legacy/scan', methods=['GET'])
async def api_legacy_scan():
    models_dir = config.get('DEFAULT', 'models_dir')
    legacy_files = scan_legacy_models(models_dir)
    return jsonify({"legacy_models": [os.path.basename(f) for f in legacy_files], "paths": legacy_files})

@app.route('/api/legacy/convert', methods=['POST'])
async def api_legacy_convert():
    global conversion_status
    if conversion_status["running"]:
        return jsonify({"error": "Conversion already in progress"}), 409
    data = await request.get_json()
    legacy_paths = data.get("paths", [])
    backup = data.get("backup", True)
    models_dir = config.get('DEFAULT', 'models_dir')
    backup_dir = os.path.join(models_dir, "backup_models") if backup else None

    conversion_status = {
        "running": True,
        "total": len(legacy_paths),
        "completed": 0,
        "failed": [],
        "backup_dir": backup_dir
    }

    async def run_conversion():
        for db_path in legacy_paths:
            base_name = os.path.splitext(os.path.basename(db_path))[0]
            new_name = base_name + "_v2"
            try:
                final_name = new_name
                counter = 1
                while os.path.exists(os.path.join(models_dir, f"{final_name}.rbm")):
                    final_name = f"{base_name}_v2_{counter}"
                    counter += 1
                convert_legacy_model(db_path, final_name, models_dir, backup_dir)
                conversion_status["completed"] += 1
            except Exception as e:
                conversion_status["failed"].append({"file": db_path, "error": str(e)})
        conversion_status["running"] = False

    asyncio.create_task(run_conversion())
    return jsonify({"status": "started", "total": len(legacy_paths)})

@app.route('/api/legacy/status', methods=['GET'])
async def api_legacy_status():
    return jsonify(conversion_status)

# ========== Web UI routes (conditional) ==========
if SERVE_WEBUI:
    @app.route('/')
    async def index():
        return await send_from_directory(os.path.join(FRONTEND_DIR, 'static'), 'index.html')

    @app.route('/static/<path:filename>')
    async def serve_static(filename):
        return await send_from_directory(os.path.join(FRONTEND_DIR, 'static'), filename)
else:
    BLANK_HTML = '<!DOCTYPE html><html><head><title></title></head><body></body></html>'

    @app.route('/')
    async def index():
        return Response(BLANK_HTML, status=200, mimetype='text/html')

    @app.route('/static/<path:filename>')
    async def serve_static(filename):
        return Response('', status=204)

# Startup/shutdown
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
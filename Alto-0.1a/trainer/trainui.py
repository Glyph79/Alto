from quart import Quart, request, jsonify, send_file, render_template, send_from_directory
import os
import tempfile
from trainer import Trainer

app = Quart(__name__, template_folder="templates", static_folder="static")
trainer = Trainer()

@app.route('/static/<path:filename>')
async def serve_static(filename):
    return await send_from_directory('static', filename)

@app.route('/')
async def index():
    return await render_template('index.html')

@app.route('/api/models', methods=['GET'])
async def list_models():
    try:
        models = trainer.list_models()
        return jsonify(models)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/models', methods=['POST'])
async def create_model():
    data = await request.get_json()
    name = data.get('name')
    description = data.get('description', '')
    author = data.get('author', '')
    version = data.get('version', '1.0.0')
    try:
        trainer.create_model(name, description, author, version)
        return jsonify({'status': 'ok'})
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/models/<name>', methods=['GET'])
async def get_model(name):
    try:
        data = trainer.load_model(name)
        return jsonify(data)
    except ValueError as e:
        return jsonify({'error': str(e)}), 404
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/models/<name>', methods=['PUT'])
async def update_model(name):
    data = await request.get_json()
    description = data.get('description')
    author = data.get('author')
    version = data.get('version')
    try:
        trainer.update_model_info(name, description, author, version)
        return jsonify({'status': 'ok'})
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/models/<name>', methods=['DELETE'])
async def delete_model(name):
    try:
        trainer.delete_model(name)
        return jsonify({'status': 'ok'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/models/<name>/groups', methods=['GET'])
async def get_groups(name):
    section_filter = request.args.get('section')
    try:
        groups = trainer.get_groups(name, section_filter)
        sections = trainer.get_sections(name)
        return jsonify({'groups': groups, 'sections': sections})
    except ValueError as e:
        return jsonify({'error': str(e)}), 404
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/models/<name>/groups', methods=['POST'])
async def add_group(name):
    data = await request.get_json()
    try:
        trainer.add_group(name, data)
        return jsonify({'status': 'ok'})
    except (ValueError, IndexError) as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/models/<name>/groups/<int:index>', methods=['PUT'])
async def update_group(name, index):
    data = await request.get_json()
    try:
        trainer.update_group(name, index, data)
        return jsonify({'status': 'ok'})
    except (ValueError, IndexError) as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/models/<name>/groups/<int:index>', methods=['DELETE'])
async def delete_group(name, index):
    try:
        trainer.delete_group(name, index)
        return jsonify({'status': 'ok'})
    except IndexError as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/models/<name>/groups/<int:group_index>/questions', methods=['POST'])
async def add_question(name, group_index):
    data = await request.get_json()
    question = data.get('question')
    if not question:
        return jsonify({'error': 'Question text required'}), 400
    try:
        trainer.add_question(name, group_index, question)
        return jsonify({'status': 'ok'})
    except IndexError as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/models/<name>/groups/<int:group_index>/questions/<int:q_index>', methods=['PUT'])
async def update_question(name, group_index, q_index):
    data = await request.get_json()
    question = data.get('question')
    if not question:
        return jsonify({'error': 'Question text required'}), 400
    try:
        trainer.update_question(name, group_index, q_index, question)
        return jsonify({'status': 'ok'})
    except IndexError as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/models/<name>/groups/<int:group_index>/questions/<int:q_index>', methods=['DELETE'])
async def delete_question(name, group_index, q_index):
    try:
        trainer.delete_question(name, group_index, q_index)
        return jsonify({'status': 'ok'})
    except IndexError as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/models/<name>/groups/<int:group_index>/answers', methods=['POST'])
async def add_answer(name, group_index):
    data = await request.get_json()
    answer = data.get('answer')
    if not answer:
        return jsonify({'error': 'Answer text required'}), 400
    try:
        trainer.add_answer(name, group_index, answer)
        return jsonify({'status': 'ok'})
    except IndexError as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/models/<name>/groups/<int:group_index>/answers/<int:a_index>', methods=['PUT'])
async def update_answer(name, group_index, a_index):
    data = await request.get_json()
    answer = data.get('answer')
    if not answer:
        return jsonify({'error': 'Answer text required'}), 400
    try:
        trainer.update_answer(name, group_index, a_index, answer)
        return jsonify({'status': 'ok'})
    except IndexError as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/models/<name>/groups/<int:group_index>/answers/<int:a_index>', methods=['DELETE'])
async def delete_answer(name, group_index, a_index):
    try:
        trainer.delete_answer(name, group_index, a_index)
        return jsonify({'status': 'ok'})
    except IndexError as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/models/<name>/groups/<int:group_index>/followups', methods=['GET'])
async def get_followups(name, group_index):
    try:
        followups = trainer.get_followups(name, group_index)
        return jsonify(followups)
    except IndexError as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/models/<name>/groups/<int:group_index>/followups', methods=['PUT'])
async def save_followups(name, group_index):
    data = await request.get_json()
    try:
        trainer.save_followups(name, group_index, data)
        return jsonify({'status': 'ok'})
    except IndexError as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/models/<name>/sections', methods=['POST'])
async def add_section(name):
    data = await request.get_json()
    section = data.get('section')
    if not section:
        return jsonify({'error': 'Section name required'}), 400
    try:
        trainer.add_section(name, section)
        return jsonify({'status': 'ok'})
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/models/<name>/sections/<old_name>', methods=['PUT'])
async def rename_section(name, old_name):
    data = await request.get_json()
    new_name = data.get('new_name')
    if not new_name:
        return jsonify({'error': 'New name required'}), 400
    try:
        trainer.rename_section(name, old_name, new_name)
        return jsonify({'status': 'ok'})
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/models/<name>/sections/<section>', methods=['DELETE'])
async def delete_section(name, section):
    action = request.args.get('action', 'uncategorized')
    target = request.args.get('target')
    try:
        trainer.delete_section(name, section, action, target)
        return jsonify({'status': 'ok'})
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/models/<name>/import', methods=['POST'])
async def import_json(name):
    files = await request.files
    if 'file' not in files:
        return jsonify({'error': 'No file uploaded'}), 400
    file = files['file']
    with tempfile.NamedTemporaryFile(delete=False, suffix='.json') as tmp:
        content = await file.read()
        tmp.write(content)
        tmp_path = tmp.name
    try:
        count = trainer.import_json(name, tmp_path)
        os.unlink(tmp_path)
        return jsonify({'imported': count})
    except Exception as e:
        os.unlink(tmp_path)
        return jsonify({'error': str(e)}), 500

@app.route('/api/models/<name>/export', methods=['GET'])
async def export_json(name):
    try:
        data = trainer.export_json(name, full=True)
        import io
        import json
        buffer = io.BytesIO()
        buffer.write(json.dumps(data, indent=2).encode('utf-8'))
        buffer.seek(0)
        return await send_file(
            buffer,
            mimetype='application/json',
            attachment_filename=f'{name}.json',
            as_attachment=True
        )
    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True, port=5001)

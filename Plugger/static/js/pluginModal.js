import { apiPost, apiPut, apiGet } from './api.js';
import { showModal, hideModal, showAlertModal } from './modals.js';
import { loadPlugins } from './pluginGrid.js';

let currentPluginName = null;
let codeEditor = null;

const DEFAULT_CODE = `plugin name "My Plugin"

define input "hello"

when input "hello":
    say "Hello world!"
`;

export async function openPluginModal(name) {
    currentPluginName = name;
    const isNew = name === null;
    document.getElementById('pluginModalTitle').innerText = isNew ? 'Create New Plugin' : 'Edit Plugin';

    let code = DEFAULT_CODE;

    if (!isNew) {
        try {
            const plugin = await apiGet(`/api/plugins/${encodeURIComponent(name)}`);
            code = plugin.code || DEFAULT_CODE;
        } catch (err) {
            showAlertModal('Error', 'Failed to load plugin: ' + err.message);
            return;
        }
    }

    if (!codeEditor) {
        const textarea = document.createElement('textarea');
        document.getElementById('codeEditor').appendChild(textarea);
        codeEditor = CodeMirror.fromTextArea(textarea, {
            lineNumbers: true,
            mode: "customLang",
            theme: "monokai",
            autoCloseBrackets: true,
            matchBrackets: true,
            indentWithTabs: true,
            tabSize: 4,
            lineWrapping: true,
            extraKeys: {
                "Enter": function(cm) {
                    const cursor = cm.getCursor();
                    const line = cm.getLine(cursor.line);
                    if (/^[\t ]*$/.test(line)) {
                        cm.replaceSelection("\n", "end");
                        return;
                    }
                    const indentMatch = line.match(/^[\t ]*/);
                    const currentIndent = indentMatch ? indentMatch[0] : '';
                    const endsWithColon = line.trim().endsWith(':');
                    cm.replaceSelection("\n", "end");
                    let newIndent = currentIndent;
                    if (endsWithColon) {
                        newIndent += "\t";
                    }
                    cm.replaceSelection(newIndent, "end");
                }
            }
        });
    }
    codeEditor.setValue(code);
    showModal('pluginModal');
}

document.getElementById('pluginSaveBtn').onclick = async () => {
    const code = codeEditor.getValue();

    if (!code.trim()) {
        showAlertModal('Validation Error', 'Plugin code is required');
        return;
    }

    const data = { code };

    try {
        if (currentPluginName === null) {
            await apiPost('/api/plugins', data);
        } else {
            await apiPut(`/api/plugins/${encodeURIComponent(currentPluginName)}`, data);
        }
        hideModal('pluginModal');
        await loadPlugins();
    } catch (err) {
        showAlertModal('Error', 'Error saving plugin: ' + err.message);
    }
};

document.getElementById('pluginCancelBtn').onclick = () => {
    hideModal('pluginModal');
};
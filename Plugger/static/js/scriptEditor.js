import { showModal, hideModal } from './modals.js';
import { initBlockly } from './blockly.js';

let rootScriptWorkspace = null;
let nodeScriptWorkspace = null;
let currentEditingNodeId = null;

export function openRootScriptEditor(pluginCopy) {
    const modalId = 'rootScriptModal';
    let modalDiv = document.getElementById(modalId);
    if (!modalDiv) {
        modalDiv = document.createElement('div');
        modalDiv.id = modalId;
        modalDiv.className = 'modal';
        modalDiv.innerHTML = `
            <div class="modal-content script-modal-content">
                <h2>Edit Root Response Script</h2>
                <div id="rootScriptBlocklyDiv" style="height: 500px; width: 100%; border: 1px solid #4a4a7a;"></div>
                <div class="modal-actions">
                    <button class="cancel" id="rootScriptCancelBtn">Cancel</button>
                    <button class="save" id="rootScriptSaveBtn">Save Script</button>
                </div>
            </div>
        `;
        document.body.appendChild(modalDiv);
        document.getElementById('rootScriptCancelBtn').onclick = () => {
            hideModal(modalId);
            if (rootScriptWorkspace) rootScriptWorkspace.dispose();
            rootScriptWorkspace = null;
        };
        document.getElementById('rootScriptSaveBtn').onclick = () => {
            if (rootScriptWorkspace) {
                const xml = Blockly.Xml.workspaceToDom(rootScriptWorkspace);
                const scriptJson = Blockly.Xml.domToText(xml);
                pluginCopy.root_script_json = scriptJson;
            }
            hideModal(modalId);
            if (rootScriptWorkspace) rootScriptWorkspace.dispose();
            rootScriptWorkspace = null;
        };
    }
    if (rootScriptWorkspace) {
        rootScriptWorkspace.dispose();
        rootScriptWorkspace = null;
    }
    const container = document.getElementById('rootScriptBlocklyDiv');
    if (container) {
        while (container.firstChild) container.removeChild(container.firstChild);
    }
    setTimeout(() => {
        rootScriptWorkspace = initBlockly('rootScriptBlocklyDiv', pluginCopy.root_script_json || '{}');
    }, 100);
    showModal(modalId);
}

export function openNodeScriptEditor(nodeId, nodeName, scriptJson, onSave) {
    const modalId = 'nodeScriptModal';
    let modalDiv = document.getElementById(modalId);
    if (!modalDiv) {
        modalDiv = document.createElement('div');
        modalDiv.id = modalId;
        modalDiv.className = 'modal';
        modalDiv.innerHTML = `
            <div class="modal-content script-modal-content">
                <h2 id="nodeScriptModalTitle">Edit Response Script</h2>
                <div id="nodeScriptBlocklyDiv" style="height: 500px; width: 100%; border: 1px solid #4a4a7a;"></div>
                <div class="modal-actions">
                    <button class="cancel" id="nodeScriptCancelBtn">Cancel</button>
                    <button class="save" id="nodeScriptSaveBtn">Save Script</button>
                </div>
            </div>
        `;
        document.body.appendChild(modalDiv);
        document.getElementById('nodeScriptCancelBtn').onclick = () => {
            hideModal(modalId);
            if (nodeScriptWorkspace) nodeScriptWorkspace.dispose();
            nodeScriptWorkspace = null;
            currentEditingNodeId = null;
        };
        document.getElementById('nodeScriptSaveBtn').onclick = () => {
            if (nodeScriptWorkspace && currentEditingNodeId && onSave) {
                const xml = Blockly.Xml.workspaceToDom(nodeScriptWorkspace);
                const newScript = Blockly.Xml.domToText(xml);
                onSave(currentEditingNodeId, newScript);
            }
            hideModal(modalId);
            if (nodeScriptWorkspace) nodeScriptWorkspace.dispose();
            nodeScriptWorkspace = null;
            currentEditingNodeId = null;
        };
    }
    const titleSpan = document.getElementById('nodeScriptModalTitle');
    if (titleSpan) titleSpan.innerText = `Edit Script - ${nodeName}`;
    currentEditingNodeId = nodeId;

    if (nodeScriptWorkspace) {
        nodeScriptWorkspace.dispose();
        nodeScriptWorkspace = null;
    }
    const container = document.getElementById('nodeScriptBlocklyDiv');
    if (container) {
        while (container.firstChild) container.removeChild(container.firstChild);
    }
    setTimeout(() => {
        nodeScriptWorkspace = initBlockly('nodeScriptBlocklyDiv', scriptJson);
    }, 100);
    showModal(modalId);
}
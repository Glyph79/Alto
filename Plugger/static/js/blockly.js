// static/js/blockly.js
export function initBlockly(divId, scriptJson) {
    const workspace = Blockly.inject(divId, {
        toolbox: `<xml xmlns="https://developers.google.com/blockly/xml" id="toolbox" style="display: none">
            <category name="Start" colour="#a78bfa">
                <block type="start"></block>
            </category>
            <category name="API" colour="#6c63ff">
                <block type="call_api"></block>
            </category>
            <category name="Logic" colour="#ffaa66">
                <block type="controls_if"></block>
            </category>
            <category name="Text" colour="#00ff88">
                <block type="text"></block>
            </category>
            <category name="Response" colour="#00ff88">
                <block type="respond"></block>
            </category>
        </xml>`,
        grid: { spacing: 20, length: 3, colour: '#4a4a7a' },
        zoom: { controls: true, wheel: true },
        theme: getDarkTheme()
    });
    defineCustomBlocks();
    if (scriptJson && scriptJson !== '{}') {
        try {
            const xml = Blockly.Xml.textToDom(scriptJson);
            Blockly.Xml.domToWorkspace(xml, workspace);
        } catch(e) { console.error('Failed to load script', e); }
    }
    return workspace;
}

function getDarkTheme() {
    return Blockly.Theme.defineTheme('darkTheme', {
        'base': Blockly.Themes.Classic,
        'componentStyles': {
            'workspaceBackgroundColour': '#1a1a2e',
            'toolboxBackgroundColour': '#252547',
            'toolboxForegroundColour': '#fff',
            'flyoutBackgroundColour': '#2d2d5a',
            'flyoutForegroundColour': '#fff',
            'flyoutOpacity': 0.9,
            'scrollbarColour': '#4a4a7a',
            'scrollbarOpacity': 0.6,
            'cursorColour': '#6c63ff',
        },
        'blockStyles': {
            'start_blocks': { 'colourPrimary': '#a78bfa', 'colourSecondary': '#a78bfa', 'colourTertiary': '#8a5cf0' },
            'logic_blocks': { 'colourPrimary': '#ffaa66', 'colourSecondary': '#ffaa66', 'colourTertiary': '#cc8844' },
            'loop_blocks': { 'colourPrimary': '#ffaa66', 'colourSecondary': '#ffaa66', 'colourTertiary': '#cc8844' },
            'math_blocks': { 'colourPrimary': '#6c63ff', 'colourSecondary': '#6c63ff', 'colourTertiary': '#4a3fcc' },
            'text_blocks': { 'colourPrimary': '#00ff88', 'colourSecondary': '#00ff88', 'colourTertiary': '#00aa55' },
            'list_blocks': { 'colourPrimary': '#ff6b9d', 'colourSecondary': '#ff6b9d', 'colourTertiary': '#cc5577' },
            'colour_blocks': { 'colourPrimary': '#ffaa66', 'colourSecondary': '#ffaa66', 'colourTertiary': '#cc8844' },
            'variable_blocks': { 'colourPrimary': '#a78bfa', 'colourSecondary': '#a78bfa', 'colourTertiary': '#8a5cf0' },
            'procedure_blocks': { 'colourPrimary': '#a78bfa', 'colourSecondary': '#a78bfa', 'colourTertiary': '#8a5cf0' },
        },
        'categoryStyles': {
            'start_category': { 'colour': '#a78bfa' },
            'api_category': { 'colour': '#6c63ff' },
            'logic_category': { 'colour': '#ffaa66' },
            'response_category': { 'colour': '#00ff88' },
        },
    });
}

function defineCustomBlocks() {
    if (Blockly.Blocks['start']) return;

    // Start block (hat block, no previous connection)
    Blockly.Blocks['start'] = {
        init: function() {
            this.appendDummyInput()
                .appendField('start');
            this.setNextStatement(true, null);
            this.setColour(167, 139, 250);
        }
    };

    Blockly.Blocks['call_api'] = {
        init: function() {
            this.appendDummyInput()
                .appendField('call_api')
                .appendField(new Blockly.FieldDropdown([['GET','GET'],['POST','POST'],['PUT','PUT'],['DELETE','DELETE']]), 'METHOD');
            this.appendValueInput('URL')
                .setCheck('String')
                .appendField('URL');
            this.appendValueInput('HEADERS')
                .setCheck('String')
                .appendField('headers (JSON)');
            this.appendValueInput('BODY')
                .setCheck('String')
                .appendField('body');
            this.setPreviousStatement(true, null);
            this.setNextStatement(true, null);
            this.setColour(108, 99, 255);
        }
    };

    Blockly.Blocks['respond'] = {
        init: function() {
            this.appendValueInput('TEXT')
                .setCheck('String')
                .appendField('respond');
            this.setPreviousStatement(true, null);
            this.setNextStatement(false);
            this.setColour(0, 255, 136);
        }
    };
}
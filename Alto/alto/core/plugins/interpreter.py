#!/usr/bin/env python3
"""
Final DSL Interpreter – supports top‑level states.
Improved fuzzy matching: selects best match among all triggers.
"""

import re
import sys
import requests
from rapidfuzz import fuzz
from typing import Dict, List, Any, Optional, Tuple

class StateNode:
    def __init__(self, name: str, parent: Optional['StateNode'] = None):
        self.name = name
        self.parent = parent
        self.children: List['StateNode'] = []
        self.fallback: Optional[str] = None
        self.input_patterns: List[Tuple[List[str], List[str]]] = []
        self.actions: List[str] = []
        self.is_root = False
        self.fuzzy = True

class DSLInterpreter:
    def __init__(self, code: str, verbose: bool = True):
        self.verbose = verbose
        self.lines = code.split('\n')
        self.pos = 0
        self.variables: Dict[str, Any] = {}
        self.waiting_state: Optional[StateNode] = None
        self.triggers: Dict[str, StateNode] = {}   # pattern -> root node
        self.all_states: Dict[str, StateNode] = {}
        self.global_fuzzy = True
        self.parse()

    def log(self, msg: str):
        if self.verbose:
            print(f"[LOG] {msg}")

    def parse(self):
        self.log("Parsing...")
        stack = []  # (node, indent_level)
        i = 0
        while i < len(self.lines):
            raw = self.lines[i]
            line = raw.rstrip()
            stripped = line.strip()
            if not stripped or stripped.startswith('#'):
                i += 1
                continue

            indent = len(line) - len(line.lstrip())

            if indent == 0:
                if stripped.startswith('plugin name '):
                    self.plugin_name = stripped[12:].strip('"')
                elif stripped.startswith('plugin version '):
                    pass
                elif stripped.startswith('fuzzy = '):
                    val = stripped[7:].strip().lower()
                    self.global_fuzzy = (val == 'true')
                elif stripped.startswith('root '):
                    name = stripped[5:].rstrip(':')
                    node = StateNode(name)
                    node.is_root = True
                    node.fuzzy = self.global_fuzzy
                    self.all_states[name] = node
                    # root name itself is a trigger
                    self.triggers[name] = node
                    stack = [(node, 0)]
                elif stripped.startswith('state '):
                    name = stripped[6:].rstrip(':')
                    node = StateNode(name, parent=None)
                    node.fuzzy = self.global_fuzzy
                    self.all_states[name] = node
                    stack = [(node, 0)]
                i += 1
                continue

            # Adjust stack based on indent
            while stack and stack[-1][1] >= indent:
                stack.pop()
            if not stack:
                self.log(f"Warning: orphan line at indent {indent}: {stripped}")
                i += 1
                continue

            parent_node = stack[-1][0]

            if stripped.startswith('state '):
                name = stripped[6:].rstrip(':')
                node = StateNode(name, parent=parent_node)
                node.fuzzy = parent_node.fuzzy
                parent_node.children.append(node)
                self.all_states[name] = node
                stack.append((node, indent))
                i += 1
                continue

            if stripped.startswith('fuzzy = '):
                val = stripped[7:].strip().lower()
                parent_node.fuzzy = (val == 'true')
                i += 1
                continue

            if stripped.startswith('define wrong '):
                match = re.match(r'define wrong\s+"(.*)"', stripped)
                if match:
                    parent_node.fallback = match.group(1)
            elif stripped.startswith('define input '):
                pattern_part = stripped[13:].strip()
                patterns = re.findall(r'"([^"]*)"', pattern_part)
                # Add patterns as triggers if parent is root
                if parent_node.is_root:
                    for pat in patterns:
                        self.triggers[pat] = parent_node
                j = i + 1
                actions = []
                while j < len(self.lines):
                    next_line = self.lines[j].rstrip()
                    next_stripped = next_line.strip()
                    if not next_stripped or next_stripped.startswith('#'):
                        j += 1
                        continue
                    next_indent = len(next_line) - len(next_line.lstrip())
                    if next_indent <= indent:
                        break
                    if next_stripped.startswith('state ') or next_stripped.startswith('define '):
                        break
                    actions.append(next_stripped)
                    j += 1
                parent_node.input_patterns.append((patterns, actions))
                i = j - 1
            else:
                parent_node.actions.append(stripped)
            i += 1

        self.log("Parse complete.")
        self.log(f"Triggers: {list(self.triggers.keys())}")
        self.log(f"All states: {list(self.all_states.keys())}")

    def run(self, user_input: str) -> Optional[str]:
        self.log(f"User input: '{user_input}'")
        if self.waiting_state:
            self.log(f"Continuing conversation in state '{self.waiting_state.name}'")
            self.variables['input'] = user_input
            response = self._execute_state(self.waiting_state, user_response=user_input)
            return response

        # Collect all matching triggers with their scores
        matches = []
        for pattern, root_node in self.triggers.items():
            if self._matches_pattern(pattern, user_input, root_node.fuzzy):
                score = self._pattern_score(pattern, user_input, root_node.fuzzy)
                matches.append((score, len(pattern), pattern, root_node))
        if not matches:
            self.log("No matching trigger")
            return None

        # Choose best match: highest score, then longest pattern
        matches.sort(key=lambda x: (-x[0], -x[1]))
        best_score, best_len, best_pattern, best_root = matches[0]
        self.log(f"Best trigger: '{best_pattern}' (score {best_score}) -> root '{best_root.name}'")
        self.variables['input'] = user_input
        return self._execute_state(best_root)

    def _pattern_score(self, pattern: str, user_input: str, fuzzy: bool) -> float:
        """Return similarity score (0-100) for this pattern against user input."""
        if not fuzzy:
            return 100.0 if pattern == user_input else 0.0
        # Use token_set_ratio for better phrase matching
        return fuzz.token_set_ratio(pattern.lower(), user_input.lower())

    def _matches_pattern(self, pattern: str, user_input: str, fuzzy: bool) -> bool:
        """Check if pattern matches user_input (with optional fuzzy)."""
        if pattern == ".*":
            return True
        if fuzzy:
            score = self._pattern_score(pattern, user_input, fuzzy)
            return score >= 80
        return pattern == user_input

    def _execute_state(self, state: StateNode, user_response: Optional[str] = None) -> Optional[str]:
        self.log(f"Executing state: {state.name}")
        if user_response is not None:
            # For waiting state, we need to match input patterns
            # Collect all matching patterns and pick best
            matches = []
            for patterns, actions in state.input_patterns:
                for pat in patterns:
                    if self._matches_pattern(pat, user_response, state.fuzzy):
                        score = self._pattern_score(pat, user_response, state.fuzzy)
                        matches.append((score, len(pat), pat, actions))
            if matches:
                matches.sort(key=lambda x: (-x[0], -x[1]))
                best_score, best_len, best_pat, best_actions = matches[0]
                self.log(f"Pattern '{best_pat}' matched (score {best_score}, fuzzy={state.fuzzy})")
                return self._execute_actions(best_actions, state)
            if state.fallback:
                self.log(f"Fallback: {state.fallback}")
                self.waiting_state = state
                return state.fallback
            self.log("No pattern matched and no fallback")
            self.waiting_state = None
            return None
        return self._execute_actions(state.actions, state)

    def _execute_actions(self, actions: List[str], current_state: StateNode) -> Optional[str]:
        i = 0
        while i < len(actions):
            line = actions[i]
            self.log(f"Action: {line}")
            if line.startswith('say '):
                match = re.match(r'say\s+"(.*)"', line)
                if match:
                    text = self._interpolate(match.group(1))
                    if i + 1 < len(actions):
                        nxt = actions[i+1]
                        if nxt.startswith('next state '):
                            parts = nxt.split()
                            if len(parts) == 3:
                                target_name = parts[2]
                                if target_name in self.all_states:
                                    target = self.all_states[target_name]
                                    self.log(f"Next state to: {target_name}")
                                    self.waiting_state = None
                                    return text + "\n" + self._execute_state(target)
                                else:
                                    self.log(f"Unknown state: {target_name}")
                                    return text
                        elif nxt == 'stop':
                            self.log("Stop after say")
                            self.waiting_state = None
                            return text
                    self.waiting_state = current_state
                    return text
            elif line.startswith('set '):
                match = re.match(r'set\s+(\w+)\s*=\s*(.+)', line)
                if match:
                    var, expr = match.groups()
                    value = self._evaluate_expr(expr)
                    self.variables[var] = value
                    self.log(f"Set {var} = {value}")
            elif line.startswith('call api '):
                match = re.match(r'call api\s+"(.*)"', line)
                if match:
                    url = self._interpolate(match.group(1))
                    self.log(f"Calling API: {url}")
                    try:
                        resp = requests.get(url, timeout=10)
                        self.variables['status'] = resp.status_code
                        if resp.status_code == 200:
                            try:
                                self.variables['result'] = resp.json()
                            except:
                                self.variables['result'] = {}
                        else:
                            self.variables['result'] = {}
                    except Exception as e:
                        self.log(f"API error: {e}")
                        self.variables['status'] = 0
                        self.variables['result'] = {}
            elif line == 'stop':
                self.log("Stop")
                self.waiting_state = None
                return None
            elif line.startswith('next state '):
                parts = line.split()
                if len(parts) == 3:
                    target_name = parts[2]
                    if target_name in self.all_states:
                        target = self.all_states[target_name]
                        self.log(f"Next state to: {target_name}")
                        self.waiting_state = None
                        return self._execute_state(target)
                    else:
                        self.log(f"Unknown state: {target_name}")
                        return None
            elif line.startswith('back'):
                if current_state.parent:
                    self.log(f"Back to parent: {current_state.parent.name}")
                    self.waiting_state = None
                    return self._execute_state(current_state.parent)
                else:
                    self.log("No parent to go back to")
                    return None
            elif line.startswith('if '):
                condition = line[3:].rstrip(':')
                block = []
                j = i + 1
                while j < len(actions):
                    nxt = actions[j]
                    if nxt.startswith('elif ') or nxt.startswith('else:'):
                        break
                    block.append(nxt)
                    j += 1
                if self._evaluate_condition(condition):
                    result = self._execute_actions(block, current_state)
                    if result is not None:
                        return result
                i = j - 1
            elif line.startswith('elif '):
                condition = line[5:].rstrip(':')
                block = []
                j = i + 1
                while j < len(actions):
                    nxt = actions[j]
                    if nxt.startswith('elif ') or nxt.startswith('else:'):
                        break
                    block.append(nxt)
                    j += 1
                if self._evaluate_condition(condition):
                    result = self._execute_actions(block, current_state)
                    if result is not None:
                        return result
                i = j - 1
            elif line.startswith('else:'):
                block = []
                j = i + 1
                while j < len(actions):
                    nxt = actions[j]
                    if nxt.startswith('elif ') or nxt.startswith('else:'):
                        break
                    block.append(nxt)
                    j += 1
                result = self._execute_actions(block, current_state)
                if result is not None:
                    return result
                i = j - 1
            i += 1
        self.waiting_state = None
        return None

    def _evaluate_condition(self, cond: str) -> bool:
        cond = self._interpolate(cond)
        try:
            return eval(cond, {}, self.variables)
        except:
            return False

    def _evaluate_expr(self, expr: str) -> Any:
        expr = expr.strip()
        try:
            return int(expr)
        except:
            try:
                return float(expr)
            except:
                pass
        if expr == 'input':
            return self.variables.get('input', '')
        if expr.startswith('result.'):
            parts = expr.split('.')
            value = self.variables.get('result', {})
            for part in parts[1:]:
                if isinstance(value, dict):
                    value = value.get(part)
                elif isinstance(value, list) and len(value) > 0:
                    value = value[0].get(part) if isinstance(value[0], dict) else None
                else:
                    value = None
                if value is None:
                    break
            return value
        return self.variables.get(expr, expr)

    def _interpolate(self, text: str) -> str:
        def repl(m):
            var = m.group(1)
            val = self._evaluate_expr(var)
            return str(val) if val is not None else ""
        return re.sub(r'\{([^{}]+)\}', repl, text)

def main():
    if len(sys.argv) != 2:
        print("Usage: python run.py <plugin.plug>")
        sys.exit(1)
    with open(sys.argv[1], 'r', encoding='utf-8') as f:
        code = f.read()
    interp = DSLInterpreter(code, verbose=True)
    print("\nPlugin loaded. Available triggers:", list(interp.triggers.keys()))
    print("Type a trigger or 'exit' to quit.\n")
    while True:
        user_input = input("> ").strip()
        if user_input.lower() in ('exit', 'quit'):
            break
        response = interp.run(user_input)
        if response is not None:
            print(f"\n{response}\n")
        else:
            print("(no response)\n")

if __name__ == '__main__':
    main()
# alto/core/session_tree.py
from collections import OrderedDict

class SessionTree:
    MAX_LOADED_NODES = 10

    def __init__(self, matcher, group_id, path=None):
        self.matcher = matcher
        self.group_id = group_id
        self._nodes = {}
        self._roots = []
        self.path = path or []
        self._loaded_nodes = OrderedDict()
        self._load_roots()

    def _load_roots(self):
        self._roots = self.matcher.adapter.get_root_nodes(self.group_id)
        for node in self._roots:
            self._nodes[node["id"]] = node

    def _load_children(self, node_id):
        children = self.matcher.adapter.get_node_children(node_id)
        if node_id in self._nodes:
            self._nodes[node_id]["children"] = children
        for child in children:
            self._nodes[child["id"]] = child

    def _ensure_questions(self, node_id):
        node = self._nodes.get(node_id)
        if not node:
            return
        if node_id in self._loaded_nodes:
            self._loaded_nodes.move_to_end(node_id)
            return
        questions = self.matcher.adapter.get_node_questions(node_id)
        node["questions"] = questions
        self._loaded_nodes[node_id] = node
        while len(self._loaded_nodes) > self.MAX_LOADED_NODES:
            oldest_id, _ = self._loaded_nodes.popitem(last=False)
            if oldest_id in self._nodes:
                self._nodes[oldest_id]["questions"] = None

    def load_questions_for_node(self, node_id):
        self._ensure_questions(node_id)

    def ensure_answers(self, node_id):
        node = self._nodes.get(node_id)
        if node and not node.get("answers_loaded"):
            answers = self.matcher.adapter.get_node_answers(node_id)
            node["answers"] = answers
            node["answers_loaded"] = True
            if node_id not in self._loaded_nodes:
                self._loaded_nodes[node_id] = node
                while len(self._loaded_nodes) > self.MAX_LOADED_NODES:
                    oldest_id, _ = self._loaded_nodes.popitem(last=False)
                    if oldest_id in self._nodes:
                        self._nodes[oldest_id]["answers"] = None
                        self._nodes[oldest_id]["answers_loaded"] = False

    def candidates(self, path):
        if not path:
            for root in self._roots:
                self._ensure_questions(root["id"])
            return self._roots
        if path[-1] not in self._nodes:
            self._nodes[path[-1]] = {"id": path[-1], "questions": None, "children": []}
        current = self._nodes[path[-1]]
        if not current.get("children"):
            self._load_children(current["id"])
        result = [self._nodes[n] for n in path if n in self._nodes] + current.get("children", [])
        for node in result:
            self._ensure_questions(node["id"])
        return result

    def move_to(self, nid, path):
        if nid in path:
            return path[:path.index(nid)+1]
        if path and self._nodes[path[-1]].get("children"):
            if any(c["id"] == nid for c in self._nodes[path[-1]]["children"]):
                return path + [nid]
        if any(r["id"] == nid for r in self._roots):
            return [nid]
        return [nid]

    def roots(self):
        return self._roots

    def current_node(self):
        if not self.path:
            return None
        return self._nodes.get(self.path[-1])
# alto/core/session_tree.py
from collections import OrderedDict
from typing import List, Dict, Optional
from .cache import SharedDataCache

class SessionTree:
    def __init__(self, matcher, group_id: int, path: List[int] = None):
        self.matcher = matcher
        self.group_id = group_id
        self.cache: SharedDataCache = matcher.cache
        self.path = path or []
        
        # Track which node IDs we hold references to (for cleanup)
        self._referenced_nodes: List[int] = []
        
        # Roots are lightweight references
        self._roots: List[Dict] = []
        self._load_roots()

    def __del__(self):
        self.release()

    def release(self):
        """Release all node references held by this tree."""
        if hasattr(self, '_referenced_nodes') and self._referenced_nodes:
            self.cache.release_many_nodes(self._referenced_nodes)
            self._referenced_nodes.clear()

    def _load_roots(self):
        """Load root nodes from adapter, store references in cache."""
        roots = self.matcher.adapter.get_root_nodes(self.group_id)
        self._roots = []
        for root_dict in roots:
            node_id = root_dict['id']
            node = self._get_node(node_id)
            # Update with adapter-provided fields
            node['branch_name'] = root_dict.get('branch_name', '')
            node['fallback_id'] = root_dict.get('fallback_id')
            self._roots.append(node)

    def _get_node(self, node_id: int) -> Dict:
        """Get node from shared cache and track reference."""
        node = self.matcher.get_node_data(node_id)
        self._referenced_nodes.append(node_id)
        return node

    def _load_children(self, node_id: int):
        """Children are already loaded as part of node data; no-op if cached."""
        node = self._get_node(node_id)  # ensures children_ids are populated
        return node.get('children', [])

    def _ensure_questions(self, node_id: int):
        """Questions are lazy‑loaded in cache; just access to trigger load."""
        node = self._get_node(node_id)
        # Accessing 'questions' may trigger lazy load inside cache
        _ = node.get('questions')

    def ensure_answers(self, node_id: int):
        """Answers lazy‑loaded."""
        node = self._get_node(node_id)
        _ = node.get('answers')

    def candidates(self, path: List[int]) -> List[Dict]:
        """Return nodes that are candidates for matching."""
        if not path:
            for root in self._roots:
                self._ensure_questions(root['id'])
            return self._roots
        
        current_id = path[-1]
        current = self._get_node(current_id)
        if 'children' not in current or not current['children']:
            children_dicts = self._load_children(current_id)
            current['children'] = children_dicts
        
        # Build result: nodes on path + children
        result = []
        for nid in path:
            result.append(self._get_node(nid))
        for child in current['children']:
            result.append(self._get_node(child['id']))
        
        for node in result:
            self._ensure_questions(node['id'])
        return result

    def move_to(self, nid: int, path: List[int]) -> List[int]:
        """Compute new path after moving to node nid."""
        if nid in path:
            return path[:path.index(nid)+1]
        if path:
            current = self._get_node(path[-1])
            if any(c['id'] == nid for c in current.get('children', [])):
                return path + [nid]
        if any(r['id'] == nid for r in self._roots):
            return [nid]
        return [nid]

    def roots(self) -> List[Dict]:
        return self._roots

    def current_node(self) -> Optional[Dict]:
        if not self.path:
            return None
        return self._get_node(self.path[-1])
# alto/core/cache.py
import threading
from collections import OrderedDict
from typing import Dict, List, Optional, Set, Any

class SharedDataCache:
    """
    Thread‑safe cache for immutable model data (groups, nodes, fallbacks, etc.)
    with reference counting and LRU eviction for zero‑reference items.
    """
    def __init__(self, max_size: int = 10000):
        self._max_size = max_size
        self._lock = threading.RLock()
        
        # Cached data
        self._groups: Dict[int, Dict] = {}          # group_id -> group_data
        self._nodes: Dict[int, Dict] = {}           # node_id -> node_data
        self._fallbacks: Dict[int, List[str]] = {}  # fallback_id -> answers
        self._variants_map: Optional[Dict[str, Set[str]]] = None  # word -> set of synonyms
        self._topics: Optional[List[str]] = None
        self._sections: Optional[List[str]] = None
        
        # Reference counts
        self._group_refs: Dict[int, int] = {}
        self._node_refs: Dict[int, int] = {}
        self._fallback_refs: Dict[int, int] = {}
        
        # LRU for zero‑ref items (candidates for eviction)
        self._lru_groups: OrderedDict = OrderedDict()
        self._lru_nodes: OrderedDict = OrderedDict()
        self._lru_fallbacks: OrderedDict = OrderedDict()
        
        # Locks for lazy loading specific items
        self._group_locks: Dict[int, threading.Lock] = {}
        self._node_locks: Dict[int, threading.Lock] = {}
        self._fallback_locks: Dict[int, threading.Lock] = {}

    # ---------- Generic helpers ----------
    def _get_lock(self, locks_dict: dict, key: int) -> threading.Lock:
        with self._lock:
            if key not in locks_dict:
                locks_dict[key] = threading.Lock()
            return locks_dict[key]

    def _evict_if_needed(self, data_dict: dict, ref_dict: dict, lru: OrderedDict):
        while len(data_dict) > self._max_size and lru:
            key, _ = lru.popitem(last=False)
            if key in data_dict and ref_dict.get(key, 0) <= 0:
                del data_dict[key]
                ref_dict.pop(key, None)

    # ---------- Groups ----------
    def get_group(self, group_id: int, loader) -> Dict:
        with self._lock:
            if group_id in self._groups:
                self._group_refs[group_id] = self._group_refs.get(group_id, 0) + 1
                self._lru_groups.pop(group_id, None)
                return self._groups[group_id]
        
        lock = self._get_lock(self._group_locks, group_id)
        with lock:
            # Double‑check after acquiring lock
            with self._lock:
                if group_id in self._groups:
                    self._group_refs[group_id] = self._group_refs.get(group_id, 0) + 1
                    self._lru_groups.pop(group_id, None)
                    return self._groups[group_id]
            
            # Load from adapter
            group_data = loader(group_id)
            with self._lock:
                self._groups[group_id] = group_data
                self._group_refs[group_id] = 1
                self._evict_if_needed(self._groups, self._group_refs, self._lru_groups)
            return group_data

    def release_group(self, group_id: int):
        with self._lock:
            if group_id in self._group_refs:
                self._group_refs[group_id] -= 1
                if self._group_refs[group_id] <= 0:
                    self._lru_groups[group_id] = None
                    self._group_refs.pop(group_id, None)
                    self._evict_if_needed(self._groups, self._group_refs, self._lru_groups)

    # ---------- Nodes ----------
    def get_node(self, node_id: int, loader) -> Dict:
        with self._lock:
            if node_id in self._nodes:
                self._node_refs[node_id] = self._node_refs.get(node_id, 0) + 1
                self._lru_nodes.pop(node_id, None)
                return self._nodes[node_id]
        
        lock = self._get_lock(self._node_locks, node_id)
        with lock:
            with self._lock:
                if node_id in self._nodes:
                    self._node_refs[node_id] = self._node_refs.get(node_id, 0) + 1
                    self._lru_nodes.pop(node_id, None)
                    return self._nodes[node_id]
            
            node_data = loader(node_id)
            with self._lock:
                self._nodes[node_id] = node_data
                self._node_refs[node_id] = 1
                self._evict_if_needed(self._nodes, self._node_refs, self._lru_nodes)
            return node_data

    def release_node(self, node_id: int):
        with self._lock:
            if node_id in self._node_refs:
                self._node_refs[node_id] -= 1
                if self._node_refs[node_id] <= 0:
                    self._lru_nodes[node_id] = None
                    self._node_refs.pop(node_id, None)
                    self._evict_if_needed(self._nodes, self._node_refs, self._lru_nodes)

    # ---------- Fallbacks ----------
    def get_fallback(self, fallback_id: int, loader) -> List[str]:
        with self._lock:
            if fallback_id in self._fallbacks:
                self._fallback_refs[fallback_id] = self._fallback_refs.get(fallback_id, 0) + 1
                self._lru_fallbacks.pop(fallback_id, None)
                return self._fallbacks[fallback_id]
        
        lock = self._get_lock(self._fallback_locks, fallback_id)
        with lock:
            with self._lock:
                if fallback_id in self._fallbacks:
                    self._fallback_refs[fallback_id] = self._fallback_refs.get(fallback_id, 0) + 1
                    self._lru_fallbacks.pop(fallback_id, None)
                    return self._fallbacks[fallback_id]
            
            answers = loader(fallback_id)
            with self._lock:
                self._fallbacks[fallback_id] = answers
                self._fallback_refs[fallback_id] = 1
                self._evict_if_needed(self._fallbacks, self._fallback_refs, self._lru_fallbacks)
            return answers

    def release_fallback(self, fallback_id: int):
        with self._lock:
            if fallback_id in self._fallback_refs:
                self._fallback_refs[fallback_id] -= 1
                if self._fallback_refs[fallback_id] <= 0:
                    self._lru_fallbacks[fallback_id] = None
                    self._fallback_refs.pop(fallback_id, None)
                    self._evict_if_needed(self._fallbacks, self._fallback_refs, self._lru_fallbacks)

    # ---------- Variants (global, no ref counting, loaded once) ----------
    def get_variants_map(self, loader) -> Dict[str, Set[str]]:
        if self._variants_map is not None:
            return self._variants_map
        with self._lock:
            if self._variants_map is None:
                self._variants_map = loader()
        return self._variants_map

    # ---------- Topics & Sections (simple lists) ----------
    def get_topics(self, loader) -> List[str]:
        if self._topics is not None:
            return self._topics
        with self._lock:
            if self._topics is None:
                self._topics = loader()
        return self._topics

    def get_sections(self, loader) -> List[str]:
        if self._sections is not None:
            return self._sections
        with self._lock:
            if self._sections is None:
                self._sections = loader()
        return self._sections

    # ---------- Bulk release for SessionTree ----------
    def release_many_nodes(self, node_ids: List[int]):
        with self._lock:
            for nid in node_ids:
                if nid in self._node_refs:
                    self._node_refs[nid] -= 1
                    if self._node_refs[nid] <= 0:
                        self._lru_nodes[nid] = None
                        self._node_refs.pop(nid, None)
            self._evict_if_needed(self._nodes, self._node_refs, self._lru_nodes)

    def release_many_groups(self, group_ids: List[int]):
        with self._lock:
            for gid in group_ids:
                if gid in self._group_refs:
                    self._group_refs[gid] -= 1
                    if self._group_refs[gid] <= 0:
                        self._lru_groups[gid] = None
                        self._group_refs.pop(gid, None)
            self._evict_if_needed(self._groups, self._group_refs, self._lru_groups)
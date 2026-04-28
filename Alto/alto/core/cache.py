# alto/core/cache.py
import threading
import time
from collections import OrderedDict
from typing import Dict, List, Optional, Set, Any
from ..config import config

class SharedDataCache:
    """
    Thread‑safe cache for immutable model data (groups, nodes, fallbacks, etc.)
    with reference counting, LRU eviction, and idle‑timeout eviction.
    """
    def __init__(self, max_size: int = 10000, group_linger_seconds: int = 60):
        self._max_size = max_size
        self._eviction_watermark = int(max_size * 1.2)
        self._group_linger_seconds = group_linger_seconds
        self._lock = threading.RLock()
        
        # Cached data
        self._groups: Dict[int, Dict] = {}
        self._nodes: Dict[int, Dict] = {}
        self._fallbacks: Dict[int, List[str]] = {}
        self._variants_map: Optional[Dict[str, Set[str]]] = None
        self._topics: Optional[List[str]] = None
        self._sections: Optional[List[str]] = None
        
        # Reference counts
        self._group_refs: Dict[int, int] = {}
        self._node_refs: Dict[int, int] = {}
        self._fallback_refs: Dict[int, int] = {}
        
        # Linger timestamps for groups (only when ref count == 0)
        self._group_linger_until: Dict[int, float] = {}
        
        # LRU for zero‑ref items (candidates for eviction)
        self._lru_groups: OrderedDict = OrderedDict()
        self._lru_nodes: OrderedDict = OrderedDict()
        self._lru_fallbacks: OrderedDict = OrderedDict()
        
        # Locks for lazy loading specific items
        self._group_locks: Dict[int, threading.Lock] = {}
        self._node_locks: Dict[int, threading.Lock] = {}
        self._fallback_locks: Dict[int, threading.Lock] = {}
        
        # Idle‑timeout eviction data
        self._node_last_used: Dict[int, float] = {}
        self._fallback_last_used: Dict[int, float] = {}
        self._idle_enabled = config.getboolean('ai', 'cache_idle_eviction_enabled', fallback=True)
        self._idle_timeout = config.getint('ai', 'cache_idle_timeout_seconds', fallback=300)
        self._cleanup_interval = config.getint('ai', 'cache_cleanup_interval_seconds', fallback=300)
        
        # Start background idle eviction thread if enabled
        if self._idle_enabled and self._idle_timeout > 0:
            self._start_idle_cleanup()

    # ---------- Generic helpers ----------
    def _get_lock(self, locks_dict: dict, key: int) -> threading.Lock:
        with self._lock:
            if key not in locks_dict:
                locks_dict[key] = threading.Lock()
            return locks_dict[key]

    def _evict_if_needed(self, data_dict: dict, ref_dict: dict, lru: OrderedDict):
        if len(data_dict) <= self._eviction_watermark:
            return
        to_remove = len(data_dict) - self._max_size
        removed = 0
        for key, _ in list(lru.items()):
            if removed >= to_remove:
                break
            if key in data_dict and ref_dict.get(key, 0) <= 0:
                if key in self._group_linger_until:
                    if time.time() < self._group_linger_until[key]:
                        continue
                    else:
                        del self._group_linger_until[key]
                del data_dict[key]
                ref_dict.pop(key, None)
                lru.pop(key, None)
                removed += 1

    # ---------- Groups with linger ----------
    def get_group(self, group_id: int, loader) -> Dict:
        with self._lock:
            if group_id in self._groups:
                ref = self._group_refs.get(group_id, 0)
                if ref == 0 and group_id in self._group_linger_until:
                    if time.time() < self._group_linger_until[group_id]:
                        self._group_refs[group_id] = 1
                        del self._group_linger_until[group_id]
                        self._lru_groups.pop(group_id, None)
                        return self._groups[group_id]
                    else:
                        del self._groups[group_id]
                        self._group_refs.pop(group_id, None)
                        self._group_linger_until.pop(group_id, None)
                        self._lru_groups.pop(group_id, None)
                else:
                    self._group_refs[group_id] = ref + 1
                    self._lru_groups.pop(group_id, None)
                    return self._groups[group_id]

        lock = self._get_lock(self._group_locks, group_id)
        with lock:
            with self._lock:
                if group_id in self._groups:
                    ref = self._group_refs.get(group_id, 0)
                    if ref == 0 and group_id in self._group_linger_until:
                        if time.time() < self._group_linger_until[group_id]:
                            self._group_refs[group_id] = 1
                            del self._group_linger_until[group_id]
                            self._lru_groups.pop(group_id, None)
                            return self._groups[group_id]
            group_data = loader(group_id)
            with self._lock:
                self._groups[group_id] = group_data
                self._group_refs[group_id] = 1
                self._group_linger_until.pop(group_id, None)
                self._evict_if_needed(self._groups, self._group_refs, self._lru_groups)
            return group_data

    def release_group(self, group_id: int):
        with self._lock:
            if group_id in self._group_refs:
                self._group_refs[group_id] -= 1
                if self._group_refs[group_id] <= 0:
                    self._group_linger_until[group_id] = time.time() + self._group_linger_seconds
                    self._lru_groups.pop(group_id, None)

    # ---------- Nodes with idle tracking ----------
    def get_node(self, node_id: int, loader) -> Dict:
        with self._lock:
            if node_id in self._nodes:
                self._node_refs[node_id] = self._node_refs.get(node_id, 0) + 1
                self._lru_nodes.pop(node_id, None)
                self._node_last_used[node_id] = time.time()
                return self._nodes[node_id]
        
        lock = self._get_lock(self._node_locks, node_id)
        with lock:
            with self._lock:
                if node_id in self._nodes:
                    self._node_refs[node_id] = self._node_refs.get(node_id, 0) + 1
                    self._lru_nodes.pop(node_id, None)
                    self._node_last_used[node_id] = time.time()
                    return self._nodes[node_id]
            
            node_data = loader(node_id)
            with self._lock:
                self._nodes[node_id] = node_data
                self._node_refs[node_id] = 1
                self._node_last_used[node_id] = time.time()
                self._evict_if_needed(self._nodes, self._node_refs, self._lru_nodes)
            return node_data

    def release_node(self, node_id: int):
        with self._lock:
            if node_id in self._node_refs:
                self._node_refs[node_id] -= 1
                if self._node_refs[node_id] <= 0:
                    self._lru_nodes[node_id] = None
                    self._evict_if_needed(self._nodes, self._node_refs, self._lru_nodes)

    # ---------- Fallbacks with idle tracking ----------
    def get_fallback(self, fallback_id: int, loader) -> List[str]:
        with self._lock:
            if fallback_id in self._fallbacks:
                self._fallback_refs[fallback_id] = self._fallback_refs.get(fallback_id, 0) + 1
                self._lru_fallbacks.pop(fallback_id, None)
                self._fallback_last_used[fallback_id] = time.time()
                return self._fallbacks[fallback_id]
        
        lock = self._get_lock(self._fallback_locks, fallback_id)
        with lock:
            with self._lock:
                if fallback_id in self._fallbacks:
                    self._fallback_refs[fallback_id] = self._fallback_refs.get(fallback_id, 0) + 1
                    self._lru_fallbacks.pop(fallback_id, None)
                    self._fallback_last_used[fallback_id] = time.time()
                    return self._fallbacks[fallback_id]
            
            answers = loader(fallback_id)
            with self._lock:
                self._fallbacks[fallback_id] = answers
                self._fallback_refs[fallback_id] = 1
                self._fallback_last_used[fallback_id] = time.time()
                self._evict_if_needed(self._fallbacks, self._fallback_refs, self._lru_fallbacks)
            return answers

    def release_fallback(self, fallback_id: int):
        with self._lock:
            if fallback_id in self._fallback_refs:
                self._fallback_refs[fallback_id] -= 1
                if self._fallback_refs[fallback_id] <= 0:
                    self._lru_fallbacks[fallback_id] = None
                    self._evict_if_needed(self._fallbacks, self._fallback_refs, self._lru_fallbacks)

    # ---------- Idle eviction background thread (batched deletions) ----------
    def _start_idle_cleanup(self):
        def _cleanup_loop():
            while True:
                time.sleep(self._cleanup_interval)
                if not self._idle_enabled or self._idle_timeout <= 0:
                    continue
                now = time.time()
                timeout = self._idle_timeout
                
                # Collect candidates under a brief lock
                with self._lock:
                    node_candidates = [
                        nid for nid, last_used in self._node_last_used.items()
                        if self._node_refs.get(nid, 0) == 0 and now - last_used > timeout
                    ]
                    fallback_candidates = [
                        fid for fid, last_used in self._fallback_last_used.items()
                        if self._fallback_refs.get(fid, 0) == 0 and now - last_used > timeout
                    ]
                
                # Delete all candidates in one batch (re‑acquire lock once)
                if node_candidates or fallback_candidates:
                    with self._lock:
                        for nid in node_candidates:
                            # Re‑verify conditions before deletion
                            if (nid in self._nodes and self._node_refs.get(nid, 0) == 0 and
                                now - self._node_last_used.get(nid, 0) > timeout):
                                del self._nodes[nid]
                                self._node_refs.pop(nid, None)
                                self._lru_nodes.pop(nid, None)
                                self._node_last_used.pop(nid, None)
                        for fid in fallback_candidates:
                            if (fid in self._fallbacks and self._fallback_refs.get(fid, 0) == 0 and
                                now - self._fallback_last_used.get(fid, 0) > timeout):
                                del self._fallbacks[fid]
                                self._fallback_refs.pop(fid, None)
                                self._lru_fallbacks.pop(fid, None)
                                self._fallback_last_used.pop(fid, None)
        
        thread = threading.Thread(target=_cleanup_loop, daemon=True)
        thread.start()

    # ---------- Variants (global) ----------
    def get_variants_map(self, loader) -> Dict[str, Set[str]]:
        if self._variants_map is not None:
            return self._variants_map
        with self._lock:
            if self._variants_map is None:
                self._variants_map = loader()
        return self._variants_map

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
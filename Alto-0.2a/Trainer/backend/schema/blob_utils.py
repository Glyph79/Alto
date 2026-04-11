import hashlib
import sqlite3
import datetime
import re
from typing import Optional
from .compression import compress_blob, decompress_blob

def normalise_question_string(s: str) -> str:
    """Trim, collapse whitespace, and lower‑case for deduplication."""
    if not s:
        return ''
    s = re.sub(r'\s+', ' ', s)
    return s.strip().lower()

def get_blob_hash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()

def store_blob(conn: sqlite3.Connection, raw_data: bytes, normalise: bool = False) -> int:
    if not raw_data:
        return 0
    
    if normalise:
        from ..utils.msgpack_helpers import unpack_array, pack_array
        original_list = unpack_array(raw_data)
        normalised_list = [normalise_question_string(s) for s in original_list]
        normalised_raw = pack_array(normalised_list)
        blob_hash = get_blob_hash(normalised_raw)
    else:
        blob_hash = get_blob_hash(raw_data)
    
    cur = conn.execute("SELECT id, ref_count FROM blob_store WHERE hash = ?", (blob_hash,))
    row = cur.fetchone()
    if row:
        conn.execute("UPDATE blob_store SET ref_count = ref_count + 1, last_used = ? WHERE id = ?",
                     (datetime.datetime.now().isoformat(), row[0]))
        return row[0]
    
    compressed = compress_blob(raw_data)
    now = datetime.datetime.now().isoformat()
    cur = conn.execute(
        "INSERT INTO blob_store (hash, data, ref_count, created_at, last_used) VALUES (?, ?, ?, ?, ?) RETURNING id",
        (blob_hash, compressed, 1, now, now)
    )
    return cur.fetchone()[0]

def release_blob(conn: sqlite3.Connection, blob_id: int):
    if blob_id == 0:
        return
    cur = conn.execute("SELECT ref_count FROM blob_store WHERE id = ?", (blob_id,))
    row = cur.fetchone()
    if not row:
        return
    if row[0] <= 1:
        conn.execute("DELETE FROM blob_store WHERE id = ?", (blob_id,))
    else:
        conn.execute("UPDATE blob_store SET ref_count = ref_count - 1 WHERE id = ?", (blob_id,))

def get_blob_data(conn: sqlite3.Connection, blob_id: int) -> bytes:
    if blob_id == 0:
        return b''
    cur = conn.execute("SELECT data FROM blob_store WHERE id = ?", (blob_id,))
    row = cur.fetchone()
    if not row:
        raise ValueError(f"Blob id {blob_id} not found")
    return decompress_blob(row[0])
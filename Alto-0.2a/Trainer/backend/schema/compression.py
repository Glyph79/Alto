import zstandard as zstd
from backend.config import config

def _get_compression_settings():
    enabled = config.getboolean('storage', 'compression_enabled', fallback=True)
    level = config.getint('storage', 'compression_level', fallback=6)
    return enabled, level

# Flag byte values
FLAG_RAW = 0
FLAG_ZSTD = 1

def compress_blob(data: bytes) -> bytes:
    """Compress with zstd if beneficial, prefix with flag byte."""
    if not data:
        return bytes([FLAG_RAW])
    
    enabled, level = _get_compression_settings()
    if not enabled:
        return bytes([FLAG_RAW]) + data
    
    compressed = zstd.compress(data, level=level)
    if len(compressed) < len(data):
        return bytes([FLAG_ZSTD]) + compressed
    else:
        return bytes([FLAG_RAW]) + data

def decompress_blob(data: bytes) -> bytes:
    """Decompress based on flag byte."""
    if not data:
        return b''
    flag = data[0]
    payload = data[1:]
    if flag == FLAG_ZSTD:
        return zstd.decompress(payload)
    else:  # FLAG_RAW or unknown (treat as raw)
        return payload
import zlib

def compress_blob(data: bytes) -> bytes:
    return zlib.compress(data, level=6)

def decompress_blob(data: bytes) -> bytes:
    return zlib.decompress(data)
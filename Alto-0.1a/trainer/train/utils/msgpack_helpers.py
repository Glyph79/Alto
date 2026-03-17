import msgpack
from typing import List

def pack_array(arr: List) -> bytes:
    return msgpack.packb(arr, use_bin_type=True)

def unpack_array(data: bytes) -> List:
    return msgpack.unpackb(data, raw=False)
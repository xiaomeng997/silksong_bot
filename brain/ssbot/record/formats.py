"""On-disk layout of an episode recording (DESIGN §3.10), shared by the recorder, the reader, the viewer and tests.

    runs/<YYYY-MM-DD>/<profile>/<episode>/
      meta.json              HELLO, versions.lock (+ sha256), git SHA, config, start/end QPC, instance, final stats
      state.msgpack.zst      STATE messages: independent zstd frames ("chunks") of CHUNK_FRAMES records each
      state.index.jsonl      one line per chunk: byte offset/length and frame range, so a seek reads one chunk
      terrain.msgpack.zst    TERRAIN messages, one zstd frame per message (+ terrain.index.jsonl)
      progress.msgpack.zst   PROGRESS messages, one zstd frame per message (+ progress.index.jsonl)
      events.jsonl           every STATE "ev" entry: {"frame", "kind", "data", "state_frame", "q"}

A decompressed chunk is a plain sequence of records (little-endian):

    u64 recv_ns | wire frame = u32 length | u8 msg_type | u8 schema | u16 flags | u32 seq | msgpack payload

The wire frame is stored byte for byte as the oracle sent it (DESIGN §4.6), so nothing is lost or re-encoded.
recv_ns is time.perf_counter_ns() when the OracleLink reader thread handed the frame over; on Windows perf_counter is
QPC, the same clock as the oracle's "q" (in ticks of HELLO.qpc_freq), so recv_ns - q * 1e9 / qpc_freq is the
end-of-frame -> brain latency. Concatenated zstd frames are a valid zstd stream: `zstd -d state.msgpack.zst` yields
the raw record stream even without the index.
"""
import base64
import json
import struct
from collections.abc import Iterable, Iterator
from typing import Any

import msgpack
import zstandard

from ssbot.ipc.framing import HEADER, MAX_MESSAGE, MsgType

CHUNK_FRAMES = 600
RECV = struct.Struct("<Q")
RECORD_PREFIX = RECV.size  # bytes before the wire frame
FLAG_ZSTD = 1  # wire flags bit0: payload is zstd-compressed (the oracle never sets it today)

STREAMS = {MsgType.STATE: "state", MsgType.TERRAIN: "terrain", MsgType.PROGRESS: "progress"}


def data_name(stream: str) -> str:
    return f"{stream}.msgpack.zst"


def index_name(stream: str) -> str:
    return f"{stream}.index.jsonl"


# ---- wire frames ---------------------------------------------------------------------------------------

def parse_frame(raw: bytes | memoryview) -> tuple[int, int, int, int, memoryview]:
    """(msg_type, schema, flags, seq, payload) of one complete wire frame; raises ValueError on a bad length."""
    length, msg_type, schema, flags, seq = HEADER.unpack_from(raw, 0)
    if length < HEADER.size - 4 or length > MAX_MESSAGE or length + 4 != len(raw):
        raise ValueError(f"bad frame length {length} for {len(raw)} bytes")
    return msg_type, schema, flags, seq, memoryview(raw)[HEADER.size:]


def payload_bytes(payload: bytes | memoryview, flags: int) -> bytes:
    """The msgpack bytes of a payload, undoing the optional zstd flag."""
    if flags & FLAG_ZSTD:
        return zstandard.ZstdDecompressor().decompress(bytes(payload), max_output_size=MAX_MESSAGE)
    return bytes(payload)


def decode(payload: bytes | memoryview, flags: int = 0) -> Any:
    return msgpack.unpackb(payload_bytes(payload, flags), raw=False, strict_map_key=False)


def peek(payload: bytes | memoryview, keys: Iterable[str], flags: int = 0) -> dict:
    """Decode only the given top-level keys of a msgpack map, skipping everything else (the STATE base fields
    come first, so f/drop/ev are found long before the large exporter sections). Returns {} for a non-map."""
    wanted = set(keys)
    out: dict = {}
    u = msgpack.Unpacker(raw=False, strict_map_key=False, max_buffer_size=MAX_MESSAGE)
    u.feed(payload_bytes(payload, flags))
    try:
        n = u.read_map_header()
    except (msgpack.UnpackException, ValueError):
        return out
    for _ in range(n):
        k = u.unpack()
        if k in wanted:
            out[k] = u.unpack()
            if len(out) == len(wanted):
                break
        else:
            u.skip()
    return out


# ---- records -------------------------------------------------------------------------------------------

def pack_record(recv_ns: int, raw: bytes) -> bytes:
    return RECV.pack(recv_ns) + raw


def iter_records(buf: bytes | memoryview) -> Iterator[tuple[int, memoryview]]:
    """(recv_ns, wire frame) for every record of a decompressed chunk."""
    mv = memoryview(buf)
    pos, end = 0, len(mv)
    while pos < end:
        if pos + RECORD_PREFIX + 4 > end:
            raise ValueError(f"truncated record at {pos}")
        (recv_ns,) = RECV.unpack_from(mv, pos)
        length = int.from_bytes(mv[pos + RECORD_PREFIX:pos + RECORD_PREFIX + 4], "little")
        stop = pos + RECORD_PREFIX + 4 + length
        if stop > end:
            raise ValueError(f"truncated frame at {pos}")
        yield recv_ns, mv[pos + RECORD_PREFIX:stop]
        pos = stop


# ---- zstd chunks ---------------------------------------------------------------------------------------

def compressor(level: int = 3) -> zstandard.ZstdCompressor:
    # Content size + checksum in every frame: each chunk decompresses (and verifies) on its own.
    return zstandard.ZstdCompressor(level=level, write_checksum=True, write_content_size=True)


def decompress_chunk(data: bytes) -> bytes:
    return zstandard.ZstdDecompressor().decompress(data, max_output_size=1 << 31)


def scan_frames(data: bytes) -> Iterator[tuple[int, int, bytes]]:
    """(offset, compressed length, decompressed bytes) of every zstd frame in a file; used to rebuild a lost index.
    A truncated last frame (recorder killed mid-write) ends the scan."""
    dctx = zstandard.ZstdDecompressor()
    pos = 0
    while pos < len(data):
        obj = dctx.decompressobj()
        try:
            out = obj.decompress(data[pos:])
        except zstandard.ZstdError:
            return
        if not obj.eof:
            return
        clen = len(data) - pos - len(obj.unused_data)
        yield pos, clen, out
        pos += clen


# ---- JSON for events / meta ----------------------------------------------------------------------------

def _json_default(o: Any) -> Any:
    if isinstance(o, (bytes, bytearray, memoryview)):
        return {"$bin": base64.b64encode(bytes(o)).decode("ascii")}
    if isinstance(o, msgpack.ExtType):
        return {"$ext": o.code, "$bin": base64.b64encode(o.data).decode("ascii")}
    if isinstance(o, (set, frozenset, tuple)):
        return list(o)
    return str(o)


def _json_safe_keys(o: Any) -> Any:
    """msgpack maps may have non-string keys; JSON objects may not."""
    if isinstance(o, dict):
        return {(k if isinstance(k, str) else str(k)): _json_safe_keys(v) for k, v in o.items()}
    if isinstance(o, list):
        return [_json_safe_keys(v) for v in o]
    return o


def to_json(o: Any, **kw) -> str:
    return json.dumps(_json_safe_keys(o), default=_json_default, ensure_ascii=False, **kw)

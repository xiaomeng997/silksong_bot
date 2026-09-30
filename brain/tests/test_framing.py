"""IPC v1 framing against the documented byte layout (DESIGN §4.6, oracle/src/Ipc/Protocol.cs)."""
import struct
import time

import msgpack
import pytest
import zstandard

from ssbot.ipc import framing
from ssbot.ipc.framing import BUTTONS, HEADER, MsgType, encode, mask, names
from ssbot.ipc.oracle_link import OracleLink
from ssbot.record import formats
from tests.fake_oracle import FakeOracle


def csharp_write_prefix(payload_len: int, msg_type: int, seq: int, flags: int = 0) -> bytes:
    """Byte-for-byte port of Protocol.WritePrefix."""
    length = 8 + payload_len
    return bytes([length & 0xFF, (length >> 8) & 0xFF, (length >> 16) & 0xFF, (length >> 24) & 0xFF,
                  msg_type, 1, flags & 0xFF, (flags >> 8) & 0xFF,
                  seq & 0xFF, (seq >> 8) & 0xFF, (seq >> 16) & 0xFF, (seq >> 24) & 0xFF])


def test_header_is_12_bytes_little_endian():
    assert HEADER.size == 12
    assert HEADER.format == "<IBBHI"


@pytest.mark.parametrize("msg_type", list(MsgType))
@pytest.mark.parametrize("seq,flags,n", [(0, 0, 0), (1, 1, 5), (0x01020304, 0x0102, 300), (0xFFFFFFFF, 0, 70000)])
def test_encode_matches_oracle_prefix(msg_type, seq, flags, n):
    payload = bytes(range(256)) * (n // 256) + bytes(n % 256)
    raw = encode(msg_type, seq, payload, flags)
    assert raw[:12] == csharp_write_prefix(n, msg_type, seq, flags)
    assert raw[12:] == payload
    assert int.from_bytes(raw[:4], "little") == len(raw) - 4


def test_seq_wraps_to_u32():
    raw = encode(MsgType.STATE, 2**32 + 5, b"")
    assert struct.unpack_from("<I", raw, 8)[0] == 5


def test_parse_frame_roundtrip_and_rejects_bad_length():
    payload = msgpack.packb({"f": 7, "ev": []})
    raw = encode(MsgType.STATE, 42, payload, flags=0)
    t, schema, flags, seq, body = formats.parse_frame(raw)
    assert (t, schema, flags, seq, bytes(body)) == (MsgType.STATE, 1, 0, 42, payload)
    with pytest.raises(ValueError):
        formats.parse_frame(raw[:-1])
    bad = struct.pack("<I", 3) + raw[4:]
    with pytest.raises(ValueError):
        formats.parse_frame(bad)


def test_zstd_flag_payload_is_decoded():
    state = {"f": 3, "x": [1.5] * 50}
    comp = zstandard.ZstdCompressor().compress(msgpack.packb(state))
    raw = encode(MsgType.STATE, 1, comp, flags=formats.FLAG_ZSTD)
    _, _, flags, _, body = formats.parse_frame(raw)
    assert formats.decode(body, flags) == state
    assert formats.peek(body, ("f",), flags) == {"f": 3}


def test_button_mask_bits_follow_table():
    assert len(BUTTONS) == len(set(BUTTONS)) == 22
    for i, b in enumerate(BUTTONS):
        assert mask(b) == 1 << i
    assert names(mask("jump", "right", "pause")) == ["jump", "pause", "right"]
    assert framing.port(0) == 47017 and framing.port(3) == 47020


def test_record_layout_roundtrip():
    frames = [encode(MsgType.STATE, i, msgpack.packb({"f": i})) for i in range(5)]
    blob = b"".join(formats.pack_record(1000 + i, fr) for i, fr in enumerate(frames))
    got = list(formats.iter_records(blob))
    assert [r for r, _ in got] == [1000, 1001, 1002, 1003, 1004]
    assert [bytes(fr) for _, fr in got] == frames
    assert blob[:8] == (1000).to_bytes(8, "little") and blob[8:20] == frames[0][:12]
    with pytest.raises(ValueError):
        list(formats.iter_records(blob[:-3]))


def test_peek_decodes_only_requested_keys():
    payload = msgpack.packb({"f": 9, "big": list(range(1000)), "drop": 2, "ev": [{"k": "A"}], "tail": 1})
    assert formats.peek(payload, ("f", "ev")) == {"f": 9, "ev": [{"k": "A"}]}
    assert formats.peek(payload, ("missing",)) == {}
    assert formats.peek(msgpack.packb([1, 2]), ("f",)) == {}


def test_oracle_link_receives_exact_frames_over_tcp():
    fo = FakeOracle()
    try:
        link = OracleLink(instance=fo.instance, connect_timeout_s=5)
        got = []
        link.subscribe_raw(lambda t, raw: got.append((t, raw)))
        fo.go.set()
        fo.stream(range(10, 40))
        deadline = time.monotonic() + 5
        while len(got) < 30 and time.monotonic() < deadline:
            time.sleep(0.01)
        assert [raw for _, raw in got] == fo.sent
        assert link.wait_state(lambda s: s["f"] == 39, timeout_s=5)["f"] == 39
        assert link.rpc("ping") == "pong"
        link.close()
    finally:
        fo.close()

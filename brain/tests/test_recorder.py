"""Recorder chunk/index round trip with synthetic STATE dicts, continuity accounting, crash recovery."""
import io
import json
import threading
import time
from datetime import datetime

import msgpack
import pytest
import zstandard

from ssbot.ipc.framing import MsgType
from ssbot.ipc.oracle_link import OracleLink
from ssbot.record import formats
from ssbot.record import synthetic as syn
from ssbot.record.recorder import Recorder, RecordingReader
from tests.fake_oracle import FakeOracle

WHEN = datetime(2026, 9, 30, 12, 0, 0)


def record(tmp_path, frames, *, episode="ep", queue_size=100_000, chunk_frames=600, **stream_kw):
    rec = Recorder(None, out_dir=tmp_path, profile="TEST", episode=episode, hello=syn.hello("3"), when=WHEN,
                   min_free_gb=0, queue_size=queue_size, chunk_frames=chunk_frames, config={"k": 1}).start()
    for t, raw in syn.stream(frames, **stream_kw):
        rec.on_raw(t, raw)
    summary = rec.close()
    return rec, summary


def roundtrip(d):
    return msgpack.unpackb(msgpack.packb(d), raw=False, strict_map_key=False)


def test_layout_and_meta(tmp_path):
    rec, summary = record(tmp_path, range(100, 1600))
    assert rec.path == tmp_path / "2026-09-30" / "TEST" / "ep"
    names = {p.name for p in rec.path.iterdir()}
    assert {"meta.json", "events.jsonl", "state.msgpack.zst", "state.index.jsonl", "terrain.msgpack.zst",
            "terrain.index.jsonl", "progress.msgpack.zst", "progress.index.jsonl"} <= names
    meta = json.loads((rec.path / "meta.json").read_text("utf-8"))
    assert meta["status"] == "closed" and meta["instance"] == "3" and meta["hello"]["qpc_freq"] == syn.QPC_FREQ
    assert meta["config"] == {"k": 1}
    assert meta["versions_lock"]["sha256"] and "[game]" in meta["versions_lock"]["text"]
    assert meta["versions_lock"]["game"]["tree_sha256"]
    assert meta["git"] is None or len(meta["git"]["sha"] or "0" * 40) == 40
    assert meta["qpc"]["start"] <= meta["qpc"]["end"] and meta["qpc"]["freq"] > 0
    assert meta["wall"]["start"] and meta["wall"]["end"]
    assert meta["streams"]["state"]["records"] == 1500 and meta["continuity"]["ok"]
    assert summary["drops"]["queue"]["state"] == 0


def test_chunks_are_independent_and_indexed(tmp_path):
    rec, _ = record(tmp_path, range(100, 1600))
    rd = RecordingReader(rec.path)
    idx = rd.index("state")
    assert [e["n"] for e in idx] == [600, 600, 300]
    assert [(e["f0"], e["f1"]) for e in idx] == [(100, 699), (700, 1299), (1300, 1599)]
    blob = (rec.path / "state.msgpack.zst").read_bytes()
    assert idx[-1]["off"] + idx[-1]["clen"] == len(blob)
    # Each chunk decompresses on its own from its offset, and holds exactly its frame range.
    for e in idx:
        raw = zstandard.ZstdDecompressor().decompress(blob[e["off"]:e["off"] + e["clen"]])
        assert len(raw) == e["ulen"]
        fs = [formats.peek(formats.parse_frame(fr)[4], ("f",))["f"] for _, fr in formats.iter_records(raw)]
        assert fs == list(range(e["f0"], e["f1"] + 1))
    # The whole file is also one valid multi-frame zstd stream.
    whole = zstandard.ZstdDecompressor().stream_reader(io.BytesIO(blob), read_across_frames=True).read()
    assert sum(1 for _ in formats.iter_records(whole)) == 1500


def test_states_roundtrip_and_seek(tmp_path):
    rec, _ = record(tmp_path, range(100, 1600), skip={650})
    rd = RecordingReader(rec.path)
    states = list(rd.states())
    assert [s["f"] for s in states] == [f for f in range(100, 1600) if f != 650]
    assert states[0] == roundtrip(syn.state(100))
    assert [s["f"] for s in rd.states(595, 605)] == [595, 596, 597, 598, 599, 600, 601, 602, 603, 604, 605]
    assert [s["f"] for s in rd.states(1297, 1302)] == [1297, 1298, 1299, 1300, 1301, 1302]  # across a chunk border
    assert [s["f"] for s in rd.states(648, 652)] == [648, 649, 651, 652]
    assert rd.state(650) is None and rd.state(99) is None and rd.state(1599)["f"] == 1599
    assert rd.state(1234) == roundtrip(syn.state(1234))
    assert list(rd.states(1598, keys=("drop",))) == [{"f": 1598, "drop": 0}, {"f": 1599, "drop": 0}]
    assert rd.chunks_for(1000, 1000) == [rd.index("state")[1]]  # chunk 1 = 701..1300 (650 missing)


def test_continuity_counts_gaps_and_oracle_drops(tmp_path):
    rec, _ = record(tmp_path, range(0, 3000), skip={500, 501, 502, 1300}, drop_at={900: 3})
    rep = RecordingReader(rec.path).check()
    assert (rep.f_first, rep.f_last, rep.expected, rep.states) == (0, 2999, 3000, 2996)
    assert rep.gaps == [[499, 503], [1299, 1301]] and rep.missing == 4
    assert rep.oracle_drops == 3 and rep.recorder_drops == 0 and rep.unexplained == 1
    assert rep.delivery == pytest.approx(2996 / 3000) and not rep.ok  # 99.87 % < 99.9 %
    deep = RecordingReader(rec.path).check(deep=True)
    assert deep.index_consistent and deep.gaps == rep.gaps and deep.delivery == rep.delivery
    assert deep.cost_us["p50"] is not None and deep.duration_s == pytest.approx(2999 / 60, rel=1e-3)


def test_continuity_passes_at_threshold(tmp_path):
    rec, _ = record(tmp_path, range(0, 2000), skip={1000})
    rep = RecordingReader(rec.path).check()
    assert rep.missing == 1 and rep.delivery == pytest.approx(0.9995) and rep.ok


def test_events_jsonl(tmp_path):
    rec, summary = record(tmp_path, range(0, 1000), event_every=100)
    evs = list(RecordingReader(rec.path).events())
    assert summary["events"] == len(evs) == 10
    assert evs[1] == {"frame": 100, "kind": "TEST", "data": {"i": 100, "b": {"$bin": "AAE="}}, "state_frame": 100,
                      "q": 0}
    assert list(RecordingReader(rec.path).events({"OTHER"})) == []


def test_terrain_and_progress_one_chunk_per_message(tmp_path):
    rec = Recorder(None, out_dir=tmp_path, profile="T", episode="e", hello=syn.hello(), when=WHEN, min_free_gb=0).start()
    for t, raw in syn.stream(range(0, 700), terrain_at=(0, 650)):
        rec.on_raw(t, raw)
    rec.on_raw(MsgType.PROGRESS, syn.wire(MsgType.PROGRESS, 999, syn.progress()))
    rec.close()
    rd = RecordingReader(rec.path)
    ter = list(rd.terrain())
    assert [e["after_f"] for e, _ in ter] == [None, 649]
    assert ter[1][1] == roundtrip(syn.terrain()) and ter[1][0]["scene"] == "Tut_01"
    prog = list(rd.progress())
    assert len(prog) == 1 and prog[0][1] == roundtrip(syn.progress()) and prog[0][0]["after_f"] == 699
    assert [e["i"] for e in rd.index("terrain")] == [0, 1]


def test_full_queue_drops_and_never_blocks(tmp_path):
    rec = Recorder(None, out_dir=tmp_path, profile="T", episode="e", hello=syn.hello(), when=WHEN, min_free_gb=0,
                   queue_size=5).start()
    gate = threading.Event()
    real = rec._handle

    def slow(*a):
        gate.wait(10)
        real(*a)

    rec._handle = slow
    t0 = time.perf_counter()
    for t, raw in syn.stream(range(0, 50)):
        rec.on_raw(t, raw)
    assert time.perf_counter() - t0 < 0.5  # the reader thread never waits for the writer
    assert 50 - 6 <= rec.dropped["state"] <= 50 - 5
    gate.set()
    summary = rec.close()
    kept = summary["streams"]["state"]["records"]
    assert kept + summary["drops"]["queue"]["state"] == 50
    rep = RecordingReader(rec.path).check()
    assert rep.recorder_drops == rec.dropped["state"] and not rep.ok
    assert rep.delivery == pytest.approx(kept / (kept + rep.recorder_drops))  # tail drops count as lost


def test_index_rebuilt_when_missing_or_torn(tmp_path):
    rec, _ = record(tmp_path, range(0, 1500), skip={10}, terrain_at=(700,))
    good = RecordingReader(rec.path).check()
    (rec.path / "state.index.jsonl").unlink()
    (rec.path / "terrain.index.jsonl").unlink()
    rd = RecordingReader(rec.path)
    assert rd.rebuilt == {"state": True, "terrain": True}
    assert rd.check().gaps == good.gaps and rd.check().states == good.states
    assert [s["f"] for s in rd.states(598, 602)] == [598, 599, 600, 601, 602]
    assert 600 <= rd.index("terrain")[0]["after_f"] <= 1200  # chunk-resolution anchor (true value 699)
    # Recorder killed mid-write: the torn last chunk is ignored, the rest still reads.
    data = rec.path / "state.msgpack.zst"
    blob = data.read_bytes()
    data.write_bytes(blob[:-100])
    rd = RecordingReader(rec.path)
    assert [e["n"] for e in rd.index("state")] == [600, 600]


def test_refuses_to_start_on_low_disk(tmp_path):
    rec = Recorder(None, out_dir=tmp_path, profile="T", episode="e", hello=syn.hello(), min_free_gb=1e9)
    with pytest.raises(RuntimeError):
        rec.start()


def test_existing_episode_is_not_overwritten(tmp_path):
    record(tmp_path, range(0, 10))
    with pytest.raises(FileExistsError):
        record(tmp_path, range(0, 10))


def test_record_from_oracle_link_over_tcp(tmp_path):
    fo = FakeOracle(terrain_at=(40,))
    try:
        link = OracleLink(instance=fo.instance, connect_timeout_s=5)
        rec = Recorder(link, out_dir=tmp_path, profile="T", episode="tcp", when=WHEN, min_free_gb=0).start()
        fo.go.set()
        fo.stream(range(0, 1300))
        link.wait_state(lambda s: s["f"] == 1299, timeout_s=10)
        time.sleep(0.2)
        rec.close()
        link.close()
    finally:
        fo.close()
    rd = RecordingReader(rec.path)
    rep = rd.check(deep=True)
    assert rep.ok and rep.states == 1300 and rep.index_consistent and rd.meta["instance"] == str(fo.instance)
    raw = b"".join(bytes(fr) for _, fr in formats.iter_records(b"".join(
        rd._chunk("state", e) for e in rd.index("state"))))
    assert raw == b"".join(r for r in fo.sent if r[4] == MsgType.STATE)  # wire frames stored byte for byte
    assert len(list(rd.terrain())) == 1


@pytest.mark.parametrize("piece", [1, 7, 4096, 1 << 20])
def test_scan_frames_streams_in_bounded_pieces(piece):
    cctx = formats.compressor()
    frames = [cctx.compress(bytes([i]) * (100 + 997 * i)) for i in range(12)]
    blob = b"".join(frames)
    offs = [sum(map(len, frames[:i])) for i in range(len(frames))]
    got = list(formats.scan_frames(io.BytesIO(blob), piece))
    assert [(o, c) for o, c, _ in got] == [(o, len(f)) for o, f in zip(offs, frames)]
    assert [raw for _, _, raw in got] == [bytes([i]) * (100 + 997 * i) for i in range(12)]
    assert len(list(formats.scan_frames(blob[:-3], piece))) == 11  # torn last frame ends the scan
    assert list(formats.scan_frames(b"", piece)) == []


def _cli_record(tmp_path, skip=frozenset()):
    from ssbot.record.recorder import main
    fo = FakeOracle(skip=skip)

    def feed():
        if fo.brain_hello.wait(10):
            time.sleep(0.3)  # let the recorder subscribe
            fo.go.set()
            fo.stream(range(0, 1300))

    t = threading.Thread(target=feed, daemon=True)
    t.start()
    try:
        return main(["record", "--instance", str(fo.instance), "--seconds", "1.5", "--out", str(tmp_path),
                     "--episode", "cli", "--game-dir", str(tmp_path / "nogame"), "--min-free-gb", "0"])
    finally:
        fo.close()
        t.join(5)


def test_record_cli_exit_code_gates_delivery(tmp_path, capsys):
    assert _cli_record(tmp_path / "a") == 0
    assert "PASS" in capsys.readouterr().out
    assert _cli_record(tmp_path / "b", skip=set(range(500, 510))) == 1  # 10 of 1300 missing: 99.23 %
    assert "FAIL" in capsys.readouterr().out


def test_record_cli_closes_the_recording_when_the_video_fails(tmp_path, monkeypatch):
    from ssbot.ipc import oracle_link
    from ssbot.record import video
    from ssbot.record.recorder import main
    closed = []

    class Link(OracleLink):
        def close(self):
            closed.append(True)
            super().close()

    def boom(self):
        raise OSError("capture failed")

    monkeypatch.setattr(oracle_link, "OracleLink", Link)
    monkeypatch.setattr(video, "instance_window", lambda instance: 0x1234)
    monkeypatch.setattr(video.VideoRecorder, "_start_capture", boom)
    fo = FakeOracle()
    try:
        with pytest.raises(OSError, match="capture failed"):
            main(["record", "--instance", str(fo.instance), "--seconds", "30", "--out", str(tmp_path), "--episode",
                  "v", "--game-dir", str(tmp_path / "nogame"), "--min-free-gb", "0", "--video"])
    finally:
        fo.close()
    ep = next(tmp_path.glob("*/TRAIN/v"))
    assert json.loads((ep / "meta.json").read_text("utf-8"))["status"] == "closed" and closed
    assert json.loads((ep / "video.json").read_text("utf-8"))["status"] == "failed"

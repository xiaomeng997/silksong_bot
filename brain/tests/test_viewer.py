"""Viewer: builds a Rerun recording (to an .rrd file, no viewer spawned) and degrades on missing sections."""
from datetime import datetime

import pytest
import rerun as rr

from ssbot.ipc.framing import MsgType
from ssbot.record import synthetic as syn
from ssbot.record.recorder import Recorder, RecordingReader
from ssbot.tools import viewer as V


def make(tmp_path, name, messages):
    rec = Recorder(None, out_dir=tmp_path, profile="T", episode=name, hello=syn.hello(), min_free_gb=0,
                   when=datetime(2026, 9, 30)).start()
    for t, raw in messages:
        rec.on_raw(t, raw)
    rec.close()
    return RecordingReader(rec.path)


def stream_for(tmp_path, name):
    s = rr.RecordingStream("ssbot-viewer-test")
    s.save(tmp_path / f"{name}.rrd", default_blueprint=V.blueprint())
    return s


def test_full_recording(tmp_path):
    rd = make(tmp_path, "full", syn.stream(range(0, 900), terrain_at=(0, 500), event_every=100))
    stats = V.build(rd, stream_for(tmp_path, "full"))
    assert stats["frames"] == 900 and stats["hero_frames"] == 900 and stats["ent_frames"] == 900
    assert stats["terrain_msgs"] == 2 and stats["terrain_layers"] == 4 and stats["events"] == 9
    assert stats["trail_segments"] == 1 and stats["series"] >= 10


def test_range_and_stride(tmp_path):
    rd = make(tmp_path, "r", syn.stream(range(0, 900), event_every=100))
    stats = V.build(rd, stream_for(tmp_path, "r"), f0=200, f1=399, ents_stride=10)
    assert stats["frames"] == 200 and stats["ent_frames"] == 20 and stats["events"] == 2


def test_missing_and_nil_sections(tmp_path):
    msgs = []
    for f in range(0, 300):
        s = syn.state(f, hero=False, ents=False)
        if f > 100:
            s["game"] = None
            s["pause"] = None
        s["ents"] = None if f % 2 else {"list": []}
        msgs.append((MsgType.STATE, syn.wire(MsgType.STATE, f + 1, s)))
    msgs.append((MsgType.TERRAIN, syn.wire(MsgType.TERRAIN, 999, {"scene": "X", "weird": [1, 2, 3], "n": None})))
    rd = make(tmp_path, "bare", msgs)
    stats = V.build(rd, stream_for(tmp_path, "bare"))
    assert stats["frames"] == 300 and "hero_frames" not in stats and "ent_frames" not in stats
    assert stats["terrain_msgs"] == 1 and "terrain_layers" not in stats


def test_main_saves_rrd(tmp_path, capsys):
    rd = make(tmp_path, "cli", syn.stream(range(0, 120)))
    out = tmp_path / "cli.rrd"
    assert V.main([str(rd.path), "--save", str(out), "--series", "fixed=fdt"]) == 0
    assert out.stat().st_size > 0 and "series" in capsys.readouterr().out


@pytest.mark.parametrize("value,expected", [
    ([[0, 0], [1, 0], [1, 1]], [(0, 0), (1, 0), (1, 1)]),
    ([0, 0, 1, 0, 1, 1], [(0, 0), (1, 0), (1, 1)]),
    ({"verts": [{"x": 0, "y": 0}, {"x": 2, "y": 0}]}, [(0, 0), (2, 0)]),
    ({"aabb": [0, 0, 2, 1]}, [(0, 0), (2, 0), (2, 1), (0, 1)]),
    ({"min": [0, 0], "max": [2, 1]}, [(0, 0), (2, 0), (2, 1), (0, 1)]),
    ([1, 2, 3], None), ("x", None), ([[0, 0]], None), ({"verts": None}, None),
])
def test_polygon_shapes(value, expected):
    assert V.polygon(value) == expected


def test_circle_and_entity_shapes():
    assert len(V.polygon({"center": [0, 0], "radius": 1})) == 16
    assert V.entities({"ents": {"items": [{"a": 1}, 3]}}) == [{"a": 1}]
    assert V.entities({"ents": {"7": {"pos": [0, 0]}}}) == [{"pos": [0, 0]}]
    assert V.entities({"ents": None}) == []
    polys = list(V.colliders({"colliders": [{"verts": [[0, 0], [1, 1]]}, {"bad": 1}]}))
    assert len(polys) == 1
    assert V.polygons_by_key({"solids": [[[0, 0], [1, 0], [1, 1]]], "geo": {"walls": [[0, 0, 0, 1]]}}) == {
        "solids": [[(0, 0), (1, 0), (1, 1)]], "geo/walls": [[(0, 0), (0, 1)]]}

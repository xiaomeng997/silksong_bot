"""Offline checks of the TERRAIN / PROGRESS / event decoders against payloads shaped like the oracle's."""
import msgpack
import numpy as np

from ssbot.ipc.framing import MsgType, encode
from ssbot.oracle.messages import (BREAKABLE, NON_SLIDER, EventLog, ProgressMirror, Terrain, split_frame, unpack,
                                   verts)


def _bin(points):
    return np.asarray(points, dtype="<f4").reshape(-1).tobytes()


def _terrain_payload():
    return {
        "seq": 3, "reason": "enter", "frame": 1200, "transition": 2, "scene_raw": "Bone_05", "scene": "Bone_05",
        "scenes": ["Bone_05"], "loaded": ["Bone_05"],
        "cam": {"scene_w": 80.0, "scene_h": 40.0, "x_limit": 65.4, "y_limit": 31.7},
        "sm": {"map_zone": "BONETOWN", "hero_keep_health": False},
        "cutscene": False,
        "solids": [
            {"id": -100, "go": "Chunk 0 0", "layer": 8, "on": True, "body": 0, "flags": NON_SLIDER,
             "shapes": [{"k": "poly", "v": _bin([[0, 0], [10, 0], [10, 2], [0, 2]])}]},
            {"id": -101, "go": "Battle Gate", "layer": 8, "on": False, "body": 0, "flags": BREAKABLE,
             "shapes": [{"k": "edge", "v": _bin([[20, 0], [20, 8]]), "r": 0.1}]},
        ],
        "hazards": [
            {"id": -200, "go": "Spikes", "on": True, "hazard": "SPIKES", "damage": 1, "flags": 0, "tink": True,
             "trigger": True, "body": 0, "shapes": [{"k": "box", "v": _bin([[3, 2], [5, 2], [5, 2.5], [3, 2.5]])}]},
        ],
        "gates": [{"go": "left1", "on": True, "pos": [0.5, 3.0], "target": "Bone_04", "entry": "right1",
                   "side": "left", "door": False, "shapes": [{"k": "box", "v": _bin([[0, 2], [1, 2], [1, 5], [0, 5]])}],
                   "aabb": [0, 2, 1, 5]}],
        "preloaders": [{"go": "Preloader", "on": True, "pos": [12.0, 4.0], "loads": "Bone_06", "started": False,
                        "has_trigger": True, "trigger_on": True, "test_ok": True, "gate_white": [],
                        "gate_black": ["left1"], "shapes": [{"k": "box", "v": _bin([[11, 3], [13, 3], [13, 5], [11, 5]])}],
                        "aabb": [11, 3, 13, 5]}],
        "harpoon": [{"go": "Harpoon Ring", "id": -300, "kind": "ring", "on": True, "trigger": True, "body": 0,
                     "pos": [30.0, 12.0], "shapes": [{"k": "circle", "v": _bin([[30, 12]]), "r": 0.6}],
                     "aabb": [29.4, 11.4, 30.6, 12.6]}],
        "layers": {"terrain": 8, "soft_terrain": 25},
        "stats": {"colliders_seen": 40, "verts": 12, "slices": 1, "frames": 1, "work_ms": 0.3, "ms": 0.3},
    }


def test_frame_split_roundtrip():
    payload = msgpack.packb(_terrain_payload())
    msg_type, seq, body = split_frame(encode(MsgType.TERRAIN, 77, payload))
    assert msg_type == MsgType.TERRAIN and seq == 77
    assert unpack(body)["scene_raw"] == "Bone_05"


def test_terrain_decode():
    t = Terrain.decode(unpack(msgpack.packb(_terrain_payload())))
    assert t.seq == 3 and t.scene_raw == "Bone_05"
    assert len(t.solids) == 2 and t.solids[0].has(NON_SLIDER) and not t.solids[1].on
    poly = t.solids[0].shapes[0]
    assert poly.closed and poly.verts.shape == (4, 2) and poly.verts.dtype == np.float32
    edge = t.solids[1].shapes[0]
    assert not edge.closed and abs(edge.radius - 0.1) < 1e-6
    assert t.hazards[0].hazard == "SPIKES" and t.hazards[0].tink
    assert t.zones["gates"][0]["target"] == "Bone_04"
    assert t.zones["gates"][0]["shapes"][0].verts[2].tolist() == [1.0, 5.0]
    assert t.zones["respawns"] == []
    ring = t.zones["harpoon"][0]
    assert ring["kind"] == "ring" and ring["shapes"][0].verts.tolist() == [[30.0, 12.0]]
    assert abs(ring["shapes"][0].radius - 0.6) < 1e-6 and not ring["shapes"][0].closed
    pre = t.zones["preloaders"][0]
    assert pre["loads"] == "Bone_06" and pre["gate_black"] == ["left1"] and pre["shapes"][0].closed
    assert t.bounds() == (0.0, 0.0, 20.0, 8.0)
    assert t.bounds(active_only=True) == (0.0, 0.0, 10.0, 2.0)
    s = t.summary()
    assert s["solids"] == 2 and s["solids_on"] == 1 and s["verts"] == 6 and s["gates"] == 1


def test_verts_layout_matches_oracle():
    # The oracle Buffer.BlockCopy's a float[] {x0, y0, x1, y1} on little-endian x86.
    raw = np.array([1.5, -2.0, 3.25, 4.0], dtype="<f4").tobytes()
    assert verts(raw).tolist() == [[1.5, -2.0], [3.25, 4.0]]


def test_progress_mirror():
    m = ProgressMirror()
    diff = {"seq": 1, "frame": 5, "full": False, "reason": "diff", "scene": "Tut_01", "t_live": 1.0,
            "changed": {"geo": 10}}
    m.apply(diff)
    assert not m.synced and m.fields == {"geo": 10}
    full = {"seq": 2, "frame": 6, "full": True, "reason": "connect", "scene": "Tut_01", "t_live": 1.1,
            "changed": {"geo": 12, "health": 5, "permadeathMode": "On", "CurrentCrestID": "Hunter"},
            "crest": {"current": "Hunter", "previous": None},
            "tools": {"Straight Pin": {"unlocked": True, "amount": 3}}, "tool_equips": {}, "extra_equips": {},
            "equipped": ["Straight Pin"], "fields": 4}
    m.apply(full)
    assert m.synced and m.fields["geo"] == 12 and m.tools["Straight Pin"]["amount"] == 3
    changed = m.apply({"seq": 3, "frame": 40, "full": False, "reason": "diff", "scene": "Tut_01", "t_live": 1.6,
                       "changed": {"health": 4}})
    assert changed == {"health": 4} and m.fields["health"] == 4 and m.fields["geo"] == 12 and m.seq == 3


def test_event_log_counts_lost_events():
    log = EventLog()
    log.add_state({"f": 10, "ev": [{"k": "gs", "f": 10, "q": 1, "d": {"n": 1, "from": "PLAYING", "to": "PAUSED"}}]})
    log.add_state({"f": 12, "ev": [{"k": "hp", "f": 12, "q": 2, "d": {"n": 4, "delta": -1}},
                                   {"k": "freeze", "f": 12, "q": 3, "d": {"n": 5, "phase": "start"}}]})
    assert log.lost == 2
    assert [e["k"] for e in log.of("hp", "freeze")] == ["hp", "freeze"]
    assert log.of("hp")[0]["delta"] == -1
    assert log.of("gs", since_frame=10) == []

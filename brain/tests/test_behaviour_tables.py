"""Behaviour tables (ssbot.knowledge.behaviour_tables) on a scripted synthetic fight and on a real fixture cut from
the trial combat run, plus the build CLI report and the timeline viewer.

Fixture tests/fixtures/bellbeast_trial_windows.msgpack.zst (82 KB): two windows of the trial recording
C:/ssbot/data/runs/m2/20261001_121446_BellBeast_data/rec/2026-10-01/TRAIN/i0_000 (episode 0), frames 45780-46660
(Charge from Set L, Bell Burst, Leap from Set R; phase P1) and 47820-49120 (the Rage pattern Ptn L, then two P2 Bell
Bursts, the second cut by the window), STATEs trimmed to the fields the scanner reads (f, dt, hero pos / box /
health, ents without anim / vel / fsm times, fsm and damage events). Regenerate with
`python tests/test_behaviour_tables.py <recording dir>`.
"""
import json
import sys
from pathlib import Path

import msgpack
import numpy as np
import pytest
import zstandard

from ssbot.knowledge import behaviour_tables as bt
from ssbot.knowledge import hitbox_tables as hb

FIXTURE = Path(__file__).parent / "fixtures" / "bellbeast_trial_windows.msgpack.zst"
FIXTURE_WINDOWS = [(45780, 46660), (47820, 49120)]
DT = 1.0 / 60.0
DMG = {"dealt": 2, "eff": 2, "hazard_type": 1, "flags": 0, "parry": 4, "parryable": False, "can_cause_damage": True}

SPEC = bt.BehaviourSpec(
    enemy="Synth", scene="S", boss_type="Test Boss", control_fsm="Control", hp=100, dormant=("Dormant",),
    death_states=("Dead",), attack_starts={"Antic A": "A", "Antic B": "B"},
    decision_states=("Idle", "Choose", "Set L", "Set R"), dir_states={"Set L": 1, "Set R": -1}, directed=("A",),
    phase_marks={}, phases={"P1": "all"}, initial_phase="P1", world_fixed=("Rock",), arena_x=(0.0, 30.0))


# ---- synthetic fight ---------------------------------------------------------------------------------------

def _box(x0, y0, x1, y1):
    return [x0, y0, x1, y0, x1, y1, x0, y1]


def _col(verts, enabled=True, kind="box"):
    return {"kind": kind, "verts_world": list(verts), "enabled": enabled, "layer": 11, "damage": dict(DMG)}


def _ent(iid, tk, x, y, cols, state=None, src=2, category="hazard", flip=False):
    return {"iid": iid, "type_key": tk, "category": category, "src": src, "pos": [x, y, 0.0], "hp": None,
            "flipX": flip, "fsms": [] if state is None else [{"name": "Control", "state": state}], "colliders": cols}


class Synth:
    """A scripted boss: Idle (underground, 30 frames) -> one-frame chain Choose -> [Set L|R ->] Antic A|B ->
    A: Antic A 20 (hidden), Dash 30 (box 2 x 2 u moving 0.2 u/frame toward the far side), Recover 10;
    B: Antic B 15 (hidden), Throw 10 (arms the world-fixed Rock for 40 frames and a Shard projectile for 25),
    Recover B 10. Always-on Spikes are ambient. One hit per Dash (frame 10), one Rock hit in B's tail."""

    def __init__(self):
        self.f = 1000
        self.out = []
        self.ev = []
        self.ctl = None
        self.entered = None
        self.boss = None
        self.hero = (12.0, 0.0)
        self.rock_left = 0
        self.rock_j = 0
        self.shard_left = 0
        self.shard_x = 0.0

    def to(self, state):
        tip = None if self.ctl is None else (self.f - self.entered) * DT
        self.ev.append({"k": "fsm", "f": self.f, "d": {"iid": 1, "ent": 1, "obj": "Test Boss", "fsm": "Control",
                                                        "from": self.ctl, "to": state, "t_in_prev": tip,
                                                        "rt_in_prev": tip}})
        self.ctl, self.entered = state, self.f

    def hit(self, source):
        self.ev.append({"k": "damage", "f": self.f, "d": {"source": source, "amount": 2, "hazard": "ENEMY"}})

    def frame(self, dt=DT):
        ents = [_ent(70, "Spikes", 30.5, 0.0, [_col(_box(30, 0, 31, 1))])]
        if self.boss is not None:
            ents.append(self.boss)
        if self.rock_left > 0:
            y = 8.0 - 0.1 * self.rock_j
            ents.append(_ent(50, "Rock", 10.0, y, [_col(_box(9.5, y - 0.5, 10.5, y + 0.5))], "Fall"))
            self.rock_left -= 1
            self.rock_j += 1
        else:
            ents.append(_ent(50, "Rock", 10.0, 8.0, [_col(_box(9.5, 7.5, 10.5, 8.5), enabled=False)], "Dormant"))
        if self.shard_left > 0:
            x = self.shard_x
            ents.append(_ent(60, "Shard", x, 1.0, [_col(_box(x - 0.25, 0.75, x + 0.25, 1.25))], "Fly", src=2 | 32))
            self.shard_x += 0.3
            self.shard_left -= 1
        self.out.append({"f": self.f, "dt": dt, "hero": {"pos": [*self.hero, 0.0], "box": [0, 0, 1, 1], "health": 5},
                         "ents": ents, "ev": self.ev})
        self.ev = []
        self.f += 1

    def idle(self, n, freeze_at=None):
        self.boss = None
        for j in range(n):
            self.frame(0.0 if j == freeze_at else DT)

    def attack_a(self, side, die=False):
        m = 1 if side == "Set L" else -1
        x0 = 5.0 if m == 1 else 25.0
        self.idle(20)
        for j in range(30):
            if j == 0:
                self.to("Dash")
            x = x0 + m * 0.2 * j
            self.boss = _ent(1, "Test Boss", x, 1.0, [_col(_box(x - 1, 0, x + 1, 2))], "Dash", src=3,
                             category="enemy", flip=m < 0)
            if die and j == 5:
                self.to("Dead")
                self.hit("Test Boss/Body")  # same frame as the kill, after the transition
                self.idle(10)
                return
            if j == 10:
                self.hit("Test Boss/Body")
            self.frame()
        self.to("Recover")
        for _ in range(10):
            self.boss = _ent(1, "Test Boss", self.boss["pos"][0], 1.0, [_col(_box(0, 0, 1, 1), enabled=False)],
                             "Recover", src=3, category="enemy")
            self.frame()

    def attack_b(self):
        self.idle(15)
        self.to("Throw")
        self.rock_left, self.rock_j = 40, 0
        self.shard_left, self.shard_x = 25, 16.0
        for _ in range(10):
            self.boss = _ent(1, "Test Boss", 15.0, 1.0, [], "Throw", src=3, category="enemy")
            self.frame()
        self.to("Recover B")
        for _ in range(10):
            self.frame()

    def fight(self, plan):
        self.to("Dormant")
        self.idle(5)
        self.to("Idle")
        for k, (fam, side) in enumerate(plan):
            self.hero = ((3.0, 12.0, 20.0, 28.0)[k % 4], 0.0)
            self.idle(30, freeze_at=7 if k == 0 else None)
            self.to("Choose")
            if side:
                self.to(side)
            self.to("Antic A" if fam == "A" else "Antic B")
            if fam == "A":
                self.attack_a(side, die=k == len(plan) - 1)
            else:
                self.attack_b()
            if self.ctl != "Dead":
                self.to("Idle")
                if fam == "B":
                    for j in range(25):  # the Rock is still falling: hit the hero 10 frames into Idle
                        if j == 10:
                            self.hit("Boss Scene/Rock")
                        self.frame()
        return self.out


PLAN = [("A", "Set L"), ("B", None), ("A", "Set R"), ("B", None), ("A", "Set L"), ("A", "Set R"), ("B", None),
        ("A", "Set L")]


@pytest.fixture(scope="module")
def synth():
    b = bt.BehaviourBuilder(SPEC)
    info = b.scan_states(Synth().fight(PLAN), "synth")
    return b, info


def test_synthetic_segmentation(synth):
    b, info = synth
    assert info["died"] and info["instances"] == 8
    fams = [i.family for i in b.instances]
    assert sorted(fams) == ["A"] * 5 + ["B"] * 3
    a = [i for i in b.instances if i.family == "A"]
    assert [i.dir for i in a] == ["Set L", "Set R", "Set L", "Set R", "Set L"]
    assert [i.mirror for i in a] == [1, -1, 1, -1, 1]
    assert [i.anchor[0] for i in a] == [5.0, 25.0, 5.0, 25.0, 5.0]
    assert all(abs(i.anchor_t - 20 * DT) < 1e-9 for i in a)
    assert [i.end for i in a] == ["rest"] * 4 + ["death"]
    assert all(abs(i.t_end - 60 * DT) < 1e-9 for i in a[:4])
    bb = [i for i in b.instances if i.family == "B"]
    assert all(i.mirror == 1 and i.anchor == (15.0, 1.0) and i.dir is None for i in bb)
    assert all(abs(i.t_end - 35 * DT) < 1e-9 for i in bb)
    assert all(abs(i.t_tail - 54 * DT) < 1e-9 for i in bb)  # the Rock (40 frames from 15) outlives the attack
    assert b.counters == {}  # the always-on Spikes are ambient, nothing unattributed


def test_synthetic_graph_dwell_and_decisions(synth):
    b, _ = synth
    t = b.tables()
    g = t["graph"]
    assert g["from"]["Idle"]["successors"] == {"Choose": 8}
    assert g["from"]["Choose"]["successors"] == {"Set L": 3, "Set R": 2, "Antic B": 3}
    p, p_unseen = bt.dirichlet({"Set L": 3, "Set R": 2, "Antic B": 3})
    assert abs(p["Set L"] - 3.5 / 10.0) < 1e-12 and abs(p_unseen - 0.05) < 1e-12
    assert abs(sum(p.values()) + p_unseen - 1.0) < 1e-12
    edge = next(e for e in g["edges"] if e["from"] == "Choose" and e["to"] == "Set L")
    assert edge["p"] == round(3.5 / 10.0, 4) and edge["low_n"]
    assert any(e.get("kill") and e["from"] == "Dash" for e in g["edges"])
    assert g["from"]["Dash"]["successors"] == {"Recover": 4} and g["from"]["Dash"]["worst_case"]
    d = t["dwell_s"]
    assert d["Antic A"]["n"] == 5 and abs(d["Antic A"]["p50"] - 20 * DT) < 1e-4
    assert d["Dash"]["n"] == 4  # the exit into Dead is not a dwell
    assert d["Choose"]["instant"] and not d["Antic A"]["instant"]
    assert d["Antic A"]["max_abs_dwell_minus_state_time"] < 1e-6
    idle = [x.dwell_s for x in b.dwells if x.state == "Idle"]
    assert min(idle) == pytest.approx(29 * DT)  # the frame with dt = 0 (hit-stop) adds no game time
    dec = t["decisions"]["Choose"]
    assert dec["n"] == 8 and sum(sum(v.values()) for v in dec["by_dist_bin"].values()) == 8
    assert set(dec["by_hero_third"]) <= {"W", "C", "E"}
    assert dec["boss_ref"] == {None: 1, "last": 7}  # never seen before the first decision, underground after


def test_synthetic_templates_follow_the_mirrored_dash(synth):
    b, _ = synth
    tpls = b.templates()
    a = tpls["A/anchor"]
    assert a.n_instances == 5
    j = np.arange(30)
    t = 20 * DT + j * DT
    # Set L and Set R dashes coincide in the anchor frame: the box centre runs along +x' at 0.2 u/frame
    assert a.contains(t, 0.2 * j, 0.0).all()
    assert not a.contains(t, 0.2 * j + 3.0, 0.0).any()
    assert not a.contains(t, -0.2 * j - 3.0, 0.0).any()
    assert tpls["A/Dash/anchor"].contains(j * DT, 0.2 * j, 0.5).all()
    rock = tpls["B/world"]
    assert rock.frame == "world"
    k = np.arange(40)
    assert rock.contains(15 * DT + k * DT, 10.0, 8.0 - 0.1 * k).all()
    tail = tpls["B/_tail/world"]  # the Rock after B ended (t from the end): 20 frames of the 40
    assert tail.contains(np.arange(1, 20) * DT, 10.0, 8.0 - 0.1 * (np.arange(1, 20) + 20)).all()
    shard = tpls["B/anchor"]
    assert shard.contains(15 * DT + np.arange(25) * DT, 1.0 + 0.3 * np.arange(25), 0.0).all()
    assert "Spikes" not in json.dumps(b.tables()["attacks"])


def test_synthetic_hits_and_entities(synth):
    b, _ = synth
    t = b.tables()
    assert t["attacks"]["A"]["hits_taken"] == {"n": 5, "by_source": {"Test Boss/Body": 5}, "by_state": {"Dash": 5}}
    assert t["attacks"]["B"]["hits_taken"]["by_state"] == {bt.TAIL: 3}
    rock = t["entities"]["Rock"]
    assert rock["armed"] == 3 and rock["armed_by_family"] == {"B": 3} and rock["armed_at_boss_state"] == {"Throw": 3}
    assert rock["by_state"]["Fall"]["enabled"] == 1.0 and "enabled" not in rock["by_state"]["Dormant"]
    assert rock["world_frame"] and rock["lifetime_s"]["p50"] == pytest.approx(39 * DT, abs=1e-4)
    shard = t["entities"]["Shard"]
    assert shard["end"] == {"left view": 3} and shard["src"] == ["damage_hero", "projectile"]
    hb_rows = {(h["state"], h["source"]): h for h in t["attacks"]["A"]["hitboxes"]}
    dash = hb_rows[("Dash", "Test Boss:box")]
    assert dash["n"] == 5 and dash["t0"] == pytest.approx(20 * DT, abs=1e-4) and dash["dmg"] == [2]
    assert dash["type"] == ["ENEMY"] and dash["parry"] == ["counter"] and not dash["parryable"]
    assert t["attacks"]["A"]["coverage"] == {"n": 5, "target": 200, "ok": False}


def test_synthetic_write_and_report(synth, tmp_path):
    from ssbot.tools.behaviour_build import report
    b, _ = synth
    js, npz, tables = b.write(tmp_path)
    data = json.loads(js.read_text("utf-8"))
    assert data["enemy"] == "Synth" and data["attacks"]["A"]["reach_union"]["anchor"]["extent"][2] > 6.0
    tpls, extra = hb.load_templates(npz)
    assert {"A/anchor", "B/world", "B/anchor", "A/Dash/anchor"} <= set(tpls)
    assert extra["A/instances"].shape == (5, len(bt.INSTANCE_COLUMNS))
    assert list(extra["A/state_names"]) == ["Antic A", "Dash", "Recover"]
    assert np.allclose(extra["A/state_t"][:4, 1], 20 * DT)
    path = extra["A/boss_path"]
    assert np.allclose(path[:, 2], path[:, 3])  # mirrored Set L / Set R paths coincide in the anchor frame
    text = report(tables)
    assert any(line.split()[:2] == ["A", "5"] for line in text.splitlines()) and "195 missing" in text


def test_static_fsm_graph_adds_unlogged_edges():
    choose = {"A": "Set L", "B": "Set R", "C": "Antic B", "D": "Antic C"}
    graph = {"states": [{"name": "Choose", "transitions": choose},
                        {"name": "Antic C", "transitions": {"FINISHED": "Idle"}}],
             "global": {"DEATH": "Dead"}}
    b = bt.BehaviourBuilder(SPEC, fsm_graph=graph)
    b.scan_states(Synth().fight(PLAN), "synth")
    g = b.tables()["graph"]
    row = next(e for e in g["edges"] if e["from"] == "Choose" and e["to"] == "Antic C")
    assert row["n"] == 0 and row["static_only"] and row["p"] == round(0.5 / (8 + 0.5 * 5), 4)
    assert g["global_targets"] == ["Dead"] and "Antic C" in b.tables()["support_transitions"]["Choose"]
    assert "Antic C" in b.tables()["support_transitions"] and g["branching"] == ["Choose"]


def test_per_instance_paths_on_request():
    b = bt.BehaviourBuilder(SPEC, keep_paths=True)
    b.scan_states(Synth().fight(PLAN[:2]), "synth")
    paths = b.extra_arrays()["A/paths"]
    assert paths.shape == (30 + 10, 4) and set(paths[:, 0]) == {0.0}
    assert np.allclose(paths[:30, 2], 0.2 * np.arange(30), atol=1e-5)  # x' of the dash
    assert np.array_equal(b.extra_arrays()["A/state_f"][0, 1:], b.extra_arrays()["A/state_f"][0, :1] + [20, 50])


def test_timeline_and_snapshot_pictures(synth, tmp_path):
    from ssbot.tools import attack_timeline as at
    b, _ = synth
    _, npz, _ = b.write(tmp_path)
    evs = [(ev["f"], ev["k"], ev["d"]) for s in Synth().fight(PLAN) for ev in s["ev"]]
    segs = at.control_segments(evs, SPEC)
    assert [fam for _, st, fam in segs if st == "Dash"] == ["A"] * 5
    img = at.draw_timeline([{"id": "synth", "f0": 1000, "f1": 1000 + 1200, "segments": segs,
                             "hits": [(f, d["source"]) for f, k, d in evs if k == "damage"]}], SPEC)
    assert img.ndim == 3 and img.shape[0] > 50
    out = tmp_path / "snap.png"
    assert at.main(["snapshots", str(npz), "--out", str(out)]) == 0 and out.stat().st_size > 1000


# ---- inputs ------------------------------------------------------------------------------------------------

def test_run_fights_reads_closed_recordings_only(tmp_path):
    run = tmp_path / "20261001_000000_BellBeast_data"
    for name, status in (("i0_000", "closed"), ("i0_001", "recording")):
        d = run / "rec" / "2026-10-01" / "TRAIN" / name
        d.mkdir(parents=True)
        (d / "meta.json").write_text(json.dumps({"status": status}), "utf-8")
    rows = [{"instance": 0, "episode": 0, "f_wake": 10, "f_end": 900, "outcome": "CLEAR",
             "recording": "D:/elsewhere/i0_000"},
            {"instance": 0, "episode": 1, "f_wake": 910, "f_end": 1900, "outcome": "CLEAR",
             "recording": str(run / "rec" / "2026-10-01" / "TRAIN" / "i0_001")},
            {"instance": 0, "episode": 2, "f_wake": None, "f_end": 2000, "outcome": "HARNESS_FAIL",
             "recording": "x"}]
    (run / "attempts_i0.jsonl").write_text("\n".join(json.dumps(r) for r in rows) + "\n{\"torn", "utf-8")
    fights, skipped = bt.run_fights(run)
    assert [(f.f0, f.f1, f.path.name) for f in fights] == [(10, 900, "i0_000")]
    assert fights[0].id.endswith("/i0/ep0") and len(skipped) == 3
    assert len(bt.run_fights(run, closed_only=False)[0]) == 2
    evs = [{"frame": f, "kind": k, "data": {"to": str(f)}, "state_frame": f, "q": 0}
           for f, k in ((5, "fsm"), (10, "fsm"), (500, "damage"), (600, "gs"), (900, "fsm"), (950, "fsm"))]
    (fights[0].path / "events.jsonl").write_text("".join(json.dumps(e) + "\n" for e in evs), "utf-8")
    assert [(f, k) for f, k, _ in bt.fight_events(fights[0])] == [(10, "fsm"), (500, "damage"), (900, "fsm")]


def test_raw_session_states_streams_a_frame_range(tmp_path):
    from ssbot.ipc.framing import MsgType, encode
    msgs = [encode(MsgType.HELLO, 0, msgpack.packb({"role": "oracle"}))]
    msgs += [encode(MsgType.STATE, f, msgpack.packb({"f": f, "dt": DT, "hero": {"pos": [f, 0]}, "big": "x" * 5000}))
             for f in range(100, 400)]
    (tmp_path / "state.raw.zst").write_bytes(zstandard.ZstdCompressor().compress(b"".join(msgs)))
    got = list(bt.raw_session_states(tmp_path, 150, 160, keys=("hero",)))
    assert [s["f"] for s in got] == list(range(150, 161))
    assert set(got[0]) == {"f", "hero"}
    assert len(list(bt.raw_session_states(tmp_path))) == 300


def test_small_statistics():
    q = bt.quantiles([1.0, 2.0, 3.0, None, float("nan")])
    assert q["n"] == 3 and q["p50"] == 2.0 and q["min"] == 1.0 and q["max"] == 3.0
    assert bt.quantiles([]) == {"n": 0}
    edges = (0.0, 3.0, 6.0, 10.0, 99.0)
    assert [bt.dist_bin(d, edges) for d in (0.0, 2.9, 3.0, 9.99, 50.0, 500.0, None)] == [0, 0, 1, 2, 3, 3, None]
    assert bt.collider_key("Boss", {"kind": "poly", "verts_world": [0.0] * 14}) == "Boss:poly7"


# ---- real fixture ------------------------------------------------------------------------------------------

@pytest.fixture(scope="module")
def trial():
    data = msgpack.unpackb(zstandard.ZstdDecompressor().decompress(FIXTURE.read_bytes()), raw=False,
                           strict_map_key=False)
    b = bt.BehaviourBuilder(bt.SPECS["BellBeast"])
    infos = [b.scan_states(states, f"trial/{i}") for i, states in enumerate(data["states"])]
    return b, infos


def test_trial_fixture_instances(trial):
    b, infos = trial
    assert [i["instances"] for i in infos] == [4, 3]
    got = [(i.family, i.phase, i.dir, i.mirror, i.end) for i in b.instances]
    # each window ends a few frames into the next attack (cut: "fight_end"; its anchor is never seen)
    assert sorted(got, key=str) == sorted([
        ("BB_CHARGE", "P1", "Set L", 1, "rest"), ("BB_BURST", "P1", None, 1, "rest"),
        ("BB_LEAP", "P1", "Set R", -1, "rest"), ("BB_LEAP", "P1", "Set L", 1, "fight_end"),
        ("BB_RAGE", "P1", None, 1, "rest"), ("BB_BURST", "P2", None, 1, "rest"),
        ("BB_BURST", "P2", None, 1, "fight_end")], key=str)
    by = {(i.family, i.phase, i.end): i for i in b.instances}
    charge, leap = by[("BB_CHARGE", "P1", "rest")], by[("BB_LEAP", "P1", "rest")]
    assert charge.anchor == pytest.approx((75.03, 5.49), abs=0.01) and charge.anchor_flip is False
    assert leap.anchor == pytest.approx((95.72, 0.99), abs=0.01) and leap.anchor_flip is True
    assert by[("BB_BURST", "P1", "rest")].anchor[0] == pytest.approx(81.26, abs=0.01)
    assert charge.anchor_t == pytest.approx(1.0166, abs=0.02)
    assert [s for s, _, _ in charge.states] == ["Emerge Antic C", "Charge Emerge", "Charge Antic", "Charge",
                                                "Charge End", "Dig In"]
    assert b.counters == {}


def test_trial_fixture_hits_entities_and_templates(trial):
    b, _ = trial
    t = b.tables()
    atk = t["attacks"]
    assert atk["BB_CHARGE"]["hits_taken"]["by_state"] == {"Charge End": 2}
    assert atk["BB_LEAP"]["hits_taken"]["by_source"] == {"Bone Beast/LeapCollider": 1}
    # the P2 burst's DropBell M2 hits the hero while the next burst is already current: attributed to its owner
    burst_hits = atk["BB_BURST"]["hits_taken"]["by_source"]
    assert burst_hits == {"Boss Scene/BoneBeast AtkBell R": 2, "BoneBeast DropBell M2": 1}
    assert atk["BB_RAGE"]["hits_taken"]["by_source"] == {"Boss Scene/Bone Beast": 1, "BoneBeast DropBell R2": 1}
    ents = t["entities"]
    assert ents["BoneBeast AtkBell L"]["armed_at_boss_state"] == {"Burst Out": 2}  # 2nd P2 burst fires after f1
    assert ents["BoneBeast AtkBell L"]["category"] == "hazard"
    assert ents["BoneBeast DropBell M2"]["armed_by_family"] == {"BB_RAGE": 1, "BB_BURST": 1}
    assert "enabled" not in ents["BoneBeast DropBell M"]["by_state"]["Antic"]
    assert ents["BoneBeast DropBell M"]["by_state"]["Air"]["enabled"] == 1.0
    assert ents["Bone Beast"]["by_state"]["Charge"]["enabled poly7"] > 0.9
    d = t["dwell_s"]
    assert d["Emerge Antic C"]["p50"] == pytest.approx(1.0166, abs=0.02)
    assert d["Charge"]["p50"] == pytest.approx(0.8833, abs=0.02)
    assert d["Submerged"]["max_abs_dwell_minus_state_time"] < 1e-3
    assert t["phases"]["P2"]["boss_hp_at_entry"]["n"] == 1
    tpls = b.templates()
    ext = tpls["BB_CHARGE/anchor"].extent()
    assert ext[0] > -6.5 and 20.0 < ext[2] < 28.5 and ext[1] > -4.2 and ext[3] < 1.6  # the charge crosses the arena
    lx = tpls["BB_LEAP/anchor"].extent()
    assert lx[2] > 20.0 and lx[0] > -6.5  # a Set R leap faces +x in the anchor frame
    assert tpls["BB_RAGE/world"].frame == "world" and tpls["BB_BURST/world"].n_instances == 1
    boxes = {h["source"] for h in atk["BB_BURST"]["hitboxes"]}
    assert {"Bone Beast:box", "BoneBeast AtkBell L:circle", "BoneBeast DropBell M2:circle"} <= boxes


# ---- fixture maker -----------------------------------------------------------------------------------------

def _trim_state(s: dict) -> dict:
    r3 = lambda v: [round(float(x), 3) for x in v]  # noqa: E731
    ents = []
    for e in s.get("ents") or ():
        out = {k: e.get(k) for k in ("iid", "type_key", "category", "src", "hp", "flipX")}
        out["pos"] = r3(e["pos"][:2])
        out["fsms"] = [{"name": f["name"], "state": f["state"]} for f in e.get("fsms") or ()]
        out["colliders"] = [{"kind": c["kind"], "verts_world": r3(c["verts_world"]), "enabled": c["enabled"],
                             "damage": c.get("damage"), **({"r": round(float(c["r"]), 3)} if "r" in c else {})}
                            for c in e.get("colliders") or ()]
        ents.append(out)
    ev = [{k: v for k, v in e.items() if k != "q"} for e in s.get("ev") or () if e.get("k") in ("fsm", "damage")]
    h = s["hero"]
    return {"f": s["f"], "dt": round(float(s["dt"]), 6), "ents": ents, "ev": ev,
            "hero": {"pos": r3(h["pos"][:2]), "box": r3(h["box"]), "health": h["health"]}}


def make_fixture(recording: Path, out: Path = FIXTURE) -> int:
    from ssbot.record.recorder import RecordingReader
    r = RecordingReader(recording)
    states = [[_trim_state(s) for s in r.states(a, b, keys=("dt", "hero", "ents", "ev"))] for a, b in FIXTURE_WINDOWS]
    raw = msgpack.packb({"source": str(recording), "windows": FIXTURE_WINDOWS, "states": states},
                        use_single_float=True)
    out.write_bytes(zstandard.ZstdCompressor(level=19).compress(raw))
    return out.stat().st_size


if __name__ == "__main__":
    print(make_fixture(Path(sys.argv[1])))

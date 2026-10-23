"""Map v2 M2: the Clapper model (ssbot.map2.clapper) - the FSM rules, the V4 memory, predict()'s branches and
shapes, the online tracker, and that the bot does not import it (forum.md 93)."""
from __future__ import annotations

import re
import sys
from pathlib import Path

import numpy as np
import pytest

from ssbot.map2 import clapper as cm

K = cm.Know.load()


def _obs(st="Idle", t=0.0, x=30.0, face=-1, **kw):
    return cm.Obs(1, st, t, x, cm.STAND_Y if st not in ("Air", "Jump") else 10.0, 0.0, 0.0, face, 230, None, **kw)


def _hero(x, T=120, y=4.568, hits=None):
    return cm.HeroPath.constant(x, y, T=T, hits=hits)


def test_know_tables():
    assert K.durations("Slam Antic") == (47, 48, 49)
    lo, nom, hi = K.durations("Evade Scuttle")
    assert lo >= 20 and hi <= 22                 # the escape's 0-frame pass-through is not a duration
    b = K.box("Idle", 0)
    assert np.allclose(b, (-1.341, 2.252, -4.434, -0.533), atol=1e-3)
    assert K.box("Slam 1", 1)[1] > 3.0           # the lunge pose reaches 3.23 u ahead


def test_v4_rules():
    far = cm.V4(("JUMP", "CAST", "JUMP CAST"), (0.5, 0.25, 0.25), (2, 1, 1), (1, 2, 2))
    assert {e for _, e in far.dist()} == {"JUMP", "CAST", "JUMP CAST"}
    far.take("CAST")                              # JUMP missed once -> forced next (missedMax 1)
    assert far.dist() == [(1.0, "JUMP")]
    close = cm.V4(("SLAM", "EVADE", "CAST"), (0.5, 0.5, 0.5), (1, 1, 1), (3, 3, 3))
    close.take("SLAM")                            # eventMax 1: no SLAM right after a SLAM
    assert {e for _, e in close.dist()} == {"EVADE", "CAST"}
    esc = cm.V4(("JUMP", "JUMP CAST"), (1, 1), (1, 1), (1, 1))
    esc.take("JUMP")
    assert esc.dist() == [(1.0, "JUMP CAST")]     # the escape jump alternates


def test_memory_sources():
    m = cm.Memory()
    assert m.observe("Close Range", "Slam Antic", "Walk B") is None          # the Walk B shortcut: no V4 ran
    assert m.observe("Close Range", "Slam Antic", "Walk F") == "close"
    m.observe("Idle", "Evade Scuttle")
    assert m.evaded
    assert m.observe("Close Range", "Spell Antic") == "close_ev"            # after an evade: SLAM / CAST only
    assert not m.evaded
    assert m.observe("Far Range", "Cast Slam Antic") == "far" and m.charged


def test_slam_hammer_timing_and_side():
    """A slam from its antic's first frame: Slam Collider 1 in Slam 1 (antic 47-49 + Slam 0 4-5), in front of it."""
    P = cm.predict([_obs("Slam Antic", 0.0, x=30.0, face=-1)], {}, _hero(25.0), K, T=90)
    assert len(P.branches) == 1
    b = P.branches[0]
    ks = [k for k in range(91) if any(s.name == "Slam Collider 1" for s in b.damage(k))]
    assert ks and 50 <= ks[0] <= 53 and ks[-1] <= 58
    sc1 = next(s for s in b.damage(ks[0]) if s.name == "Slam Collider 1")
    assert sc1.bbox()[0] < 30.0 - 4.0             # facing left: the hammer reaches ~6 u to the left of the lunge
    # the body is a pogo target, the hammer is not
    assert all(s.kinds & cm.POGO for s in b.shapes(10) if s.name == "body")
    assert not any(s.kinds & cm.POGO for s in b.shapes(ks[0]) if s.name.startswith("Slam Collider"))


def test_idle_will_evade_branch_and_reveal():
    """Idle with her inside Slam Range: Will Evade is a 50 / 50 branch revealed at Can Evade (~16 frames)."""
    P = cm.predict([_obs("Idle", 0.0, x=30.0, face=-1)], {1: cm.Memory()}, _hero(27.0, T=60), K, T=60)
    evs = [b for b in P.branches if any(c[0] == "will_evade" for c in b.choices[1])]
    assert len(evs) >= 2
    assert abs(sum(b.p for b in P.branches) - 1.0) < 1e-9
    rv = sorted(b.reveal for b in evs)
    assert 14 <= rv[0] <= 18


def test_hit_on_idle_reacts_in_the_hit_frame():
    hero = _hero(27.0, T=40, hits={1: {5: ("side", 10)}})
    P = cm.predict([_obs("Idle", 0.0, x=30.0, face=-1)], {1: cm.Memory()}, hero, K, T=40, group=False)
    for b in P.branches:
        st5 = [r[3] for r in b.recs[1] if r[0] == 5][0]
        assert st5 in ("Slam Antic", "Spell Antic", "Evade Scuttle")            # Dmg Attack -> Close Range -> move


def test_far_jump_lands_at_the_aim_formula():
    """Out of Slam Range a forced JUMP: the landing = take-off + 0.916 x clamp(her x - 5 x facing - x, 12)."""
    m = cm.Memory()
    m.v4["far"].take("CAST")                      # -> JUMP forced
    hero = _hero(18.0, T=120, hits={1: {2: ("side", 0)}})
    P = cm.predict([_obs("Idle", 0.0, x=32.0, face=-1)], {1: m}, hero, K, T=120, group=False)
    b = P.branches[0]
    land = next(r for r in b.recs[1] if r[3] == "Slam 2")
    aim_x = 32.0 + 0.48 * 0 + 0.0
    expect = 32.0 + 0.916 * float(np.clip(18.0 + 5.0 - 32.0, -12, 12))
    assert abs(land[5] - expect) < 0.6
    assert any(c[0] == "far" and c[1] == "JUMP" for c in b.choices[1])
    del aim_x


def test_wall_push_moves_the_landing_away_from_the_wall():
    """A jump taking off at the left wall: the roof's slope pushes it out (the person's wall push)."""
    m = cm.Memory()
    m.v4["far"].take("CAST")
    o = _obs("Idle", 0.0, x=15.95, face=1)
    # her above it, out of Slam Range (its top 10.8): the far list; the aim 5 u short of her x toward the wall
    hero = _hero(17.5, T=120, y=14.0, hits={1: {2: ("down", 0)}})
    P = cm.predict([o], {1: m}, hero, K, T=120, group=False)
    b = P.branches[0]
    land = next(r for r in b.recs[1] if r[3] == "Slam 2")
    air = sum(1 for r in b.recs[1] if r[3] == "Air")
    naive = 15.95 + 0.916 * (17.5 - 5.0 - 15.95)
    assert land[5] > naive + 1.0 and air < 50           # pushed out by the roof, a shorter flight (fit: 43 - 46)


def test_buddy_lock_cancels():
    """Close Range while the buddy attacks: CANCEL to Idle (a hit on it is a free hit)."""
    a = cm.Obs(1, "Idle", 0.5, 30.0, cm.STAND_Y, face=-1, hp=230, will_evade=False)
    b = cm.Obs(2, "Slam Antic", 0.1, 40.0, cm.STAND_Y, face=-1, hp=230)
    hero = cm.HeroPath.constant(27.0, 4.568, T=30, hits={1: {3: ("side", 10)}})
    P = cm.predict([a, b], {}, hero, K, T=30, group=False)
    for br in P.branches:
        st = [r[3] for r in br.recs[1] if 3 <= r[0] <= 8]
        assert st[0] == "Idle"
        assert any(c[0] == "cancel" for c in br.logs[1])


def test_shapes_grow_and_danger_boxes():
    s = cm.Shape(cm.DAMAGE, 0, "Slam Collider 1", poly=cm.HAMMER["Slam Collider 1"].copy(), mv="slam")
    g = s.grown(0.3)
    b0, b1 = s.bbox(), g.bbox()
    assert abs(b1[0] - (b0[0] - 0.3)) < 1e-9 and abs(b1[3] - (b0[3] + 0.3)) < 1e-9
    P = cm.predict([_obs("Slam Antic", 0.0)], {}, _hero(25.0, T=60), K, T=60)
    db = P.danger_boxes(52, margins=False)
    assert db.shape[1] == 4 and len(db) >= 2


def test_tracker_obs_from_states():
    """The online tracker: the V4 replay from the transitions, the frames in the state, Will Evade's evidence."""
    trk = cm.Tracker()

    def ent(st, t, x=30.0):
        return {"iid": 7, "type_key": "Song Heavy Sentry", "pos": [x, cm.STAND_Y], "vel": [0, 0], "flipX": False,
                "hp": 200, "fsms": [{"name": "Control", "state": st, "t": t}], "anim": {"clip": "Idle"}}
    ev = [{"k": "fsm", "d": {"iid": 7, "obj": "Song Heavy Sentry", "fsm": "Control", "from": a, "to": b}}
          for a, b in (("Walk", "Close Range"), ("Close Range", "Slam Antic"))]
    trk.feed({"hero": {"box": [26.0, 3.015, 26.5, 5.09]}, "ents": [ent("Slam Antic", 0.0)], "ev": ev})
    for i in range(1, 5):
        trk.feed({"hero": {"box": [26.0, 3.015, 26.5, 5.09]}, "ents": [ent("Slam Antic", i / 60)], "ev": []})
    o = trk.obs()[0]
    assert o.st == "Slam Antic" and o.j == 4
    assert trk.mems()[7].v4["close"].run == [1, 0, 0]
    ev2 = [{"k": "fsm", "d": {"iid": 7, "obj": "Song Heavy Sentry", "fsm": "Control", "from": "Slam Recover",
                              "to": "Idle"}}]
    trk.feed({"hero": {"box": [26.0, 3.015, 26.5, 5.09]}, "ents": [ent("Idle", 0.0)], "ev": ev2})
    for i in range(1, 20):
        trk.feed({"hero": {"box": [26.0, 3.015, 26.5, 5.09]}, "ents": [ent("Idle", i / 60)], "ev": []})
    o = trk.obs()[0]
    assert o.st == "Idle" and o.will_evade is False          # in range at Can Evade and no evade


def test_bot_does_not_import_map2():
    """M2 is offline: the bot's code paths do not import ssbot.map2 (decisions bit-identical); the overlay imports
    it only inside its --overlay-map2 layer."""
    root = Path(cm.__file__).resolve().parents[1]
    pat = re.compile(r"^\s*(from|import)\s+ssbot\.map2|ssbot\.map2\s+import", re.M)
    allowed = {"tools/m1_envelope.py", "tools/m2_validate.py", "tools/zone_overlay.py", "tools/m3_search.py",
               "tools/m3_accept.py", "tools/m4b_speed.py"}
    offenders = []
    for p in root.rglob("*.py"):
        rel = p.relative_to(root).as_posix()
        if rel.startswith("map2/") or rel in allowed:
            continue
        if pat.search(p.read_text(encoding="utf-8", errors="ignore")):
            offenders.append(rel)
    assert offenders == []
    for name in [m for m in sys.modules if m.startswith("ssbot.tools.zone_overlay")]:
        del sys.modules[name]
    before = {m for m in sys.modules if m.startswith("ssbot.map2")}
    for m in before:
        del sys.modules[m]
    import importlib
    importlib.import_module("ssbot.tools.zone_overlay")
    assert not any(m.startswith("ssbot.map2") for m in sys.modules)


@pytest.mark.skipif(not Path(r"C:\ssbot\data\m2_play\map2\m2\cache\held").exists(), reason="no recorded traces")
def test_tracker_matches_the_validation_obs():
    """On a recorded episode the online Tracker's Obs equal the validation's (same state, frames in it, Will Evade
    evidence, bomb row seed) at sampled frames."""
    from ssbot.tools import m2_validate as mv
    from ssbot.tools.m2_clapper import load_set
    tr = next(load_set("held"))
    E = mv.Episode(tr)
    mem_at = mv._memories(E)
    from ssbot.record.recorder import RecordingReader
    import json
    row = None
    run = Path(tr["meta"]["run"])
    for line in (run / f"attempts_i{tr['meta']['inst']}.jsonl").read_text("utf-8").splitlines():
        r = json.loads(line)
        if r.get("episode") == tr["meta"]["episode"]:
            row = r
    states = list(RecordingReader(row["recording"]).states(int(row["f_wake"]) - 30, int(row["f_end"])))
    trk = cm.Tracker()
    n_cmp = 0
    for i, s in enumerate(states):
        g = int(E.gi[i])
        trk.feed(s, k=g)
        if i < 200 or i % 97 or E.g2i[g] != i:
            continue
        got = {o.iid: o for o in trk.obs()}
        for iid in E.iids:
            o = E.obs(iid, g, mem_at(iid, g))
            if o is None or iid not in got:
                continue
            t = got[iid]
            assert t.st == o.st
            assert abs(t.j - o.j) <= 1
            assert t.will_evade == o.will_evade
            n_cmp += 1
    assert n_cmp > 5

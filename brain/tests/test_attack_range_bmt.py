"""Attack range, stage B types: the Bellbearer (its bell on the real / decided path, the builder's bell truth), the
Maestro (the slash side decided at Slash 1) and the Tiny (the orbit around the Maestro, its own parked states), and the
stage B hooks (EnemySpec.custom / attach, Decision.scale, the type's parked states live). Offline, synthetic data."""
import math

import numpy as np
import pytest

from ssbot.combat import attack_range as ar
from ssbot.combat.are_types import module_of
from ssbot.combat.are_types import bellbearer as bb
from ssbot.combat.are_types import tiny as ti

C = ar.CELL
BB = "Pilgrim 03 Song"
TINY = "Song Automaton Tiny"
MAE = "Song Pilgrim Maestro"


def test_registry_has_the_stage_b_types():
    assert module_of("bellbearer").SPEC.type_key == BB
    assert module_of("maestro").SPEC.type_key == MAE
    assert module_of("tiny").SPEC.type_key == TINY
    assert ar.SPECS[MAE].decide["MA_SLASH"].scale is False
    for tk in (BB, MAE, TINY):
        s = ar.SPECS[tk]
        for st, fam in s.start.items():
            assert st in s.fam_states[fam]


def test_bell_path_gravity_bounce_walls_end():
    # 50 Hz semi-implicit Euler, g 60: after 10 steps vy = 20 - 12 = 8, y = sum of vy_i x 0.02
    x, y = bb.bell_path(30.0, 10.0, -5.0, 20.0, 0.2, False)
    assert x == pytest.approx(29.0) and y == pytest.approx(10.0 + 0.02 * sum(20.0 - 1.2 * i for i in range(1, 11)))
    # a bell falling onto the floor bounces once (vy back to 20) ...
    p = bb.bell_path(30.0, 3.6, 0.0, -10.0, 0.1, False)
    assert p is not None and p[1] > bb.FLOOR_Y
    # ... and ends at its second floor contact
    assert bb.bell_path(30.0, 3.6, 0.0, -10.0, 0.1, True) is None
    # the walls send it back at 10 u/s
    x, _ = bb.bell_path(14.6, 8.0, -15.0, 20.0, 0.2, False)
    assert x == pytest.approx(bb.WALLS[0] + 10.0 * 0.02 * 9, abs=0.05)


def test_spit_rule_clamps_and_keeps_4():
    assert bb.spit_vx(4.0, 0.0) == pytest.approx(4.6)
    assert bb.spit_vx(30.0, 1.0) == 15.0 and bb.spit_vx(-30.0, -1.0) == -15.0
    assert bb.spit_vx(1.0, -1.0) == pytest.approx(4.0)          # 0.15 -> abs(vx) >= 4 toward its sign
    assert bb.spit_vx(-0.5, 0.0) == pytest.approx(-4.0)


def _bb(st, x=30.0, y=12.0, iid=5, tin=0.0, flip=False):
    return {"type_key": BB, "iid": iid, "pos": [x, y, 0.0], "flipX": flip, "vel": [0.0, 0.0],
            "fsms": [{"name": "Control", "state": st, "t": tin}],
            "cols": [{"name": "Pilgrim 03 Song", "enabled": True,
                      "verts_world": [x - 0.66, y - 0.76, x + 0.66, y - 0.76, x + 0.66, y + 0.76, x - 0.66, y + 0.76]}]}


def _bell(x, y, vx, vy, st="Air", iid=77, dealt=1):
    return {"type_key": bb.BELL, "iid": iid, "pos": [x, y, 0.0], "vel": [vx, vy],
            "fsms": [{"name": "Control", "state": st, "t": 0.0}],
            "cols": [{"name": "Throwing Bell(Clone)", "enabled": True, "damage": {"dealt": dealt},
                      "verts_world": [x - 0.425, y - 0.425, x + 0.425, y - 0.425, x + 0.425, y + 0.425, x - 0.425,
                                      y + 0.425]}]}


def _bb_table():
    spec = ar.SPECS[BB]
    body = np.ones((int(1.5 / C), int(1.3 / C)), bool)
    nb = 80
    tp = ar.Template(nb=nb, shape=[body] * nb, origin=np.tile(np.array([[-13, -15]], np.int32), (nb, 1)),
                     disp=np.zeros((nb, 2)), n=1)
    return ar.RangeTable(spec=spec, templates={("CB_THROW", "main"): tp, ("CB_EVADE", "main"): tp},
                         meta={"face_flip1": 1})


def test_live_bell_in_flight_drawn_on_its_path_and_only_for_its_owner():
    tab = _bb_table()
    trk = ar.RangeTracker(tables={BB: tab})
    ents = [_bb("In Range", x=30.0, iid=5), _bb("In Range", x=40.0, iid=6), _bell(31.0, 11.0, -6.0, 12.0)]
    trk.feed({"dt": ar.FT, "hero": {"pos": [20.0, 4.0]}, "ents": ents})
    e5, e6 = trk.estimate(5, 12), trk.estimate(6, 12)
    assert e5.haz is not None and e5.haz.m.any() and (e6.haz is None or not e6.haz.m.any())
    px, py = bb.bell_path(31.0, 11.0, -6.0, 12.0, 12 * ar.FT, False)
    x0, y0, x1, y1 = e5.haz.bbox()
    assert 0.5 * (x0 + x1) == pytest.approx(px, abs=2 * C) and 0.5 * (y0 + y1) == pytest.approx(py, abs=2 * C)
    # hit back by the nail: harmless, not drawn
    trk.feed({"dt": ar.FT, "hero": {"pos": [20.0, 4.0]},
              "ents": ents[:2] + [_bell(31.0, 11.0, 30.0, 0.0, st="Nail Hit", dealt=0)]})
    e5 = trk.estimate(5, 12)
    assert e5.haz is None or not e5.haz.m.any()


def test_live_throw_antic_draws_the_decided_arc_near_the_release_only():
    tab = _bb_table()
    trk = ar.RangeTracker(tables={BB: tab})
    for i in range(20):
        trk.feed({"dt": ar.FT, "hero": {"pos": [22.0, 4.0]}, "ents": [_bb("Throw Antic", tin=i * ar.FT)]})
    e = trk.estimate(5, 6)                                      # 0.42 s after the antic start: before any release
    assert e.haz is None or not e.haz.m.any()
    e = trk.estimate(5, 30)                                     # 0.82 s: the arc released at 0.617-0.721 s
    assert e.haz.m.any()
    vx = bb.spit_vx(22.0 - 30.0, 0.0)
    px, py = bb.bell_path(30.0 + math.copysign(0.94, vx), 11.5, vx, 20.0, 49 * ar.FT - 0.67, False)
    x0, y0, x1, y1 = e.haz.bbox()
    assert x0 - C <= px <= x1 + C and y0 - C <= py <= y1 + C


def test_bell_attach_gives_the_flight_to_its_thrower():
    from ssbot.tools.attack_range_build import tracks_from_cache
    F = 120
    T = np.arange(F) * ar.FT
    names_st = ["In Range", "Throw Antic", "Throw", "Recover", "Air"]
    seq = np.array([0] * 10 + [1] * 40 + [2] * 10 + [3] * 60)
    rel = 50
    brow = list(range(rel, rel + 30))
    n_e = 2 * F + len(brow)
    bx = [30.0 - 0.94 - 6.0 * (i * ar.FT) for i in range(len(brow))]
    c = {"types": [BB, bb.BELL], "states": names_st, "names": ["Pilgrim 03 Song", "Throwing Bell(Clone)"],
         "f": np.arange(F), "T": T, "hx": np.full(F, 20.0), "hy": np.full(F, 4.0), "events": [], "meta": {"id": "syn"}}
    c.update(e_fi=np.concatenate([np.arange(F), np.arange(F), brow]).astype(np.int32),
             e_iid=np.array([5] * F + [6] * F + [77] * len(brow), np.int64),
             e_tk=np.array([0] * (2 * F) + [1] * len(brow), np.int16),
             e_x=np.array([30.0] * F + [45.0] * F + bx, np.float32),
             e_y=np.array([12.0] * (2 * F) + [11.5] * len(brow), np.float32),
             e_vx=np.array([0.0] * (2 * F) + [-6.0] * len(brow), np.float32),
             e_vy=np.array([0.0] * (2 * F) + [20.0] * len(brow), np.float32), e_flip=np.zeros(n_e, np.int8),
             e_st=np.concatenate([seq, np.zeros(F, int), [4] * len(brow)]).astype(np.int16),
             e_tin=np.zeros(n_e, np.float32), e_hidden=np.zeros(n_e, np.int8), e_src=np.zeros(n_e, np.int16))
    c.update(c_ei=np.arange(2 * F, n_e, dtype=np.int32), c_name=np.ones(len(brow), np.int16),
             c_box=np.array([[x - 0.425, 11.075, x + 0.425, 11.925] for x in bx], np.float32),
             c_dealt=np.ones(len(brow), np.int8), c_eff=np.ones(len(brow), np.int8))
    trs = tracks_from_cache(c, BB, "dev")
    bb.attach(c, trs)
    own = {tr["iid"]: tr for tr in trs}
    assert len(own[5]["bells"]) == 1 and not own[6]["bells"]
    assert own[5]["bells"][0]["t_ant"] == pytest.approx(T[10])
    assert any(nm == "HZ:bell" for nm, _ in own[5]["cols"][rel + 3])


def test_tiny_orbit_turns_around_the_maestro_with_the_profiles():
    tin, tau = 1.0, 12 * ar.FT
    # a Tiny 5 u right of a still Maestro, moving up (counter-clockwise)
    dx, dy = ti.orbit_shift(35.0, 10.0, 0.0, 15.0, (30.0, 10.0, 0.0, 0.0), tin, tau)
    ang = ti._turn(tin, tau)
    assert ang == pytest.approx(math.radians(ti._prof(ti.W_PROF, tin)) * tau, rel=0.1)
    r1 = 5.0 + ti._prof(ti.R_PROF, tin + tau) - ti._prof(ti.R_PROF, tin)
    assert 35.0 + dx == pytest.approx(30.0 + r1 * math.cos(ang), abs=1e-6)
    assert 10.0 + dy == pytest.approx(10.0 + r1 * math.sin(ang), abs=1e-6)
    # clockwise: the other way; a moving Maestro carries the centre
    dx2, dy2 = ti.orbit_shift(35.0, 10.0, 2.0, -15.0, (30.0, 10.0, 2.0, 0.0), tin, tau)
    assert 10.0 + dy2 == pytest.approx(10.0 - r1 * math.sin(ang), abs=1e-6)
    assert 35.0 + dx2 == pytest.approx(30.0 + 2.0 * tau + r1 * math.cos(ang), abs=1e-6)


def _tiny(st, x, y, vx=0.0, vy=0.0, iid=9, tin=0.0):
    return {"type_key": TINY, "iid": iid, "pos": [x, y, 0.0], "vel": [vx, vy], "flipX": False,
            "fsms": [{"name": "Control", "state": st, "t": tin}],
            "cols": [{"name": "Song Automaton Tiny(Clone)", "enabled": True,
                      "verts_world": [x - 0.5, y - 0.54, x + 0.5, y - 0.54, x + 0.5, y + 0.54, x - 0.5, y + 0.54]}]}


def _mae(x, y, st="Defending", iid=2):
    return {"type_key": MAE, "iid": iid, "pos": [x, y, 0.0], "vel": [0.0, 0.0], "flipX": False,
            "fsms": [{"name": "Control", "state": st, "t": 0.0}], "cols": []}


def test_tiny_ready_is_in_play_and_defend_buzz_orbits_live():
    spec = ar.SPECS[TINY]
    assert not ar._parked(_tiny("Ready", 30.0, 10.0), spec.parked)
    assert ar._parked(_tiny("Ready", 30.0, 10.0))                      # the default PARKED would drop it
    assert ar._parked(_tiny("Dead", 30.0, 10.0), spec.parked)
    body = np.ones((int(1.08 / C), int(1.0 / C)), bool)
    tp = ar.Template(nb=60, shape=[body] * 60, origin=np.tile(np.array([[-10, -11]], np.int32), (60, 1)),
                     disp=np.zeros((60, 2)), n=1)
    tab = ar.RangeTable(spec=spec, templates={("AT_DEFEND", "main"): tp, ("AT_DIVE", "main"): tp},
                        meta={"face_flip1": 1})
    trk = ar.RangeTracker(tables={TINY: tab})
    trk.feed({"dt": ar.FT, "hero": {"pos": [20.0, 4.0]},
              "ents": [_tiny("Defend Buzz", 35.0, 10.0, vy=15.0, tin=1.0), _mae(30.0, 10.0)]})
    e = trk.estimate(9, 12)
    dx, dy = ti.orbit_shift(35.0, 10.0, 0.0, 15.0, (30.0, 10.0, 0.0, 0.0), 1.0, 12 * ar.FT)
    x0, y0, x1, y1 = e.raw.bbox()
    assert 0.5 * (x0 + x1) == pytest.approx(35.0 + dx, abs=2 * C)
    assert 0.5 * (y0 + y1) == pytest.approx(10.0 + dy, abs=2 * C)
    e0 = trk.estimate(9, 0)                                            # k 0: the body now
    x0, y0, x1, y1 = e0.raw.bbox()
    assert 0.5 * (x0 + x1) == pytest.approx(35.0, abs=2 * C) and 0.5 * (y0 + y1) == pytest.approx(10.0, abs=2 * C)


def test_maestro_slash_pending_until_slash1_then_in_the_decided_side():
    """Decision.scale False: after the decision the template's median u displacement, mirrored by the decided side."""
    spec = ar.SPECS[MAE]
    body = np.ones((int(2.0 / C), int(1.8 / C)), bool)
    hit = np.ones((int(2.4 / C), int(3.2 / C)), bool)
    nb = 60
    shapes = [body] * 42 + [hit] * 18
    origin = np.array([[-18, -20]] * 42 + [[10, -20]] * 18, np.int32)       # the slash in front (u > 0.5)
    disp = np.zeros((nb, 2))
    disp[42:, 0] = -np.arange(18) * 0.1                                     # recoil after the decision
    tp = ar.Template(nb=nb, shape=shapes, origin=origin, disp=disp, n=1, b_dec=42)
    tab = ar.RangeTable(spec=spec, templates={("MA_SLASH", "main"): tp}, meta={"face_flip1": 1})
    trk = ar.RangeTracker(tables={MAE: tab})
    for i in range(10):
        trk.feed({"dt": ar.FT, "hero": {"pos": [20.0, 4.0]}, "ents": [_mae(30.0, 8.0, "Fire Antic", iid=2)]})
    e = trk.estimate(2, 40)
    x0, _, x1, _ = e.raw.bbox()
    assert x1 - x0 == pytest.approx(1.8, abs=2 * C)                          # pending: the antic body only
    for i in range(33):
        trk.feed({"dt": ar.FT, "hero": {"pos": [20.0, 4.0]},
                  "ents": [_mae(30.0, 8.0, "Fire Antic" if i < 32 else "Slash 1", iid=2)]})
    inst = trk.now[2][2]
    assert inst.dec is not None and inst.dec["s"] == -1                     # the hero is on the left
    e = trk.estimate(2, 5)
    x0, _, x1, _ = e.raw.bbox()
    # the slash on the hero's side (u 0.5 .. 3.7 mirrored), the body 0.5 u back (+x) by the median recoil at bin 47
    assert x1 == pytest.approx(30.5 - 0.5, abs=2 * C) and x1 - x0 == pytest.approx(3.2, abs=2 * C)


def test_solo_keeps_the_maestros_tinies_and_maps_the_tiny_to_its_maestro():
    from ssbot.tools.solo_practice import SoloController, plan_for

    class Line:
        def __init__(self):
            self.pd = {}

        def pdget(self, k):
            return self.pd.get(k, "1")

        def pdset(self, k, v):
            self.pd[k] = v

        def close(self):
            pass

    def st(ents):
        return {"room": {"battles": [{"name": "Battle Scene", "started": True, "id": 1}]}, "ents": ents}

    def en(tk, iid):
        return {"type_key": tk, "iid": iid, "hp": 30, "src": 1 | 8, "fsms": [{"name": "Control", "state": "Fly"}]}
    assert plan_for(TINY).type_key == MAE and plan_for(TINY).savestate == plan_for(MAE).savestate
    sc = SoloController(TINY, debug=Line, rpc=lambda *a, **k: {}, log=lambda *_: None)
    assert sc.tk == MAE
    assert sc.tick(st([en(MAE, 5), en(MAE, 6), en(TINY, 40), en(TINY, 41)])) == "clear"   # the other Maestro
    assert sc.tick(st([en(MAE, 5), en(TINY, 40), en(TINY, 41)])) == "solo"                # its Tinies stay

def test_tiny_dive_carried_by_velocity_and_steering_not_by_a_wall_hit():
    from ssbot.combat.are_spec import CustomView
    tr = {"T": np.array([0.0, ar.FT]), "vx": np.array([-24.0, -24.0]), "vy": np.array([-26.2, -24.8])}
    v = CustomView(tab=None, inst=None, k=12, T=ar.FT, t=13 * ar.FT, x=30.0, y=12.0, vx=-24.0, vy=-24.8, s=-1,
                   st="Fire", tin=0.2, hero=None, track=tr, j=1)
    tau = 12 * ar.FT
    dx, dy = ti.kinematic_shift(v, tau)
    ay = (-24.8 + 26.2) / ar.FT
    assert dx == pytest.approx(-24.0 * tau) and dy == pytest.approx(-24.8 * tau + 0.5 * ay * tau * tau)
    # at the wall its vx is zeroed (-24 -> 0 in a frame): no 1,440 u/s^2 "steering" back across the arena
    tr["vx"] = np.array([-24.0, 0.0])
    v = CustomView(tab=None, inst=None, k=12, T=ar.FT, t=13 * ar.FT, x=14.51, y=6.07, vx=0.0, vy=-20.9, s=-1,
                   st="Fire", tin=0.4, hero=None, track=tr, j=1)
    dx, dy = ti.kinematic_shift(v, tau)
    assert dx == pytest.approx(0.0, abs=1e-9) and 6.07 + dy >= 4.7 - 1e-9          # the floor clamp
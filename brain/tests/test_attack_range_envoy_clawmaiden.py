"""Attack-range types of stage B: the Envoy (the charge drawn to 4 u past the hero or the wall), the Clawmaiden (the
slash side decided twice: the union of the branches still possible; the flying body carried along its velocity; the
teleport's random arrival not drawn) and her Spear (the decided path: aim rule, antic, homing flight, explosion), and
the two framework hooks they use (EnemySpec.on_step / place_fn, a polygon collider in the builder's truth). Offline,
synthetic tables."""
import math

import numpy as np
import pytest

from ssbot.combat import attack_range as ar
from ssbot.combat.are_types import module_of
from ssbot.combat.are_types import clawmaiden as cm
from ssbot.combat.are_types import envoy as en
from ssbot.combat.are_types import spear as sp

C = ar.CELL
ENVOY, CLAW, SPEAR = "Song Pilgrim 01", "Song Handmaiden", "Spear"


def test_registry_has_the_stage_b_types():
    assert module_of("envoy").SPEC.type_key == ENVOY
    assert module_of("clawmaiden").SPEC.type_key == CLAW
    assert module_of("spear").SPEC.type_key == SPEAR
    for t in (ENVOY, CLAW, SPEAR):
        assert ar.SPECS[t].place_fn is not None and ar.SPECS[t].on_step is not None


def _box(w, h, u0, v0):
    return (np.ones((int(round(h / C)), int(round(w / C))), bool), int(round(u0 / C)), int(round(v0 / C)))


def _gated(fam, states_by_bin, nb, branches=("main",)):
    """A state-gated template: per bin {state: shape}, order by first bin."""
    tps = {}
    for br in branches:
        sst = [dict(states_by_bin(b)) for b in range(nb)]
        order = {}
        for b in range(nb):
            for st in sst[b]:
                order.setdefault(st, len(order))
        order.setdefault("<end>", len(order))
        shp = [next(iter(d.values()))[0] if d else np.zeros((0, 0), bool) for d in sst]
        org = np.array([[next(iter(d.values()))[1], next(iter(d.values()))[2]] if d else [0, 0] for d in sst], np.int32)
        tps[(fam, br)] = ar.Template(nb=nb, shape=shp, origin=org, disp=np.zeros((nb, 2)), n=2, sst=sst, order=order)
    return tps


BODY = _box(1.2, 2.0, -0.6, -1.0)
CHARGE = _box(4.4, 2.0, -0.6, -1.0)          # the body + the Charge Damager in front


def _envoy_table():
    def sb(b):
        if b < 30:
            return {"Charge Antic": BODY}
        if b < 90:
            return {"Charge": CHARGE, "Charge End": BODY}
        return {"<end>": BODY}
    return ar.RangeTable(spec=ar.SPECS[ENVOY], templates=_gated("EN_CHARGE", sb, 120),
                         meta={"face_flip1": 1, "walls": [17.37, 45.57]})


def _ent(tk, st, x, y=4.0, flip=False, iid=5, tin=0.0, vel=(0.0, 0.0)):
    return {"type_key": tk, "iid": iid, "pos": [x, y, 0.0], "flipX": flip, "vel": list(vel),
            "fsms": [{"name": "Control", "state": st, "t": tin}], "cols": []}


def test_envoy_charge_stops_4u_past_the_hero_or_at_the_wall():
    en._STATE_SHAPES.clear()
    tab = _envoy_table()
    trk = ar.RangeTracker(tables={ENVOY: tab})
    for i in range(3):                                   # facing -x, hero 10 u ahead
        trk.feed({"dt": ar.FT, "hero": {"pos": [25.0, 4.0]}, "ents": [_ent(ENVOY, "Charge Antic", 35.0, tin=i * ar.FT)]})
    e0 = trk.estimate(5, 0)
    x0, _, x1, _ = e0.raw.bbox()
    assert x0 == pytest.approx(34.4, abs=2 * C) and x1 == pytest.approx(35.6, abs=2 * C)    # k 0: the body
    # charging from bin 30 at 13 u/s: bin 2 + 40 -> 12 bins of charge = 2.6 u, the damager in front (-x)
    x0, _, x1, _ = trk.estimate(5, 40).raw.bbox()
    assert x1 == pytest.approx(35.6 - 2.6, abs=2 * C) and x1 - x0 == pytest.approx(4.4, abs=2 * C)
    # stopped at 25 - 4 = 21 at bin 30 + ceil(14 / (13/60)) = 95, then the Charge End skid, then the body
    x0, _, x1, _ = trk.estimate(5, 117 - 2).raw.bbox()
    assert 0.5 * (x0 + x1) == pytest.approx(21.0 - en.SKID[22], abs=2 * C)
    x0, _, x1, _ = trk.estimate(5, 121 - 2).raw.bbox()
    assert 0.5 * (x0 + x1) == pytest.approx(21.0 - en.SKID[-1], abs=2 * C)
    # the hero beyond the wall side: the wall stops it (body x 17.37)
    en._STATE_SHAPES.clear()
    trk = ar.RangeTracker(tables={ENVOY: tab})
    for i in range(32):
        trk.feed({"dt": ar.FT, "hero": {"pos": [12.0, 4.0]},
                  "ents": [_ent(ENVOY, "Charge Antic" if i < 30 else "Charge", 30.0)]})
    assert trk.now[5][2].extra["charge_t"] == pytest.approx(31 * ar.FT)
    x0, _, x1, _ = trk.estimate(5, 80).raw.bbox()
    assert 0.5 * (x0 + x1) == pytest.approx(en.CHARGE_WALLS[0], abs=2 * C)


def _claw_table():
    def sb(b):
        if b < 30:
            return {"Slash Antic": BODY}
        return {"Slash 1": _box(4.0, 2.0, 0.0, -1.0)}
    tps = {}
    for br in cm.SLASH_BRANCHES:                     # "t*": the slash behind the antic's facing
        t = _gated("CM_SLASH", (lambda b, br=br: sb(b) if br[0] == "f" or b < 30 else
                                {"Slash 1": _box(4.0, 2.0, -4.0, -1.0)}), 60, (br,))
        tps.update(t)
    tps.update(_gated("CM_FLY", lambda b: {"Fly": BODY}, 60))
    tps.update(_gated("CM_TELE", lambda b: {"Tele Out Antic": BODY} if b < 10 else
                      ({"Tele Out": _box(0.05, 0.05, 0, 0)} if b < 40 else {"<end>": BODY}), 80))
    return ar.RangeTable(spec=ar.SPECS[CLAW], templates=tps, meta={"face_flip1": 1, "walls": [10.0, 50.0]})


def test_clawmaiden_slash_sides_union_until_decided():
    tab = _claw_table()
    trk = ar.RangeTracker(tables={CLAW: tab})
    hero = {"pos": [40.0, 4.0]}
    for i in range(5):                                   # antic facing +x
        trk.feed({"dt": ar.FT, "hero": hero, "ents": [_ent(CLAW, "Slash Antic", 30.0, 8.0, flip=True)]})
    x0, _, x1, _ = trk.estimate(5, 30).raw.bbox()
    assert x0 < 26.5 and x1 > 33.5                       # before Slash 1: both sides
    for i in range(26):                                  # Slash 1 entered facing -x (turned)
        st = "Slash Antic" if i < 25 else "Slash 1"
        trk.feed({"dt": ar.FT, "hero": hero, "ents": [_ent(CLAW, st, 30.0, 8.0, flip=st == "Slash Antic")]})
    inst = trk.now[5][2]
    assert inst.extra["side1"][1] == "t"
    assert cm.slash_branches(inst, trk.T) == ("t_k", "t_f")
    assert cm.slash_branches(inst, inst.extra["side1"][0] - 0.01) == cm.SLASH_BRANCHES
    x0, _, x1, _ = trk.estimate(5, 2).raw.bbox()
    assert x0 == pytest.approx(26.0, abs=2 * C) and x1 < 31.0     # only the turned side


def test_clawmaiden_fly_body_is_carried_and_the_teleport_arrival_is_not_drawn():
    tab = _claw_table()
    trk = ar.RangeTracker(tables={CLAW: tab})
    trk.feed({"dt": ar.FT, "hero": {"pos": [40.0, 4.0]}, "ents": [_ent(CLAW, "Fly", 30.0, 8.0, flip=True,
                                                                        vel=(6.0, -3.0))]})
    x0, y0, x1, y1 = trk.estimate(5, 12).raw.bbox()
    assert 0.5 * (x0 + x1) == pytest.approx(30.0 + 1.2, abs=2 * C) and 0.5 * (y0 + y1) == pytest.approx(7.4, abs=2 * C)
    cm.CARRY_ON = False
    try:
        x0, _, x1, _ = trk.estimate(5, 12).raw.bbox()
        assert 0.5 * (x0 + x1) == pytest.approx(30.0, abs=2 * C)
    finally:
        cm.CARRY_ON = True
    # with her body colliders exported: k 0 is that body exactly, k 12 the same polygon moved by v x 0.2 s
    e = _ent(CLAW, "Fly", 30.0, 8.0, flip=True, vel=(6.0, -3.0))
    e["cols"] = [{"name": "Song Handmaiden", "enabled": True,
                  "verts_world": [29.5, 6.0, 30.4, 6.0, 30.4, 9.2, 29.5, 9.2]}]
    trk = ar.RangeTracker(tables={CLAW: tab})
    trk.feed({"dt": ar.FT, "hero": {"pos": [40.0, 4.0]}, "ents": [e]})
    assert trk.estimate(5, 0).raw.bbox() == pytest.approx((29.5, 6.0, 30.4, 9.2), abs=C + 1e-6)
    assert trk.estimate(5, 12).raw.bbox() == pytest.approx((30.7, 5.4, 31.6, 8.6), abs=C + 1e-6)
    trk = ar.RangeTracker(tables={CLAW: tab})
    for i in range(12):
        st = "Tele Out Antic" if i < 10 else "Tele Out"
        trk.feed({"dt": ar.FT, "hero": {"pos": [40.0, 4.0]}, "ents": [_ent(CLAW, st, 30.0, 8.0)]})
    assert not trk.estimate(5, 40).raw.m.any()          # the body after the arrival: pending, not drawn


def test_spear_aim_rule_clamps_to_the_fan_and_the_nearer_edge():
    ux, uy = sp.aim_rule(20.0, 10.0, 1, (30.0, 10.0 - sp.AIM_DY))
    assert (ux, uy) == pytest.approx((1.0, 0.0))
    ux, uy = sp.aim_rule(20.0, 10.0, 1, (21.0, 0.0))     # steeply below: -45 deg
    assert math.degrees(math.atan2(uy, ux)) == pytest.approx(-45.0)
    ux, uy = sp.aim_rule(20.0, 10.0, -1, (25.0, 11.0))   # behind her, above: the upper edge on her side
    assert math.degrees(math.atan2(uy, ux)) == pytest.approx(135.0)


def test_spear_flight_straight_homing_and_floor_explosion():
    r = sp.flight(20.0, 10.0, 37.0, 0.0, 37.0, 0.0, 0.2, None, first=True)
    assert r[0] == "fire" and r[1] == pytest.approx(20.0 + 37.0 * 0.2, abs=1e-6) and r[2] == pytest.approx(10.0)
    r = sp.flight(20.0, 10.0, 37.0, 0.0, 37.0, 0.0, 0.2, (40.0, 5.0), first=True)
    assert r[0] == "fire" and r[2] < 10.0 and r[4] < 0          # turned toward the hero below
    r = sp.flight(20.0, 8.0, 0.0, -37.0, 37.0, 0.0, 1.0, None, first=True)
    assert r[0] == "expl"                                       # straight down: the contact point reaches y 3
    assert r[2] == pytest.approx(sp.FLOOR_Y + sp.CONTACT - sp.EXPL_ALONG, abs=1e-6)   # backed to the contact


def test_spear_tracker_pending_antic_then_fire_triangle():
    tab = ar.RangeTable(spec=ar.SPECS[SPEAR], templates={}, meta={"face_flip1": 1})
    trk = ar.RangeTracker(tables={SPEAR: tab})
    hero = {"pos": [40.0, 10.0 - sp.AIM_DY]}
    trk.feed({"dt": ar.FT, "hero": hero, "ents": [_ent(SPEAR, "Antic Pause", 20.0, 10.0, flip=True)]})
    inst = trk.now[5][2]
    assert inst.extra["aim"][1:] == pytest.approx((1.0, 0.0))
    assert not trk.estimate(5, 0).raw.m.any() and not trk.estimate(5, 40).raw.m.any()   # harmless in the antic
    e = trk.estimate(5, 54)                              # past the fire window's late end: two triangles
    assert e.raw.m.any()
    x0, _, x1, _ = e.raw.bbox()
    assert x0 > 20.0 - 3.645 - sp.BASE - 0.1 and x1 < 20.0 + 37.0 * 4 * ar.FT + sp.TIP + 0.5
    trk.feed({"dt": ar.FT, "hero": hero, "ents": [_ent(SPEAR, "Fire", 18.0, 10.0, flip=True, vel=(37.0, 0.0))]})
    x0, y0, x1, y1 = trk.estimate(5, 0).raw.bbox()       # k 0 in Fire: the triangle now
    assert x0 == pytest.approx(18.0 - sp.BASE, abs=2 * C) and x1 == pytest.approx(18.0 + sp.TIP, abs=2 * C)


def test_polygon_collider_in_the_builders_truth():
    from ssbot.tools.attack_range_build import poly_of
    tri = sp.triangle(10.0, 5.0, 0.0, 1.0)
    p = poly_of("Spear", tri.reshape(-1), 0, {})
    assert p.shape == (3, 2) and np.allclose(p, tri)
    assert poly_of("X", np.array([0.0, 0.0, 1.0, 2.0]), 0, {}).shape == (4, 2)

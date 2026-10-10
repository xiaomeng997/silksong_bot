"""The attack-range estimate (combat.attack_range), its error measure (tools.attack_range_build.compare), the overlay
modes that draw it and the single-enemy practice controller (tools.solo_practice): offline, synthetic data."""
import math

import numpy as np
import pytest

from ssbot.combat import attack_range as ar
from ssbot.tools.attack_range_build import compare
from ssbot.tools.solo_practice import SoloController, plan_for

C = ar.CELL


def box(x0, y0, x1, y1):
    return np.array([[x0, y0], [x1, y0], [x1, y1], [x0, y1]], float)


def test_poly_mask_area_and_bbox():
    m = ar.poly_mask([box(10.0, 4.0, 11.0, 6.0)])
    assert m.area() == pytest.approx(2.0, abs=4 * C)
    x0, y0, x1, y1 = m.bbox()
    assert x0 == pytest.approx(10.0, abs=1.5 * C) and x1 == pytest.approx(11.0, abs=1.5 * C)
    assert y0 == pytest.approx(4.0, abs=1.5 * C) and y1 == pytest.approx(6.0, abs=1.5 * C)


def test_hero_space_is_the_hurtbox_dilation_only():
    m = ar.poly_mask([box(10.0, 4.0, 11.0, 6.0)])
    h = ar.hero_space(m)
    x0, y0, x1, y1 = h.bbox()
    hx, hy = ar.HERO_HALF
    # the hero transform p is hit when [p.x +- hx] x [p.y + HERO_DY +- hy] meets the box
    assert x0 == pytest.approx(10.0 - hx, abs=1.5 * C) and x1 == pytest.approx(11.0 + hx, abs=1.5 * C)
    assert y0 == pytest.approx(4.0 - (ar.HERO_DY + hy), abs=1.5 * C)
    assert y1 == pytest.approx(6.0 - (ar.HERO_DY - hy), abs=1.5 * C)


def test_place_shape_mirrors_with_the_facing():
    sh = np.ones((4, 20), bool)                  # u in [1, 2): template cells 20 .. 39 at CELL 0.05
    iu0 = int(round(1.0 / C))
    right = ar.place_shape(sh, iu0, 0, 30.0, 5.0, +1)
    left = ar.place_shape(sh, iu0, 0, 30.0, 5.0, -1)
    assert right.bbox()[0] == pytest.approx(31.0, abs=C) and right.bbox()[2] == pytest.approx(32.0, abs=C)
    assert left.bbox()[0] == pytest.approx(28.0, abs=C) and left.bbox()[2] == pytest.approx(29.0, abs=C)


def test_segmenter_instances_branches_and_backdating():
    seg = ar.Segmenter(ar.CHORISTOR)
    seq = ["Battle Idle", "Slash Antic", "Slash Antic", "Slash 1", "Combo?", "ComboSlash Antic1", "ComboSlash 1",
           "Slash Recover", "Slash Antic", "Slash 1", "Combo?", "Slash Recover", "Battle Idle"]
    insts = []
    for i, st in enumerate(seq):
        inst = seg.step(st, i * ar.FT, 20.0, 4.87, +1, 25.0, tin=0.004 if st == "Slash Antic" else 0.0)
        if inst is not None and (not insts or insts[-1] is not inst):
            insts.append(inst)
    assert len(insts) == 2
    assert insts[0].branch == "combo" and insts[1].branch == "single"
    assert insts[0].t0 == pytest.approx(1 * ar.FT - 0.004)
    assert insts[0].hero_du == pytest.approx(5.0)
    assert seg.cur is None                       # Battle Idle: idle again


def _table():
    """A synthetic table: CH_SLASH single = the body at the anchor then a 2 u blade in front from bin 10."""
    nb = 30
    body = np.ones((int(2.0 / C), int(1.0 / C)), bool)
    blade = np.ones((int(2.0 / C), int(3.0 / C)), bool)
    shapes, origin = [], np.zeros((nb, 2), np.int32)
    for b in range(nb):
        if b < 10:
            shapes.append(body)
            origin[b] = (int(-0.5 / C), 0)
        else:
            shapes.append(blade)
            origin[b] = (int(-0.5 / C), 0)
    tp = ar.Template(nb=nb, shape=shapes, origin=origin, disp=np.zeros((nb, 2)), n=1)
    meta = {"face_flip1": 1, "walls": [14.0, 49.0], "jump_fit": [1.0, 0.0], "jump_lmax": 15.0}
    return ar.RangeTable(spec=ar.CHORISTOR, templates={("CH_SLASH", "single"): tp, ("CH_SLASH", "combo"): tp},
                         meta=meta)


def test_table_roundtrip(tmp_path):
    t = _table()
    p = ar.save_table(t, tmp_path / "t.npz")
    u = ar.load_table(p)
    a = t.place("CH_SLASH", "single", 12, (20.0, 4.0), -1)
    b = u.place("CH_SLASH", "single", 12, (20.0, 4.0), -1)
    assert a.ix0 == b.ix0 and a.iy0 == b.iy0 and np.array_equal(a.m, b.m)


def _ent(st, x=20.0, flip=True, iid=7, tin=0.0):
    return {"type_key": "Song Pilgrim 03", "iid": iid, "pos": [x, 4.87, 0.0], "flipX": flip,
            "fsms": [{"name": "Attack", "state": st, "t": tin}],
            "cols": [{"name": "Body Damager", "enabled": True,
                      "verts_world": [x - 0.44, 4.0, x + 0.44, 4.0, x + 0.44, 6.15, x - 0.44, 6.15]}]}


def test_tracker_idle_is_the_exact_body_and_attack_is_placed():
    trk = ar.RangeTracker(tables={"Song Pilgrim 03": _table()})
    trk.feed({"dt": ar.FT, "hero": {"pos": [25.0, 4.5]}, "ents": [_ent("Battle Idle")]})
    e = trk.estimate(7, 12)
    assert e.fam is None
    assert e.raw.area() == pytest.approx(0.88 * 2.15, rel=0.1)
    for i in range(3):
        trk.feed({"dt": ar.FT, "hero": {"pos": [25.0, 4.5]}, "ents": [_ent("Slash Antic", tin=i * ar.FT)]})
    e0 = trk.estimate(7, 0)
    e12 = trk.estimate(7, 12)
    assert e0.fam == "CH_SLASH" and e0.b == 2
    assert e12.raw.area() == pytest.approx(6.0, rel=0.05)           # the blade, 3 x 2 u
    x0, _, x1, _ = e12.raw.bbox()
    assert x0 == pytest.approx(19.5, abs=C) and x1 == pytest.approx(22.5, abs=C)   # in front (+x: flipX)


def test_tracker_drops_parked_members():
    trk = ar.RangeTracker(tables={"Song Pilgrim 03": _table()})
    e = _ent("Battle Idle")
    e["pos"] = [40.0, 4.5, -15.0]
    trk.feed({"dt": ar.FT, "hero": {"pos": [25.0, 4.5]}, "ents": [e]})
    assert trk.estimates(0) == []


def test_compare_ratio_miss_excess():
    R = ar.poly_mask([box(20.0, 4.0, 22.0, 6.0)])
    c = compare(R, R, +1)
    assert c["aE"] == pytest.approx(c["aR"]) and not c["miss"] and not c["exc"]
    E = ar.poly_mask([box(20.0, 4.0, 21.0, 6.0)])
    c = compare(E, R, +1)
    assert "front" in c["miss"] and c["miss"]["front"][0] == pytest.approx(1.0, abs=2 * C)
    c = compare(E, R, -1)                                          # facing -x: the same cells are behind
    assert "back" in c["miss"]
    c = compare(R, E, +1)
    assert "front" in c["exc"] and c["aE"] / c["aR"] > 1.5


def test_range_modes():
    from ssbot.tools.zone_overlay import View
    v = View(mode="range+red")
    assert v.show("range") and v.show("red") and not v.show("yellow") and not v.needs_forecast()
    assert View(mode="yellow+red").needs_forecast()


# ------------------------------------------------------------------------------------------------ solo practice

def test_plan_for_the_choristor():
    p = plan_for("Song Pilgrim 03")
    assert p.wave == 0 and p.savestate == "fo_r1_w0"
    assert set(p.others) == {"Song Reed", "Song Pilgrim 01"} and not p.ally


class FakeLine:
    def __init__(self):
        self.pd = {"nailUpgrades": "1", "isInvincible": "False"}
        self.log = []

    def pdget(self, k):
        return self.pd[k]

    def pdset(self, k, v):
        self.log.append((k, str(v)))
        self.pd[k] = str(v)
        return "ok"

    def close(self):
        pass


def _st(ents, bid=1):
    return {"room": {"battles": [{"name": "Battle Scene", "started": True, "id": bid}]}, "ents": ents}


def _enemy(tk, iid, hp=55):
    return {"type_key": tk, "iid": iid, "hp": hp, "src": 1 | 8, "fsms": [{"name": "Control", "state": "Idle"}]}


def test_solo_boost_until_one_left_then_protect():
    line = FakeLine()
    calls = []
    sc = SoloController("Song Pilgrim 03", debug=lambda: line, rpc=lambda *a, **k: calls.append(k) or {"set": []},
                        log=lambda *_: None)
    assert sc.tick(_st([_enemy("Song Pilgrim 03", 5), _enemy("Song Reed", 3), _enemy("Song Pilgrim 01", 4)])) \
        == "clear"
    assert line.pd == {"nailUpgrades": "4", "isInvincible": "True"}
    assert sc.tick(_st([_enemy("Song Pilgrim 03", 5), _enemy("Song Pilgrim 03", 9)])) == "clear"   # a 2nd one
    assert sc.tick(_st([_enemy("Song Pilgrim 03", 5)])) == "solo"
    assert line.pd == {"nailUpgrades": "1", "isInvincible": "False"}
    assert sc.tick(_st([_enemy("Song Pilgrim 03", 5, hp=20)])) == "solo"
    assert calls and calls[-1]["type_key"] == "Song Pilgrim 03" and calls[-1]["hp"] == 55
    # a reload: a new battle clears again
    assert sc.tick(_st([_enemy("Song Pilgrim 03", 11), _enemy("Song Reed", 12)], bid=2)) == "clear"
    assert line.pd["isInvincible"] == "True"
    sc.close()
    assert line.pd == {"nailUpgrades": "1", "isInvincible": "False"}


def test_solo_without_enemy_hp_turns_protection_off():
    def rpc(*a, **k):
        raise RuntimeError("unknown rpc enemy.hp")
    sc = SoloController("Song Pilgrim 03", debug=FakeLine, rpc=rpc, log=lambda *_: None)
    sc.tick(_st([_enemy("Song Pilgrim 03", 5, hp=55)]))
    sc.tick(_st([_enemy("Song Pilgrim 03", 5, hp=10)]))
    assert sc.protect is False and any("protection off" in e for e in sc.events)


def test_hero_kernel_extent():
    k, (ax, ay) = ar.hero_kernel()
    hx, hy = ar.HERO_HALF
    assert (k.shape[1] - 1) / 2 * C == pytest.approx(hx, abs=C)
    assert -ay * C == pytest.approx(ar.HERO_DY - hy, abs=C)
    assert (k.shape[0] - 1 - ay) * C == pytest.approx(ar.HERO_DY + hy, abs=C)
    assert math.isfinite(float(k.sum()))

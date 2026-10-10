import json

import numpy as np
import pytest

from ssbot.knowledge import hitbox_tables as hb
from ssbot.tools import support_precision as sp
from ssbot.tools import zone_overlay as zo

HX, HY = hb.HERO_HALF_U


def _brute(grid, poly, hx, hy, res=0.01):
    """Hero centres whose box meets the polygon, from the polygon filled at res u (cv2) and a box sum over it."""
    import cv2
    poly = np.asarray(poly, np.float64)
    o = poly.min(0) - (hx, hy) - 2 * grid.cell
    n = np.ceil((poly.max(0) + (hx, hy) + 2 * grid.cell - o) / res).astype(int) + 1
    img = np.zeros((n[1], n[0]), np.uint8)
    cv2.fillPoly(img, [np.rint((poly - o) / res).astype(np.int32)], 1)
    ii = cv2.integral(img)
    out = np.zeros(grid.shape, bool)
    for r, y in enumerate(grid.ys):
        for c, x in enumerate(grid.xs):
            x0, x1 = int(round((x - hx - o[0]) / res)), int(round((x + hx - o[0]) / res)) + 1
            y0, y1 = int(round((y - hy - o[1]) / res)), int(round((y + hy - o[1]) / res)) + 1
            if x1 <= 0 or y1 <= 0 or x0 >= n[0] or y0 >= n[1]:
                continue
            x0, y0, x1, y1 = max(x0, 0), max(y0, 0), min(x1, n[0]), min(y1, n[1])
            out[r, c] = ii[y1, x1] - ii[y0, x1] - ii[y1, x0] + ii[y0, x0] > 0
    return out


def test_hero_centre_mask_box_is_the_minkowski_sum():
    g = zo.Grid()
    box = np.array([[30.0, 6.0], [32.0, 6.0], [32.0, 7.0], [30.0, 7.0]])
    m = sp.hero_centre_mask(g, [box], HX, HY)
    cols = g.xs[m.any(axis=0)]
    rows = g.ys[m.any(axis=1)]
    assert cols.min() >= 30.0 - HX - 1e-9 and cols.max() <= 32.0 + HX + 1e-9
    assert cols.min() < 30.0 - HX + g.cell and cols.max() > 32.0 + HX - g.cell
    assert rows.min() >= 6.0 - HY - 1e-9 and rows.max() <= 7.0 + HY + 1e-9
    # a full rectangle of grid points
    assert m.sum() == len(cols) * len(rows)


@pytest.mark.parametrize("poly", [
    [[30.0, 6.0], [33.0, 7.5], [30.5, 9.0]],                              # a triangle (convex, sloped edges)
    [[30.0, 6.0], [34.0, 6.0], [34.0, 9.0], [33.0, 9.0], [33.0, 7.0], [30.0, 7.0]],   # an L (not convex)
])
def test_hero_centre_mask_matches_a_dense_box_sampling(poly):
    g = zo.Grid()
    m = sp.hero_centre_mask(g, [np.asarray(poly)], HX, HY)
    ref = _brute(g, poly, HX, HY)
    # the raster differs only for points within a raster step of the boundary
    assert (m ^ ref).sum() <= 0.03 * ref.sum()


def _ent(iid, tk, x, y, cols=(), state=None, fsm="Control", **kw):
    e = {"iid": iid, "type_key": tk, "pos": [x, y, 0.0], "render_aabb": [0, 0, 1, 1], "cols": list(cols),
         "fsms": [{"name": fsm, "state": state}]}
    e.update(kw)
    return e


def _col(x0, y0, x1, y1, dealt=1):
    return {"name": "c", "verts_world": [x0, y0, x1, y0, x1, y1, x0, y1], "enabled": True,
            "damage": {"dealt": dealt, "parry": 4}}


def _states():
    """Two Reeds (1 near x 30, 2 near x 40); Reed 1 throws a pin at frame 2 that flies to x 45; Reed 2 starts a stab
    at frame 3 and is hit at frame 4; a nail clash next to the hero at frame 5."""
    out = []
    for f in range(8):
        r1 = _ent(1, "Song Reed", 30.0, 6.0, [_col(29.5, 5.0, 30.5, 7.0)], state="Alert")
        st2 = "Alert" if f < 3 else "Stab Antic" if f < 6 else "Stab 1"
        r2 = _ent(2, "Song Reed", 40.0, 6.0, [_col(39.5, 5.0, 40.5, 7.0)], state=st2)
        ents = [r1, r2]
        if f >= 2:
            px = 30.5 + 3.0 * (f - 2)
            ents.append(_ent(-9, "Song Reed Pin Projectile", px, 7.0, [_col(px - 1.0, 6.8, px + 1.0, 7.2)],
                             state="Fly", fsm="Javelin Control"))
        ev = []
        if f == 4:
            ev.append({"k": "hit", "d": {"ent": 2, "dealt": 9}})
        if f == 5:
            ev.append({"k": "freeze", "d": {"phase": "start", "type": "NailClashEffect"}})
        out.append({"f": f, "_f_raw": 100 + f, "ents": ents, "ev": ev,
                    "hero": {"box": [38.0, 4.0, 38.5, 6.08]}})
    return out


def test_truth_pins_go_to_their_thrower_and_interruptions():
    t = sp.Truth(_states())
    assert t.thrower[-9] == 1                         # armed next to Reed 1 at frame 2
    assert len(t.polys[3][1]) == 2 and len(t.polys[3][2]) == 1   # Reed 1: its body + its pin
    assert t.interrupted(2, 2, 3) == []
    assert t.interrupted(2, 3, 4) == ["hit"]
    assert "clash" in t.interrupted(2, 4, 5)          # Reed 2 is 1.8 u from the hero at the clash
    assert "clash" not in t.interrupted(1, 4, 5)      # Reed 1 is 8 u away
    assert t.started(2, 1, 4, {"Stab Antic"}) == "Stab Antic"
    assert t.started(2, 3, 6, {"Stab Antic"}) is None   # already in it at frame 3
    assert t.started(1, 0, 7, {"Stab Antic"}) is None


def test_truth_reference_window_and_strict():
    g = zo.Grid()
    t = sp.Truth(_states())
    R, Rs = t.reference(g, 4, 1)
    assert Rs.any() and not (Rs & ~R).any()           # the strict frame is inside the window
    # the pin moves 3 u a frame: the window holds frames 3..5, the strict one only 4
    assert R.sum() > Rs.sum() * 1.5
    R0, Rs0 = t.reference(g, 4, 99)
    assert not R0.any() and not Rs0.any()


def test_layer_stats_sides_by_facing():
    g = zo.Grid()
    R = np.zeros(g.shape, bool)
    R[10:20, 50:60] = True
    P = R.copy()
    P[10:20, 60:72] = True                            # 12 cells further right
    P[25:28, 50:60] = True                            # above
    st = sp.layer_stats(P, R, R, 1, (50, 59, 10, 19), g.cell)
    d = dict(zip(sp.STAT, st))
    assert d["P"] == P.sum() and d["I"] == R.sum()
    assert d["xf"] == 120 and d["xb"] == 0 and d["xu"] == 30 and d["xd"] == 0
    assert d["ef"] == pytest.approx(12 * g.cell) and d["eu"] == pytest.approx(8 * g.cell)
    st = sp.layer_stats(P, R, R, -1, (50, 59, 10, 19), g.cell)   # facing left: the right side is behind
    d = dict(zip(sp.STAT, st))
    assert d["xb"] == 120 and d["xf"] == 0 and d["eb"] == pytest.approx(12 * g.cell)


def _row(f, P, R, lay="committed", intr=(), Rns=None, k="12"):
    st = [P, min(P, R), min(P, R), P - min(P, R), 0, 0, 0, 0, 1.0, 0.0, 0.0, 0.0]
    ent = {"R": R, "Rs": R, "in": list(intr), "kinds": ["com_fine"], "aim": False,
           "L": {lay: st, "total": st}}
    if Rns is not None:
        ent["Rns"] = Rns
    return {"f": f, "iid": 1, "name": "Reed 1", "type": "Song Reed", "fam": "RE_STAB", "state": "Stab 1",
            "tis": 0.1, "com": True, "facing": 1, "k": {k: ent}}


def test_summary_applies_the_persons_rule(tmp_path):
    rows = [_row(1, 100, 80, "com_all"), _row(2, 100, 10, "com_all"), _row(3, 50, 0, "com_all"),
            _row(4, 50, 0, "com_all", intr=["hit"]), _row(5, 100, 50, "com_all")]
    (tmp_path / "20261009_085824_a0.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows), "utf-8")
    res = sp.summarize([tmp_path], ks=(12,))
    c = res["k"]["12"]["com_all"]
    # 100/80 = 1.25 ok; 100/10 error; empty reference error; interrupted apart; 100/50 = 2.0 error
    assert c["population"] == 4 and c["errors"] == 3 and c["false_alarms"] == 1 and c["interrupted"] == 1
    assert c["ratio"]["max"] == 10.0
    assert c["causes"][0]["group"].startswith("Reed|RE_STAB|Stab 1|com_fine")
    assert res["k"]["12"]["recall"]["rows"] == 3                 # rows 3 / 4 have no reference
    assert res["k"]["12"]["recall"]["rows_full_pct"] == 100.0
    assert res["worst"][0][2] == 2 and res["worst_ns"] == []                  # the largest excess area


def test_not_started_reference_is_the_attack_that_started():
    e = _row(1, 40, 30, lay="not_started", Rns=0)["k"]["12"]
    assert sp.judge(e, "not_started")[2] is None and sp.judge(e, "not_started")[3]   # nothing started: false alarm
    e = _row(1, 40, 30, lay="not_started", Rns=30)["k"]["12"]
    assert sp.judge(e, "not_started")[2] == pytest.approx(40 / 30) and not sp.judge(e, "not_started")[3]


def test_spec_of_row_files():
    assert sp._spec_of("20261009_085824_a0", "R") == "C:/ssbot/data/human/20261009_085824:win:0"
    assert sp._spec_of("20261008_211754_Forum_W_eval_planner_oracle_clashM_i3_ep2", "R").endswith(
        "20261008_211754_Forum_W_eval_planner_oracle_clashM#i3ep2")


def test_hurts_takes_the_multi_hit_colliders_and_not_the_hit_back_bell():
    whip = {"enabled": True, "damage": {"dealt": 0, "eff": 2}}
    assert zo.hurts({"enabled": True, "damage": {"dealt": 1, "eff": 1}}, 0)
    assert zo.hurts(whip, 8 | 2)                                  # multi_wounder src bit: the whip, ParrySlash Hit
    assert not zo.hurts(whip, 2)                                  # dealt 0 without the bit
    assert not zo.hurts({"enabled": True, "damage": {"dealt": 0, "eff": 0}}, 8)   # a hit-back bell: eff 0
    assert not zo.hurts(dict(whip, enabled=False), 8)
    c = dict(_col(31.0, 5.0, 36.0, 6.0, dealt=0), damage={"dealt": 0, "eff": 2, "parry": 4})
    s = {"ents": [_ent(5, "Song Pilgrim 03", 30.0, 6.0, [c], src=8)]}
    assert len(zo.damage_colliders(s)) == 1
    s["ents"][0]["src"] = 2
    assert zo.damage_colliders(s) == []


def _two_reed_states(first_thrower_state="Throw", n=12):
    """Two Reeds 6 u apart; a pin appears at frame 2 next to Reed 2 (x 40) while Reed 1 (x 34) is in a throw state;
    the pin is unarmed at frames 6-7 and re-armed at frame 8 while Reed 2 throws."""
    out = []
    for f in range(n):
        st1 = first_thrower_state if f <= 2 else "Alert"
        st2 = "Throw" if 7 <= f <= 8 else "Alert"
        ents = [_ent(1, "Song Reed", 34.0, 6.0, [_col(33.5, 5.0, 34.5, 7.0)], state=st1),
                _ent(2, "Song Reed", 40.0, 6.0, [_col(39.5, 5.0, 40.5, 7.0)], state=st2)]
        if f >= 2:
            armed = not (6 <= f <= 7)
            ents.append(_ent(-9, "Song Reed Pin Projectile", 39.0, 7.0,
                             [_col(38.0, 6.8, 40.0, 7.2, dealt=1 if armed else 0)], state="Fly",
                             fsm="Javelin Control"))
        out.append({"f": f, "_f_raw": 100 + f, "ents": ents, "ev": [], "dt": 1 / 60,
                    "hero": {"box": [20.0, 4.0, 20.5, 6.08]}})
    return out


def test_thrower_by_throw_state_and_owner_as_of_the_frame():
    t = sp.Truth(_two_reed_states())
    # nearest is Reed 2, but Reed 1 was throwing: the pin is Reed 1's until it re-arms at frame 8 (Reed 2 throwing)
    assert t.owner(-9, 3) == 1 and t.owner(-9, 7) == 1 and t.owner(-9, 8) == 2 and t.owner(-9) == 2
    assert len(t.polys[3][1]) == 2 and len(t.polys[7][1]) == 1 and len(t.polys[9][2]) == 2
    assert t.assign_how["throw"] == 2
    t2 = sp.Truth(_two_reed_states("Alert"))
    assert t2.owner(-9, 3) == 2 and t2.assign_how["nearest"] == 1   # nobody threw: the nearest


def test_look_ahead_by_game_time_skips_a_hit_stop():
    st = _two_reed_states(n=30)
    for s in st[5:10]:
        s["dt"] = 0.0                                         # a 5-frame freeze
    t = sp.Truth(st)
    assert t.at(2, 0) == 2 and t.at(12, 6) == 18
    assert t.at(2, 6) == 13                                   # 6 frames of game time after 2: 5 frozen ones skipped


def test_ns_any_is_judged_against_any_real_damage():
    e = _row(1, 40, 30, lay="not_started", Rns=0)["k"]["12"]
    e["L"]["ns_any"] = e["L"]["not_started"]
    assert sp.judge(e, "not_started")[3]                       # nothing started: a false alarm by the start rule
    assert sp.judge(e, "ns_any")[2] == pytest.approx(40 / 30) and not sp.judge(e, "ns_any")[3]


def test_hindsight_counts_own_and_all_owners_apart_from_hits(tmp_path):
    rows = []
    for f, own, al, intr, ha in ((1, 10, 10, [], None), (2, 6, 10, [], None), (3, 2, 4, [], None),
                                 (4, 0, 0, ["hit"], None), (5, 0, 10, [], 3)):
        r = _row(f, 50, 10)
        ent = r["k"]["12"]
        ent["L"]["total"] = list(ent["L"]["total"])
        ent["L"]["total"][2] = own
        ent["Ia"] = al
        ent["in"] = intr
        if ha is not None:
            r["hit_ago"] = ha
        rows.append(r)
    rows.append(dict(_row(6, 50, 10), iid=sp.UNATTR, name=sp.UNATTR, type=sp.UNATTR))
    (tmp_path / "x_a0.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows), "utf-8")
    res = sp.hindsight([tmp_path])
    a = res["k"]["12"]["ALL"]
    assert a["clean"]["rows"] == 3 and a["hit"]["rows"] == 2
    assert a["clean"]["own_full_pct"] == pytest.approx(100 / 3, abs=1e-2)
    assert a["clean"]["all_full_pct"] == pytest.approx(200 / 3, abs=1e-2)
    assert res["k"]["12"]["families"]["Reed/RE_STAB"]["clean"]["rows"] == 3
    assert res["misses_clean_n"] == 1 and res["misses_clean"][0][2] == 3


def test_summary_reports_unattributed_support_apart(tmp_path):
    rows = [_row(1, 100, 80, "com_all"), dict(_row(2, 30, 0, "com_all"), iid=sp.UNATTR, name=sp.UNATTR,
                                               type=sp.UNATTR)]
    (tmp_path / "20261009_085824_a0.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows), "utf-8")
    res = sp.summarize([tmp_path], ks=(12,))
    assert res["k"]["12"]["com_all"]["population"] == 1
    u = res["unattributed"]["12"]
    assert u["frames"] == 1 and u["false_alarms"] == 1 and u["errors"] == 1

"""Task 1v1 SP12b: SSBOT_FORUM_TWO_RT2 (combat.rune_pogo RtCfg v2 + two_play; default off) - every jump cast of either
Clapper: the pass under the caster to behind its landing first (the escape casts too), the pogo on B the fallback; the
small-rune bombs in the plans; the run ends behind the landing and L2 holds the caster (its rune hold); B leaving /
slamming ends a pogo run; far casts in the Clawline band optionally to claw_chase."""
import importlib

import numpy as np
import pytest

from ssbot.combat import claw_chase as cc
from ssbot.combat import rune_pogo as rp
from ssbot.combat import slam_play as sp
from ssbot.combat import two_play as tp
from tests.test_sp11a import P, _antic_states, _run, _sim
from tests.test_sp9b import WALL_X, fstate


@pytest.fixture
def rt2(monkeypatch):
    for k in ("ESC", "RUNETIER", "ANY", "ESC_SWITCH", "RT2"):
        monkeypatch.setattr(tp, k, True)
    monkeypatch.setattr(tp, "ESC_CORNER", False)
    monkeypatch.setattr(tp, "ESC_FALLBACK", False)
    monkeypatch.setenv("SSBOT_FORUM_TWO_RUNETIER_SET", "v2=1")
    yield


def test_default_off(monkeypatch):
    monkeypatch.delenv("SSBOT_FORUM_TWO_RT2", raising=False)
    monkeypatch.delenv("SSBOT_FORUM_TWO_RUNETIER", raising=False)
    try:
        for v2 in ("0", "1"):
            monkeypatch.setenv("SSBOT_FORUM_V2", v2)
            m = importlib.reload(tp)
            assert not m.RT2 and not m.RUNETIER and m.TwoPlay().rt is None
        assert importlib.reload(rp)._cfg().v2 == 0
        monkeypatch.setenv("SSBOT_FORUM_TWO_RT2", "1")
        r = importlib.reload(rp)
        m = importlib.reload(tp)
        assert m.RT2 and m.RUNETIER and m.ESC and m.TwoPlay().rt.cfg.v2 == 1 and r._cfg().v2 == 1
    finally:
        monkeypatch.delenv("SSBOT_FORUM_V2", raising=False)
        monkeypatch.delenv("SSBOT_FORUM_TWO_RT2", raising=False)
        importlib.reload(rp)
        importlib.reload(tp)


def test_bomb_hits_geometry():
    ro = type("R", (), {})()
    # her box standing at x 30 (bottom 3.015) for 4 frames, then 4 frames 3.3 u up (bomb top 2.83 + 0.15)
    box = [[29.77, 3.015, 30.23, 4.3]] * 4 + [[29.77, 6.315, 30.23, 7.6]] * 4
    ro.box = np.array([box])
    bk = np.array([[7, 31.5, 3.015 + 2.83 - 2.166, 2.166, 1, 6]])     # a ring-1 bomb lit at k 1..6 (top 2.83 u up)
    h = rp.bomb_hits(ro, bk, 0, 0.15)[0].tolist()
    assert h == [False, True, True, True, False, False, False, False]
    bk2 = bk.copy()
    bk2[0, 1] = 35.0                                                      # 4.77 u from her centre: out of reach
    assert not rp.bomb_hits(ro, bk2, 0, 0.15).any()


def test_p_need_and_room_behind():
    run = rp.RtRun(iid=7, other=99, f_a=0, k_a=0, x0=WALL_X, face=1, back0=WALL_X - tp.WALL_L, rel0=4.0, db0=20.0,
                   b_st0="Idle")
    pg = rp.RunePogo()
    p = pg.p_need(run)
    L = rp.landing(WALL_X, WALL_X + p, 1)
    assert rp.room_behind(L, 1) >= pg.cfg.pass_room
    L0 = rp.landing(WALL_X, WALL_X + max(p - 0.5, 0.0), 1)
    assert p == 0.0 or rp.room_behind(L0, 1) < pg.cfg.pass_room + 0.5
    assert rp.room_behind(30.0, -1) == pytest.approx(tp.WALL_R - 30.0)


def test_v2_escape_cast_starts_with_b_near_and_lures(rt2):
    two = tp.TwoPlay()
    assert two.rt.cfg.v2 == 1
    # B only 6.3 u in front of F, she 2 u (v1: "b near", no run): v2 takes it
    _run(two, _antic_states(b_x=WALL_X + 6.3, x_rel=2.0))
    assert two.esc is not None and two.esc.mode == "pogo" and two.rt.run is not None
    # B far (30 u): the antic stance is B's face (p_spot >= p_need + lure_m)
    two = tp.TwoPlay()
    out = _run(two, _antic_states(b_x=WALL_X + 25.0))
    run = two.rt.run
    spot, slash = two.rt._go_v2(run, next(e for e in _antic_states(b_x=WALL_X + 25.0)[1]["ents"] if e["iid"] == 99),
                                WALL_X + 25.0 - 3.0)
    assert spot == pytest.approx(WALL_X + 22.0) and out[-1] & tp.M_R
    # B near its own wall (its back 5 u < b_wall): no slash on it
    bx = tp.WALL_R - 5.0
    run.face = 1
    _spot, slash = two.rt._go_v2(run, {"pos": [bx, 7.45], "iid": 99}, bx - 3.0)
    assert slash == 0


def test_v2_behind_f_keeps_the_default_switch(rt2):
    two = tp.TwoPlay()
    _run(two, _antic_states(b_x=WALL_X + 25.0, x_rel=-1.0))           # she is behind F at its antic
    assert two.esc is not None and two.esc.mode == "switch" and two.rt.run is None
    assert two.esc_n["rt2_behind"] == 1


def test_v1_unchanged_without_v2(monkeypatch):
    for k in ("ESC", "RUNETIER", "ANY", "ESC_SWITCH"):
        monkeypatch.setattr(tp, k, True)
    monkeypatch.setattr(tp, "RT2", False)
    monkeypatch.setattr(tp, "ESC_FALLBACK", False)
    monkeypatch.delenv("SSBOT_FORUM_TWO_RUNETIER_SET", raising=False)
    two = tp.TwoPlay()
    assert two.rt.cfg.v2 == 0
    _run(two, _antic_states(b_x=WALL_X + 6.3, x_rel=2.0))
    assert two.esc.mode is None and two.esc.why == "b near" and two.rt.run is None


def _far_states(x_rel=3.0, b_x=40.0, silk=3):
    out = []
    for f, st in ((1000, "Idle"), (1001, "Cast Slam Antic")):
        s = fstate(f, "Idle", 0.5, x_rel=x_rel, b_st=st, b_x=b_x)
        s["ents"][1]["flipX"] = False                  # B faces left, toward her and F
        s["hero"]["silk"] = silk
        out.append(s)
    return out


def test_claw_handoff_in_band(rt2, monkeypatch):
    monkeypatch.setenv("SSBOT_FORUM_TWO_RUNETIER_SET", "v2=1,claw=1")
    two = tp.TwoPlay()
    # her x: F + 3 = WALL_X + 3; B at WALL_X + 14 -> 11 u from her: the band; F (behind her) not in the way
    _run(two, _far_states(x_rel=3.0, b_x=WALL_X + 14.0))
    assert two.claw_req is not None and two.claw_req[0] == 99 and two.rt.run is None
    assert two.rt.hold_after is not None and two.rt.hold_after[0] == 99
    v = two.esc_view()
    assert v["mode"] == "rt_hold" and v["hold"] == 99 and v["hold_after"]
    assert two.stats()["esc"]["rt2_claw"][0]["iid"] == 99 and two.esc_n["rt2_claw_n"] == 1
    # out of the band (B 20 u away): the pass run
    two = tp.TwoPlay()
    _run(two, _far_states(x_rel=3.0, b_x=WALL_X + 23.0))
    assert two.claw_req is None and two.rt.run is not None and two.rt.run.src == "other"
    # claw=2 alternates: the first in-band cast to the Clawline, the second to the pass
    monkeypatch.setenv("SSBOT_FORUM_TWO_RUNETIER_SET", "v2=1,claw=2")
    two = tp.TwoPlay()
    _run(two, _far_states(x_rel=3.0, b_x=WALL_X + 14.0))
    assert two.claw_req is not None
    two.rt.hold_after, two.claw_req = None, None
    ss = _far_states(x_rel=3.0, b_x=WALL_X + 14.0)
    for s in ss:
        s["f"] += 400
    _run(two, ss)
    assert two.claw_req is None and two.rt.run is not None and two.esc_n["rt2_claw_alt_pass"] == 1


def test_claw_chase_starts_only_on_request(monkeypatch):
    monkeypatch.setattr(cc, "ENABLED", True)
    monkeypatch.setattr(cc, "SCOPE", "any")
    ss = _far_states(x_rel=3.0, b_x=WALL_X + 14.0)
    c = cc.ClawChase()
    for s in ss:
        c.step(s["f"], s, True, True, s["f"] / 60.0, req=None)
    assert c.run is None
    c = cc.ClawChase()
    for s in ss:
        c.step(s["f"], s, True, True, s["f"] / 60.0, req=(99, 1001))
    assert c.run is not None and c.run.J == 99
    c = cc.ClawChase()
    for s in ss:
        c.step(s["f"], s, True, True, s["f"] / 60.0)                   # no req kwarg: the old rule
    assert c.run is not None


def test_pass_stay_plan_and_bombs():
    """Already behind the far caster's landing: the stay plan is safe and chosen; a lit bomb at her x makes standing
    bad."""
    jx, ix = 38.0, 22.0
    cfg = rp.RtCfg(v2=1)
    cfg.horizon = 100
    L = rp.landing(jx, 25.0, -1)
    hx = L + 3.6                                         # behind it (it faces left): 3.6 u
    f_L = 1000
    ctx = rp.Ctx(F0=1020, b_box=(ix - 1.34, 3.02, ix + 2.25, 6.92), b_x=ix, b_ok=True, tx=ix, face=1, L=L, f_L=f_L,
                 fface=-1, rc=rp.rune_centre(L, -1), lit=(f_L + cfg.lit0, f_L + cfg.lit1), a_frame=f_L - 53,
                 a_seen=True, ground=True, atk_ready_f=1020, pass_x=3.25,
                 f_box=(L - 2.25, 3.02, L + 1.34, 6.92))
    pl = rp.Planner(_sim(hx), ctx, cfg)
    q = pl.best_pass(hx)
    assert q is not None and q.bad is None and q.dirk == 0 and q.why == "pass stay"
    bk = np.array([[7, hx, 3.015 + 0.66, 2.166, 30, 36]])
    ctx.bombs = bk
    st = rp.Plan("pass", 0, 1020, 1020, why="pass stay")
    pl.evaluate([st])
    assert st.bad is not None and 1020 + 28 <= st.bad <= 1020 + 36


def test_update_ends_behind_and_holds_the_caster(rt2):
    pg = rp.RunePogo()
    F = {"iid": 7, "pos": [WALL_X + 3.0, 7.45], "flipX": True, "fsms": [{"name": "Control", "state": "Cast Slam Antic",
                                                                         "t": 0.0}]}
    B = {"iid": 99, "pos": [WALL_X + 25.0, 7.45], "flipX": False, "fsms": [{"name": "Control", "state": "Idle",
                                                                             "t": 0.0}]}
    s = fstate(1001, "Cast Slam Antic", 0.0, x_rel=8.0, b_x=WALL_X + 25.0)
    pg.start(1001, s, F, B, WALL_X + 8.0, 7, 0.0)
    r = pg.run
    r.f_aim, r.f_land, r.x_land, r.L_pred, r.phase = 1056, 1109, WALL_X + 3.0, WALL_X + 3.0, "air"
    pg.plan = rp.Plan("pass", 0, 0, 0)
    # 10 frames after the landing (its hammer on), 3.5 u behind it: still running
    s2 = fstate(1119, "Slam Recover", 0.1, hx=WALL_X - 0.5, b_x=WALL_X + 25.0)
    s2["ents"][0]["pos"][0] = WALL_X + 3.0
    pg.update(1119, s2, WALL_X - 0.5, 7)
    assert pg.run is not None
    s3 = fstate(1124, "Slam Recover", 0.2, hx=WALL_X - 0.5, b_x=WALL_X + 25.0)
    s3["ents"][0]["pos"][0] = WALL_X + 3.0
    pg.update(1124, s3, WALL_X - 0.5, 7)
    assert pg.run is None and pg.done[-1].end == "behind"
    assert pg.hold_after is not None and pg.hold_after[0] == 7 and pg.hold_after[1] >= 1109 + 84


def test_update_ends_when_b_leaves(rt2):
    pg = rp.RunePogo()
    F = {"iid": 7, "pos": [WALL_X, 7.45], "flipX": True, "fsms": [{"name": "Control", "state": "Cast Slam Antic",
                                                                   "t": 0.0}]}
    B = {"iid": 99, "pos": [WALL_X + 20.0, 7.45], "flipX": False, "fsms": [{"name": "Control", "state": "Idle",
                                                                            "t": 0.0}]}
    s = fstate(1001, "Cast Slam Antic", 0.0, x_rel=17.0, b_x=WALL_X + 20.0)
    pg.start(1001, s, F, B, WALL_X + 17.0, 7, 0.0)
    r = pg.run
    r.f_aim, r.f_land, r.x_land, r.phase = 1056, 1109, WALL_X + 10.0, "air"
    pg.plan = rp.Plan("keep", 0, 0, 0)
    # B evaded 9 u away, the circle due at L + 64 (35 frames away < leave_f): kept
    s2 = fstate(1138, "Idle", 0.3, hx=WALL_X + 17.0, b_x=WALL_X + 26.0, b_st="Evade Scuttle")
    s2["ents"][0]["pos"][0] = WALL_X + 10.0
    pg.update(1138, s2, WALL_X + 17.0, 7)
    assert pg.run is not None
    pg2 = rp.RunePogo()
    pg2.start(1001, s, F, B, WALL_X + 17.0, 7, 0.0)
    pg2.run.f_aim, pg2.run.f_land, pg2.run.x_land, pg2.run.phase = 1056, 1109, WALL_X + 10.0, "air"
    pg2.plan = rp.Plan("keep", 0, 0, 0)
    s3 = fstate(1115, "Idle", 0.3, hx=WALL_X + 17.0, b_x=WALL_X + 26.0, b_st="Evade Scuttle")
    s3["ents"][0]["pos"][0] = WALL_X + 10.0
    pg2.update(1115, s3, WALL_X + 17.0, 7)
    assert pg2.run is None and pg2.done[-1].end == "b left"
    # a pass plan is not ended by B leaving
    pg3 = rp.RunePogo()
    pg3.start(1001, s, F, B, WALL_X + 17.0, 7, 0.0)
    pg3.run.f_aim, pg3.run.f_land, pg3.run.x_land, pg3.run.phase = 1056, 1109, WALL_X + 10.0, "air"
    pg3.plan = rp.Plan("pass", tp.M_L, 0, 30)
    pg3.update(1115, s3, WALL_X + 17.0, 7)
    assert pg3.run is not None


def test_b_slam_at_start_is_modelled(rt2):
    pg = rp.RunePogo()
    F = {"iid": 7, "pos": [WALL_X, 7.45], "flipX": True, "fsms": [{"name": "Control", "state": "Cast Slam Antic",
                                                                   "t": 0.0}]}
    B = {"iid": 99, "pos": [WALL_X + 20.0, 7.45], "flipX": False, "fsms": [{"name": "Control", "state": "Slam Antic",
                                                                            "t": 0.25}]}
    s = fstate(1001, "Cast Slam Antic", 0.0, x_rel=10.0, b_x=WALL_X + 20.0)
    pg.start(1001, s, F, B, WALL_X + 10.0, 7, 0.0)
    assert pg._b_slam_f0 == 1001 - 15


def test_iframe_preference(rt2):
    """In the float above B near the lit: a safe down slash whose contact falls in lit0 - 3 .. lit0 is chosen."""
    bx, L = 30.0, 21.0
    cfg = rp.RtCfg(v2=1)
    f_L = 1000
    lit0 = f_L + 65
    F0 = lit0 - 9
    ctx = rp.Ctx(F0=F0, b_box=(bx - 2.25, 3.02, bx + 1.34, 6.92), b_x=bx, b_ok=True, tx=bx, face=1, L=L, f_L=f_L,
                 fface=1, rc=rp.rune_centre(L, 1), lit=(f_L + cfg.lit0, f_L + cfg.lit1), a_frame=f_L - 53, a_seen=True,
                 ground=False, atk_ready_f=F0, gliding=True, lit_pred=lit0)
    pl = rp.Planner(_sim(bx - 0.3, ground=False, vy=-1.0, y=11.5), ctx, cfg)
    q = pl.best_air(bx - 0.3)
    if q.kind == "drop" and q.contact is not None and q.bad is None:
        assert lit0 - cfg.iframe_lo <= q.contact <= lit0


@pytest.mark.parametrize("bx", [WALL_X + 17.0, WALL_X + 12.0])
def test_closed_loop_escape_pass_from_b_face(bx):
    """v2 on the hero model, re-planned every frame from F's aim - 2: from B's face (p = B - 3) under F's flight to
    behind its landing - no F flight body / landing hammer / dome / B body contact; she ends >= 2.9 u behind it."""
    from ssbot.combat.air_chain import ChainSim
    from ssbot.knowledge import kinematics as kin
    from ssbot.knowledge.kinematics import HoldState
    from tests.test_sp11a import TERR
    x0 = WALL_X
    hx = bx - 3.0
    cfg = rp.RtCfg(v2=1)
    a_frame = 1002
    f_L = a_frame + cfg.land_f
    bbox = (bx - 2.25, 3.02, bx + 1.34, 6.92)
    state = kin.initial_state(P, hx, 4.568, facing=1, ground=True)
    hold = HoldState.idle(1)
    ctl = rp.RunePogo()
    ctl.cfg = cfg
    L = rp.landing(x0, hx, 1)
    rc = rp.rune_centre(L, 1)
    assert rp.room_behind(L, 1) >= cfg.pass_room
    ground, x_now, dangers, kinds, trace = True, hx, [], [], []
    for frame in range(1000, 1000 + 150):
        sim = ChainSim(state, np.zeros(0, np.int64), hold, P, TERR, frame - 1, frame - 2)
        seen = frame > a_frame
        Lc = L if seen else rp.landing(x0, x_now, 1)
        landed = frame >= f_L
        ctx = rp.Ctx(F0=frame, b_box=bbox, b_x=bx, b_ok=True, tx=Lc - cfg.pass_x, face=1, L=Lc, f_L=f_L, fface=1,
                     rc=rp.rune_centre(Lc, 1), lit=(f_L + cfg.lit0, f_L + cfg.lit1), a_frame=a_frame, a_seen=seen,
                     ground=ground, atk_ready_f=frame, jx0=None if seen else x0, pass_x=cfg.pass_x,
                     j_box=None if seen else (x0 - 1.34, 3.02, x0 + 2.25, 6.92),
                     f_box=(L - 1.34, 3.02, L + 2.25, 6.92) if landed else None,
                     f_fall=None if landed else (a_frame, f_L, x0, Lc, 1))
        p = ctl.plan
        pl = rp.Planner(sim, ctx, cfg)
        q = pl.best_pass(x_now, prev=p) if ground else None
        if q is None:
            q = (pl.best_up(x_now, a_frame, prev=p) or pl.best_flee(x_now)) if ground else pl.best_air(x_now, None, p)
        ctl.plan = p = q
        if not kinds or kinds[-1] != q.kind:
            kinds.append(q.kind)
        m = rp.mask_at(p, frame)
        lat, hold = kin.hold_filter(np.array([m], np.int64), hold)
        ro = kin.rollout(state, lat.reshape(1, 1), P, TERR)
        state = ro.final[:, 0]
        b = [float(v) for v in ro.box[0, 1]]
        ground = bool(ro.flags[0, 1] & kin.F_GROUND)
        x_now = 0.5 * (b[0] + b[2])
        trace.append((frame - a_frame, round(x_now - L, 2), round(b[1] - 3.015, 2), q.kind, q.why))
        g = frame + 1
        rr = type("R", (), {})()
        rr.box, rr.flags = np.array(b).reshape(1, 1, 4), np.zeros((1, 1), np.int64)
        if f_L - 1 <= g <= f_L + 12 and rp.hammer_hits(rr, L, 1, 0.0)[0, 0]:
            dangers.append((g - f_L, "hammer"))
        if f_L + 65 <= g <= f_L + 72:
            top = float(rp.dome_top(max(b[0] - rc, rc - b[2], 0.0)))
            if top > 0 and b[1] - 3.015 < top:
                dangers.append((g - f_L, "dome"))
        if a_frame <= g <= f_L:
            k = g - a_frame
            xc = x0 + (L - x0) * min(k / 53.0, 1.0)
            y0 = float(np.interp(k * 54.0 / 53.0, np.arange(0, 66, 6), rp.FLIGHT_Y0))
            if b[0] < xc + 2.25 and b[2] > xc - 1.34 and b[1] < 3.015 + y0 + 3.8 and b[3] > 3.015 + y0:
                dangers.append((g - f_L, "flight"))
        if landed and b[0] < L + 2.25 and b[2] > L - 1.34 and b[1] < 6.92:
            dangers.append((g - f_L, "F body"))
        if b[0] < bbox[2] and b[2] > bbox[0] and b[1] < bbox[3] and b[3] > bbox[1]:
            dangers.append((g - f_L, "B body"))
    assert "pass" in kinds
    assert dangers == []
    assert (x_now - L) <= -2.9


def test_front_exit_when_behind_is_blocked():
    """A far cast clamped (she 20 u from it): behind its landing is 12 u away under its flight past a body, the far
    edge ~6 u ahead - the front plan is safe and chosen."""
    jx, hx = 20.0, 40.0
    cfg = rp.RtCfg(v2=1)
    cfg.horizon = 140
    a_frame, F0 = 1003, 1000
    f_L = a_frame + 53
    # a Clapper body between her and the landing's back side (the pass is blocked)
    ix = 34.0
    ctx = rp.Ctx(F0=F0, b_box=(ix - 1.34, 3.02, ix + 2.25, 6.92), b_x=ix, b_ok=False, tx=ix, face=1, L=None, f_L=f_L,
                 fface=1, rc=None, lit=(f_L + cfg.lit0, f_L + cfg.lit1), a_frame=a_frame, ground=True,
                 atk_ready_f=F0, f_fall=(a_frame, f_L, jx, rp.landing(jx, hx, 1), 1), jx0=jx,
                 j_box=(jx - 1.34, 3.02, jx + 2.25, 6.92), pass_x=3.25)
    pl = rp.Planner(_sim(hx), ctx, cfg)
    q = pl.best_pass(hx)
    assert q is not None and q.why.startswith("front") and q.bad is None
    pl.evaluate([q])
    L = float(pl.last_Ls[0])
    xe = float(pl.last_ro.centre[0, -1, 0])
    assert (xe - rp.rune_centre(L, 1)) >= rp.RUNE_R + 0.25 + 0.5
    cfg.front = 0
    assert rp.Planner(_sim(hx), ctx, cfg).best_pass(hx) is None


def test_hold_view_blocks_hits_and_the_chase(rt2):
    two = tp.TwoPlay()
    two.rt.hold_after = (7, 1200)
    two._f_now = 1100
    v = two.esc_view()
    assert v["mode"] == "rt_hold" and v["no_hit"] == frozenset({7})
    assert two.rt_hold_block(1100) == "rt hold" and two.rt_hold_block(1201) is None
    two._f_now = 1201
    assert two.esc_view() is None and two.rt.hold_after is None


def test_far_cast_waits_for_the_focus_slam(rt2):
    """The far one jump-casts while her focus (F) slams: no run then; once F's slam is in its recovery and the caster
    still in its antic, the run starts (src other, its aim from the antic entry)."""
    def st(f, f_state, b_state, tin=0.0):
        s = fstate(f, f_state, tin, x_rel=3.0, b_st=b_state, b_x=WALL_X + 20.0)
        s["ents"][1]["flipX"] = False
        s["ents"][1]["fsms"][0]["t"] = (f - 1001) / 60.0 if b_state.startswith("Cast") else 0.1
        return s
    two = tp.TwoPlay()
    _run(two, [st(1000, "Slam Antic", "Idle", 0.3), st(1001, "Slam Antic", "Cast Slam Antic", 0.32)])
    assert two.rt.run is None and two._rt_pend is not None and two.esc_n["rt2_pend"] == 1
    _run(two, [st(1015, "Slam 1", "Cast Slam Antic")])
    assert two.rt.run is None and two._rt_pend is not None
    _run(two, [st(1025, "Slam Recover", "Cast Slam Antic")])
    assert two.rt.run is not None and two.rt.run.src == "other" and two.rt.run.a_pred == 1001 + 55
    assert two.esc_n["rt2_pend_start"] == 1


def test_escape_cast_with_b_slamming_starts_and_models_its_hammer(rt2):
    two = tp.TwoPlay()
    ss = _antic_states(b_x=WALL_X + 22.0, b_st="Slam Antic")
    for s in ss:
        s["ents"][1]["fsms"][0]["t"] = 0.3
    _run(two, ss)
    assert two.esc is not None and two.esc.mode == "pogo" and two.rt.run is not None
    assert two.rt._b_slam_f0 is not None and two.rt.run.phase == "air"

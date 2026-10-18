"""Task 1v1 SP11a: SSBOT_FORUM_TWO_RUNETIER (combat.rune_pogo + two_play mode "pogo"; default off) - the person's big-rune
sequence on the focus's escape jump cast: B's face and its slashes through F's lock, the hero model's altitude plans
(a pogo on B's head, the umbrella) against F's landing hammer, its circle's dome, B's body / hammer; "far" hands back;
TWO_ESC_FALLBACK's corner takes the casts the tier does not."""
import importlib

import numpy as np
import pytest

from ssbot.combat import rune_pogo as rp
from ssbot.combat import slam_play as sp
from ssbot.combat import two_play as tp
from ssbot.combat.air_chain import ChainSim
from ssbot.knowledge import kinematics as kin
from ssbot.knowledge.kinematics import HeroParams, HoldState, Terrain2D
from tests.test_sp9b import WALL_X, fstate

P = HeroParams.load(kin.REPO / "knowledge/1.0.30000/kinematics/hero_wanderer_forum.json")
TERR = Terrain2D.from_boxes([(-200.0, 3.015 - 10.0, 260.0, 3.015), (0.0, 0.0, 14.01, 40.0), (48.99, 0.0, 70.0, 40.0)])


@pytest.fixture
def tier(monkeypatch):
    for k in ("ESC", "RUNETIER", "ANY", "ESC_SWITCH"):
        monkeypatch.setattr(tp, k, True)
    monkeypatch.setattr(tp, "ESC_CORNER", False)
    monkeypatch.setattr(tp, "ESC_FALLBACK", False)
    yield


def test_default_off(monkeypatch):
    monkeypatch.delenv("SSBOT_FORUM_TWO_RUNETIER", raising=False)
    try:
        for v2 in ("0", "1"):
            monkeypatch.setenv("SSBOT_FORUM_V2", v2)
            m = importlib.reload(tp)
            assert not m.RUNETIER
            assert m.TwoPlay().rt is None
        monkeypatch.setenv("SSBOT_FORUM_TWO_RUNETIER", "1")
        m = importlib.reload(tp)
        assert m.RUNETIER and m.ESC and m.TwoPlay().rt is not None
    finally:
        monkeypatch.delenv("SSBOT_FORUM_V2", raising=False)
        monkeypatch.delenv("SSBOT_FORUM_TWO_RUNETIER", raising=False)
        importlib.reload(tp)


def test_cfg_overrides(monkeypatch):
    monkeypatch.setenv("SSBOT_FORUM_TWO_RUNETIER_SET", "spot=2.8,slash=0")
    c = rp._cfg()
    assert c.spot == pytest.approx(2.8) and c.slash == 0
    monkeypatch.setenv("SSBOT_FORUM_TWO_RUNETIER_SET", "nope=1")
    with pytest.raises(KeyError):
        rp._cfg()


def test_plan_masks_frame_by_frame():
    p = rp.Plan("drop", rp.M_R, 100, 108, press=110, hold_j=True, umb=125)
    full = rp.plan_cmds(p, 100, 40)
    assert [rp.mask_at(p, 100 + i) for i in range(40)] == [int(x) for x in full]
    assert full[0] & rp.M_J and full[0] & rp.M_R and not full[8] & rp.M_R
    assert full[9] & rp.M_D and not full[9] & rp.M_A                     # down a frame before the press
    assert full[10] & rp.M_A and full[10] & rp.M_D and not full[10] & rp.M_J and full[11] & rp.M_A
    assert not any(full[11:15] & rp.M_J) and all(full[11:15] & rp.M_D) and not full[12] & rp.M_A
    assert not full[24] & rp.M_J and all(full[25:] & rp.M_J)             # the umbrella from 125, held
    q = rp.Plan("up", 0, 0, 0, jump=(102, 12), press=120)
    m = rp.plan_cmds(q, 100, 30)
    assert not m[1] & rp.M_J and all(m[2:14] & rp.M_J) and not m[14] & rp.M_J


def test_dome_and_hammer_geometry():
    assert float(rp.dome_top(0.0)) == pytest.approx(0.34 + 7.187, abs=1e-6)
    assert float(rp.dome_top(7.3)) < 0
    assert float(rp.dome_top(3.0)) == pytest.approx(0.34 + np.sqrt(7.187 ** 2 - 9.0), abs=1e-6)
    ro = type("R", (), {})()
    ro.flags = np.zeros((1, 3), np.int64)
    # her box at 4.07 u in front of the landing: under the hammer's top (6.9 u) / above it / past its end (7.76 u)
    ro.box = np.array([[[24.0 - 0.25, 3.015, 24.0 + 0.25, 5.1], [24.0 - 0.25, 10.4, 24.0 + 0.25, 12.5],
                        [28.3 - 0.25, 3.015, 28.3 + 0.25, 5.1]]])
    h = rp.hammer_hits(ro, 20.0 - 0.07, 1, 0.0)
    assert h[0].tolist() == [True, False, False]
    assert rp.rune_centre(20.0, 1) == pytest.approx(26.75) and rp.rune_centre(20.0, -1) == pytest.approx(13.52)


def _sim(x, ground=True, vy=0.0, y=4.568):
    S = kin.initial_state(P, x, y, vy=vy, facing=1, ground=ground)
    return ChainSim(S, np.zeros(0, np.int64), HoldState.idle(1), P, TERR, 999, 998)


def _ctx(F0, L, bx, a_frame, ground=True):
    cfg = rp.RtCfg()
    f_L = a_frame + cfg.land_f
    return rp.Ctx(F0=F0, b_box=(bx - 2.25, 3.02, bx + 1.34, 6.92), b_x=bx, b_ok=True, tx=bx, face=1, L=L, f_L=f_L,
                  fface=1, rc=rp.rune_centre(L, 1), lit=(f_L + cfg.lit0, f_L + cfg.lit1), a_frame=a_frame,
                  ground=ground, atk_ready_f=F0, f_fall=(a_frame, f_L, 15.5, L, 1))


def test_up_plan_pogos_b_and_floats_over_the_landing():
    """From B's face at F's aim: the jump, the down slash meeting B's box, the umbrella - no danger through F's
    landing (its hammer, its falling body)."""
    bx, x0 = 30.0, 15.5
    hx = bx - 3.0
    L = rp.landing(x0, hx, 1)
    pl = rp.Planner(_sim(hx), _ctx(1000, L, bx, 1002), rp.RtCfg())
    q = pl.best_up(hx, 1002)
    assert q is not None and q.press is not None and q.contact is not None
    assert q.press + 3 <= q.contact <= q.press + 9 and q.umb == q.contact + rp.RtCfg().umb_f
    assert q.bad is None or q.bad > 1002 + rp.RtCfg().land_f + 13      # nothing before the landing's end
    ro = pl.last_ro
    i = pl._i(1002 + rp.RtCfg().land_f)
    assert float(ro.box[0, i, 1]) - 3.015 > 7.0                         # high over the landing


def test_closed_loop_clears_the_landing_and_the_dome():
    """The controller on the hero model, re-planned every frame, the bounce only where the slash meets B: no B body /
    landing hammer / dome contact (B 14.5 u from F at its wall)."""
    x0, bx = 15.5, 30.0
    hx = bx - 3.0
    L = rp.landing(x0, hx, 1)
    cfg = rp.RtCfg()
    a_frame = 1002
    f_L = a_frame + cfg.land_f
    rc = rp.rune_centre(L, 1)
    bbox = (bx - 2.25, 3.02, bx + 1.34, 6.92)
    state = kin.initial_state(P, hx, 4.568, facing=1, ground=True)
    hold = HoldState.idle(1)
    ctl = rp.RunePogo()
    ground, gliding, x_now, last_bounce, atk_until, vy_now = True, False, hx, None, 0, 0.0
    bounces, dangers = [], []
    for frame in range(1000, 1000 + 160):
        sim = ChainSim(state, np.zeros(0, np.int64), hold, P, TERR, frame - 1, frame - 2)
        ctx = rp.Ctx(F0=frame, b_box=bbox, b_x=bx, b_ok=True, tx=bx, face=1, L=L, f_L=f_L, fface=1, rc=rc,
                     lit=(f_L + cfg.lit0, f_L + cfg.lit1), a_frame=a_frame, ground=ground,
                     atk_ready_f=max(frame, atk_until), gliding=gliding, j_held=bool(int(hold.mask()[0]) & rp.M_J),
                     rising=(not ground) and bool(int(hold.mask()[0]) & rp.M_J) and vy_now > 0.5 and not gliding
                     and (last_bounce is None or frame - last_bounce > 12),
                     f_fall=(a_frame, f_L, x0, L, 1) if frame <= f_L + 1 else None)
        p = ctl.plan
        if not ctl.committed(p, frame):
            pl = rp.Planner(sim, ctx, cfg)
            if ground:
                q = pl.best_up(x_now, a_frame, prev=p) or pl.best_flee(x_now)
            else:
                ub = None if last_bounce is None or frame - last_bounce > 30 else last_bounce + cfg.umb_f
                q = pl.best_air(x_now, ub, prev=p)
            ctl.plan = p = q
            ctl._drop_f = None
        m = rp.mask_at(p, frame)
        if p.press is not None and frame == p.press:
            ctl._drop_f, atk_until = frame, frame + 19
        lat, hold = kin.hold_filter(np.array([m], np.int64), hold)
        ev = np.zeros((1, 1), np.int64)
        if ctl._drop_f is not None and 3 <= frame + 1 - ctl._drop_f <= 9 and not ground:
            r0 = kin.rollout(state, lat.reshape(1, 1), P, TERR)
            fc = (1 if p.dirk == rp.M_R else -1) if (p.dirk and p.d0 < p.press) else 1
            if rp.slash_hits(r0, np.array([fc]), bbox, 1)[0, 1]:
                ev[0, 0] |= kin.EV_POGO
        ro = kin.rollout(state, lat.reshape(1, 1), P, TERR, events=ev)
        if ev[0, 0]:
            bounces.append(frame - f_L)
            last_bounce, ctl.plan, ctl._drop_f = frame, None, None
        state = ro.final[:, 0]
        b = [float(v) for v in ro.box[0, 1]]
        ground = bool(ro.flags[0, 1] & kin.F_GROUND)
        gliding = int(ro.mode[0, 1]) == kin.M_GLIDE
        inv = bool(ro.flags[0, 1] & kin.F_INVULN)
        x_now = 0.5 * (b[0] + b[2])
        vy_now = float(ro.vel[0, 1, 1])
        g = frame + 1
        if not inv and b[0] < bbox[2] and b[2] > bbox[0] and b[1] < bbox[3] and b[3] > bbox[1]:
            dangers.append((g - f_L, "B body"))
        rr = type("R", (), {})()
        rr.box, rr.flags = np.array(b).reshape(1, 1, 4), np.zeros((1, 1), np.int64)
        if f_L - 1 <= g <= f_L + 12 and rp.hammer_hits(rr, L, 1, 0.0)[0, 0]:
            dangers.append((g - f_L, "hammer"))
        if f_L + 65 <= g <= f_L + 72 and not inv:
            top = float(rp.dome_top(max(b[0] - rc, rc - b[2], 0.0)))
            if top > 0 and b[1] - 3.015 < top:
                dangers.append((g - f_L, "dome"))
    assert bounces and bounces[0] < 0                                   # the pogo on B before F's landing
    assert dangers == []


def _antic_states(b_st="Idle", b_x=34.0, x_rel=4.0):
    return [fstate(1000, "Idle", 0.5, x_rel=x_rel, b_st=b_st, b_x=b_x),
            fstate(1001, "Cast Slam Antic", 0.0, x_rel=x_rel, b_st=b_st, b_x=b_x)]


def _run(two, ss, focus=7):
    out = []
    for s in ss:
        two.observe(s["f"], s, s["f"] / 60.0)
        out.append(two.step(s["f"], s, sp.on_ground(s), True, focus, s["f"] / 60.0))
    return out


def test_tier_starts_on_the_escape_cast_and_holds_b(tier):
    two = tp.TwoPlay()
    out = _run(two, _antic_states())
    r = two.esc
    assert r is not None and r.mode == "pogo" and r.kind == "cast"
    assert two.rt.run is not None and two.rt.run.phase == "go" and two.rt_critical()
    v = two.esc_view()
    assert v["hold"] == 99 and v["hold_after"] and v["no_hit"] == frozenset()
    # the go phase walks toward B's face (B at 34, the spot 31): right
    assert out[-1] is not None and out[-1] & tp.M_R
    assert two.last_part == "rt"
    st = two.stats()["esc"]["rune_tier"]
    assert st[0]["tier"] == "pogo" and st[0]["db0"] == pytest.approx(34.0 - WALL_X, abs=0.01)


def test_tier_not_on_a_busy_b_and_the_fallback(tier, monkeypatch):
    two = tp.TwoPlay()
    _run(two, _antic_states(b_st="Jump Antic"))
    assert two.esc is not None and two.esc.mode is None and two.esc.why == "other jumping"
    assert two.rt.run is None and not two.rt_critical()
    monkeypatch.setattr(tp, "ESC_FALLBACK", True)
    two = tp.TwoPlay()
    _run(two, _antic_states(b_st="Jump Antic"))
    assert two.esc.mode == "corner" and two.esc_n["fallback_corner"] == 1


def test_plain_escape_jump_keeps_the_switch(tier):
    two = tp.TwoPlay()
    _run(two, [fstate(1000, "Idle", 0.5, b_x=40.0), fstate(1001, "Jump Antic", 0.0, b_x=40.0)])
    assert two.esc is not None and two.esc.mode == "switch" and two.rt.run is None


def test_go_slashes_b_in_reach(tier):
    two = tp.TwoPlay()
    # B 5.0 u in front of her (her x 4 u in front of F, nearer to it; B at F + 9.0): the side slash meets its body
    ss = _antic_states(b_x=WALL_X + 9.0)
    for s in ss:
        s["hero"]["facing"] = 1
    out = _run(two, ss)
    assert out[-1] & tp.M_A and out[-1] & tp.M_R
    assert two.rt.run.presses


def test_far_tier_hands_back(tier):
    two = tp.TwoPlay()
    ss = _antic_states(b_x=WALL_X + 30.0, x_rel=4.0)
    _run(two, ss)
    assert two.esc.mode == "pogo"
    # F's aim with her still near it: the landing short, B's face far past the circle -> far
    s = fstate(1056, "Jump", 0.0, x_rel=4.0, b_x=WALL_X + 30.0)
    two.observe(1056, s, 1056 / 60.0)
    m = two.step(1056, s, True, True, 7, 1056 / 60.0)
    assert m is None or not (m & tp.M_A)
    assert two.rt.done and two.rt.done[-1].tier == "far" and two.esc is None


def test_warm_runs():
    assert rp.warm(P) < 30.0


def test_scope_any_jump_cast_of_the_other_one(tier, monkeypatch):
    """The lead's NOTE 7: B (far, not at a wall) jump-casts while she is at F's face - the run pogos F's head."""
    def ss(x_rel):
        out = []
        for f, st in ((1000, "Idle"), (1001, "Cast Slam Antic")):
            s = fstate(f, "Idle", 0.5, x_rel=x_rel, b_st=st, b_x=40.0)
            s["ents"][1]["flipX"] = False                  # B faces left, toward her and F
            out.append(s)
        return out
    two = tp.TwoPlay()
    _run(two, ss(3.0))
    r = two.esc
    assert r is not None and r.mode == "pogo" and r.iid == 99 and r.other == 7
    run = two.rt.run
    assert run.src == "other" and run.spot_sgn == -1       # she is between them: F's face on B's side
    assert two.esc_view()["hold"] == 7 and two.esc_n["mode_pogo_other"] == 1
    two = tp.TwoPlay()
    _run(two, ss(-3.0))
    assert two.rt.run is not None and two.rt.run.spot_sgn == 1   # she is behind F (near it): that side kept
    monkeypatch.setenv("SSBOT_FORUM_TWO_RUNETIER_SET", "scope=0")
    two = tp.TwoPlay()
    _run(two, ss(3.0))
    assert two.esc is None and two.esc_n["rt_other"] == 0


def test_pass_under_the_far_caster():
    """The lead's NOTE 8: another Clapper's jump cast at her from 13 u - under its flight to 3.25 u behind its landing
    (each plan's landing from its own x at the aim), no danger to the horizon."""
    jx, hx, ix = 38.0, 25.0, 22.0
    cfg = rp.RtCfg()
    cfg.horizon = 140
    a_frame = 1053
    f_L = a_frame + 53
    ctx = rp.Ctx(F0=1000, b_box=(ix - 1.34, 3.02, ix + 2.25, 6.92), b_x=ix, b_ok=True, tx=ix, face=1, L=None, f_L=f_L,
                 fface=-1, rc=None, lit=(f_L + cfg.lit0, f_L + cfg.lit1), a_frame=a_frame, ground=True,
                 atk_ready_f=1000, f_fall=(a_frame, f_L, jx, rp.landing(jx, hx, -1), -1), jx0=jx,
                 j_box=(jx - 2.25, 3.02, jx + 1.34, 6.92), pass_x=3.25)
    pl = rp.Planner(_sim(hx), ctx, cfg)
    q = pl.best_pass(hx)
    assert q is not None and q.kind == "pass" and q.bad is None
    pl.evaluate([q])
    L = float(pl.last_Ls[0])
    xe = float(pl.last_ro.centre[0, -1, 0])
    assert 3.0 <= (xe - L) <= 5.8                                         # behind the landing (it faces left)
    assert pl.best_pass(hx, prev=q) is not None                          # kept while safe

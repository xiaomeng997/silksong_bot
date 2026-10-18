"""Task 1v1 SP13 (forum.md 87): SSBOT_FORUM_CLAWSTRIKE - the Clawline approach to the slam strike when the playbook's
ground strike cannot reach it in time (combat.claw_strike, combat.slam_play). Off: unchanged."""
from pathlib import Path

import numpy as np
import pytest

from ssbot.combat import air_chain as ac
from ssbot.combat import claw_strike as cs
from ssbot.combat import slam_play as sp
from ssbot.knowledge import kinematics as kin
from tests.test_slam_play import state

REPO = Path(__file__).resolve().parents[2]
PARAMS = kin.HeroParams.load(REPO / "knowledge" / "1.0.30000" / "kinematics" / "hero_wanderer_forum.json")
TERR = kin.Terrain2D.from_boxes([(-200.0, cs.FLOOR - 10.0, 260.0, cs.FLOOR), (0.0, 0.0, 14.01, 40.0),
                                 (48.99, 0.0, 70.0, 40.0)])
cs.warm(PARAMS)                 # the numba paths (the plan's search stops at HARD_S: a compile inside it finds nothing)


def sim_for(hx, f=1000, ground=True, bb=0.0, vy=0.0):
    S = kin.initial_state(PARAMS, hx, cs.FLOOR + bb + cs.POS_DY, vy=vy, facing=1, ground=ground)
    return ac.ChainSim(S, np.zeros(1, np.int64), kin.HoldState.idle(1), PARAMS, TERR, f, f)


def ctx_for(hx, kb0):
    return cs.CsCtx(s_iid=7, s_x=31.0, s_y=cs.FLOOR + 4.434, s_face=-1, kb0=kb0, hero_x=hx, face=1,
                    tls=ac.timelines())


def test_defaults_off():
    assert not cs.CLAWSTRIKE
    c = cs.CsCfg()
    assert c.trigger == "reach" and c.room == 0 and c.k_last == 14


def test_claw_phase_timeline():
    # the antic's drift 1.25 u (20 -> 21.25), the stop 2.0 + 0.23 short of the body front (29.127): 5.65 u of dash
    # (5 frames at 1.167 u), control 26 + 5 frames after the press; her box bottom 1.5 - 0.261
    x_s, bb, fc = cs.claw_phase(20.0, 1.5, 0.0, 1, 29.127, 2.0, 26)
    assert abs(x_s - 26.897) < 1e-6 and abs(bb - 1.239) < 1e-3 and fc == 31
    assert cs.claw_phase(10.0, 1.5, 0.0, 1, 29.127, 2.0, 26) is None          # beyond the dash's 7 u
    x_s, bb, fc = cs.claw_phase(26.5, 2.0, -8.0, 1, 29.127, 2.0, 26)          # inside the stop: no dash
    assert x_s == 27.75 and fc == 26 and abs(bb - (2.0 - 0.261 - 0.63)) < 1e-3


def test_ctrl_sim_bounce_no_iframes():
    c = cs.ClawStrike(cs.CsCfg(), PARAMS, TERR)
    csim = c._ctrl_sim(sim_for(20.0), 26.9, 2.7, 1, 1040)
    ro = csim.roll(np.zeros((1, 12), np.int64))
    bb = ro.box[0, :, 1] - cs.FLOOR
    # the recorded bounce after a hook: +0.35 u a frame from the frame after control (DownSpikeBounce, vy 17.4)
    assert abs(bb[1] - 3.05) < 0.03 and bb[6] > bb[1] + 1.2
    assert not ((ro.flags[0] & kin.F_INVULN) != 0).any()
    # the down slash is not taken before control + 9 (the attack cooldown 0.15 s, the harpoon's recovery)
    m = np.zeros((1, 16), np.int64)
    m[0, 2:6] = kin.B_DOWN | kin.B_ATTACK
    ro = csim.roll(m)
    assert not ((ro.flags[0, :8] & kin.F_ATTACKING) != 0).any()


def test_plan_ground_small_hop_and_mask():
    hx = 31.0 - 7.5
    p = cs.ClawStrike(cs.CsCfg(), PARAMS, TERR).plan(sim_for(hx), ctx_for(hx, 2), True, True)
    assert p is not None and 3 <= p.hop <= 5 and 5 <= p.k_press <= 10 and min(p.var_ok) > 0
    assert p.bb_press <= 3.3
    ms = [cs.plan_mask(p, F, 1) for F in range(p.f0, p.f_press + 4)]
    assert all(m & cs.M_J for m in ms[:p.hop]) and not any(m & cs.M_J for m in ms[p.hop:])
    assert ms[p.f_press - 1 - p.f0] & cs.M_R and not ms[p.f_press - 1 - p.f0] & cs.M_CLAW
    assert ms[p.f_press - p.f0] == cs.M_CLAW | cs.M_R and ms[p.f_press + 1 - p.f0] == cs.M_CLAW | cs.M_R
    assert ms[p.f_press + 2 - p.f0] == 0


@pytest.mark.parametrize("hx,kb0,ground,bb", [(31.0 - 13.5, 2, True, 0.0), (31.0 - 7.5, 8, True, 0.0),
                                              (31.0 - 7.5, 2, False, 6.0)])
def test_plan_none(hx, kb0, ground, bb):
    # too far for the ray / the dash, too late in the antic, too high to fall into the ray band in time
    c = cs.ClawStrike(cs.CsCfg(), PARAMS, TERR)
    assert c.plan(sim_for(hx, ground=ground, bb=bb), ctx_for(hx, kb0), ground, True) is None


def _slam(f, k, hx, silk=3):
    s = state(f, "Slam Antic", k / 60.0, hx=hx)
    s["hero"]["silk"] = silk
    return s


def test_slamplay_takes_the_clawline_when_the_walk_does_not_fit(monkeypatch):
    monkeypatch.setattr(cs, "CLAWSTRIKE", True)
    hx = 31.0 - 9.5
    p = sp.SlamPlay(sp.PlayCfg())
    m = p.step(1000, _slam(1000, 2, hx), True, t_game=10.0, sim=sim_for(hx))
    r = p.run
    assert r.phase == "cs_pre" and r.cs is not None and m & sp.M_J and not m & cs.M_CLAW
    assert r.cs_log[0][1] == "plan" and r.cs_log[0][2] == "distance"     # why: beyond the reach band (9 u)
    # the keys to the press, then the lock (no key) while the Harpoon clip runs
    P = r.cs.f_press
    masks = {}
    for f in range(1001, P + 4):
        s = _slam(f, 2 + f - 1000, hx)
        s["hero"]["hero_accepting_input"] = f < P + 1
        if f >= P:
            s["hero"]["anim"] = {"clip": "Harpoon Antic"}
        masks[f + 2] = p.step(f, s, False, t_game=10.0 + (f - 1000) / 60.0, sim=None)
    assert masks[P] == cs.M_CLAW | sp.M_R and masks[P + 1] == cs.M_CLAW | sp.M_R and masks[P + 2] == 0
    assert r.phase == "cs_lock" and r.cs_k_press == P - 1000 + 2
    st = p.stats()
    assert st["cs_runs"] == 1 and st["cs_pressed"] == 1


def test_slamplay_off_unchanged(monkeypatch):
    hx = 31.0 - 9.5
    for on in (False, True):
        monkeypatch.setattr(cs, "CLAWSTRIKE", on)
        p = sp.SlamPlay(sp.PlayCfg())
        m = p.step(1000, _slam(1000, 2, hx, silk=0), True, t_game=10.0, sim=sim_for(hx))
        # no silk: no Clawline either way - the playbook's decline, no key, the row as before
        assert m is None and p.run.phase == "wait" and p.run.why == "distance 9.5"
        assert len(p.runs_rec()[0]) == (12 if not on else 17 + 6)
    monkeypatch.setattr(cs, "CLAWSTRIKE", False)
    p = sp.SlamPlay(sp.PlayCfg())
    assert p.step(1000, _slam(1000, 2, hx), True, t_game=10.0, sim=sim_for(hx)) is None
    assert "cs_runs" not in p.stats() and len(p.runs_rec()[0]) == 12


def test_airstrike_from_high_in_the_air(monkeypatch):
    # SP13a: 6 u up and rising slowly at antic frame 8, 6.5 u in front: no landing by K_JUMP_LATE2, no Clawline (off):
    # the air plan (air_chain.search with S as B) takes the keys on the tick after the air entry; without AIRSTRIKE the
    # run aborts 'no landing (fall)' there
    hx = 31.0 - 6.5

    def st(f, k):
        s = _slam(f, k, hx)
        s["hero"]["box"] = [hx - 0.23, cs.FLOOR + 6.0, hx + 0.23, cs.FLOOR + 8.07]
        s["hero"]["pos"] = [hx, cs.FLOOR + 6.0 + cs.POS_DY]
        s["hero"]["vel"] = [0.0, 2.0]
        return s
    for on in (False, True):
        monkeypatch.setattr(cs, "AIRSTRIKE", on)
        monkeypatch.setattr(sp, "LATE", True)
        p = sp.SlamPlay(sp.PlayCfg())
        p.step(1000, st(1000, 8), False, t_game=10.0, sim=sim_for(hx, ground=False, bb=6.0, vy=2.0))
        assert p.run.phase == "land"
        m = p.step(1001, st(1001, 9), False, t_game=10.0 + 1 / 60.0, sim=sim_for(hx, f=1001, ground=False, bb=6.0, vy=2.0))
        if not on:
            assert m is None and p.done and p.done[0].why.startswith("no landing")
            continue
        r = p.run
        assert r is not None and r.as_air and r.phase == "cs_strike" and r.cs_strike is not None
        assert 46 <= r.cs_strike.k_press <= 48 and r.cs_log[-1][1] == "as_plan"

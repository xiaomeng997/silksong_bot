"""Task 179 #315 (Sol seq 238 G1-a): SSBOT_FORUM_TWO_RETURN_BODY, a default-off local candidate, not a claim that the
second Clapper's place is better known. While L2's middle return is in force with both Clappers in Idle / Walk (no move
instance), the other one's separable idle body takes FOCUS_M in a second stack (stack_ret) that only the ordinary rows'
revocable frames read; the stack, the hazards, the dash checks and every other reader keep the original margins."""
from pathlib import Path
from types import SimpleNamespace as NS

import numpy as np
import pytest

from ssbot.combat import forum_v2 as v2
from ssbot.combat.attack_range import union
from ssbot.combat.forum_planner import ForumConfig, ForumPlanner
from ssbot.combat.planner import PlannerConfig
from ssbot.combat.tactics import gauntlet as G
from ssbot.knowledge import kinematics as kin
from tests.test_clapper_priority import change, manual, scene, step   # noqa: F401  (autouse manual-B fixture)
from tests.test_forum_planner import arena, params  # noqa: F401
from tests.test_forum_v2 import _cell_mask
from tests.test_middle_return313 import near_attack

CL = v2.CLAPPER


def _tracker(units, haz=None):
    """units: {iid: ((x, y), state, inst)}; an idle unit's estimate is its 1-cell body (core is raw, fam None) and, for
    iids in haz, that body plus a hazard cell 8 u to its left (raw = core + haz, as attack_range.estimate builds it)."""
    haz = haz or {}
    now = {iid: (CL, {"pos": p, "fsms": [{"state": st, "t": 0.0}]}, inst) for iid, (p, st, inst) in units.items()}

    def est(iid, k):
        (x, y), _, inst = units[iid]
        core = _cell_mask(x, y)
        fam = None if inst is None else "CC_SLAM"
        if iid in haz:
            h = _cell_mask(x - 8.0, y)
            return NS(raw=union([core, h]), core=core, haz=h, fam=fam)
        return NS(raw=core, core=core, haz=None, fam=fam)
    return NS(now=now, tables={CL: NS(cell=0.05)}, hero=None, T=0.0, estimate=est)


IDLE2 = {7: ((24.0, 6.0), "Idle", None), 9: ((30.0, 6.0), "Walk", None)}


def test_off_by_default_nothing_is_built_and_the_stacks_are_unchanged(monkeypatch):
    import os
    if "SSBOT_FORUM_TWO_RETURN_BODY" not in os.environ:
        assert v2.RETURN_BODY is False
    monkeypatch.setattr(v2, "RETURN_BODY", False)
    a = v2.RangeSupport.build(_tracker(IDLE2), margin_mode="focus", focus=9)
    b = v2.RangeSupport.build(_tracker(IDLE2), margin_mode="focus", focus=9, body2=7)
    assert b.body2 is None and b.stack_ret is None and not b.ret_tags
    assert np.array_equal(a.stack, b.stack) and np.array_equal(a.stack_esc, b.stack_esc)
    assert np.array_equal(a.stack_dash, b.stack_dash)


def test_on_the_other_idle_body_takes_the_focus_margin_in_stack_ret_only(monkeypatch):
    monkeypatch.setattr(v2, "RETURN_BODY", True)
    off = v2.RangeSupport.build(_tracker(IDLE2), margin_mode="focus", focus=9)
    rs = v2.RangeSupport.build(_tracker(IDLE2), margin_mode="focus", focus=9, body2=7)
    assert rs.body2 == 7 and rs.stack_ret is not None
    # the stack every other reader uses, the escape check's and the focus's dash copy are exactly the original ones
    assert np.array_equal(rs.stack, off.stack) and np.array_equal(rs.stack_esc, off.stack_esc)
    assert np.array_equal(rs.stack_dash, off.stack_dash)
    flat7 = v2.RangeSupport.build(_tracker({7: IDLE2[7]}), margin_mode="flat:0.5")
    focus9 = rs._stack_of(lambda i: i == 9)
    for si, k in enumerate(rs.samples):
        if k <= 12:                      # the rule margin is FOCUS_M there: nothing narrowed
            assert np.array_equal(rs.stack_ret[si], rs.stack[si])
        else:
            assert np.array_equal(rs.stack_ret[si], focus9[si] | flat7.stack[si])
            assert rs.stack_ret[si].sum() < rs.stack[si].sum()
    # a point 2 u beside the narrowed body at k 36: in the stack (rule 4.3 u), not in stack_ret (0.5 u)
    tk = np.array([36 * v2.FT])
    x, y = np.array([[22.0]]), np.array([[6.0]])
    assert rs.occupied(x, y, tk)[0, 0] and not rs.occupied_ret(x, y, tk)[0, 0]
    # no stack_ret: occupied_ret is occupied
    assert off.occupied_ret(x, y, tk)[0, 0] == off.occupied(x, y, tk)[0, 0]


def test_hazards_keep_their_margin_and_an_inseparable_estimate_is_not_narrowed(monkeypatch):
    monkeypatch.setattr(v2, "RETURN_BODY", True)
    monkeypatch.setattr(v2, "COMMIT", True)
    rs = v2.RangeSupport.build(_tracker(IDLE2, haz={7}), margin_mode="focus", focus=9, body2=7)
    assert rs.stack_ret is not None
    tk = np.array([36 * v2.FT])
    # around the hazard (8 u left of the body) both stacks agree; beside the body they differ
    xs, ys = np.meshgrid(np.linspace(14.5, 18.5, 17), np.linspace(4.0, 8.0, 17))
    near_haz = rs.occupied(xs.reshape(1, -1), ys.reshape(1, -1), tk)
    assert near_haz.any() and np.array_equal(near_haz, rs.occupied_ret(xs.reshape(1, -1), ys.reshape(1, -1), tk))
    x, y = np.array([[22.0]]), np.array([[6.0]])
    assert rs.occupied(x, y, tk)[0, 0] and not rs.occupied_ret(x, y, tk)[0, 0]
    # without TWO_COMMIT the body and its hazards are one raw raster: not separable, not narrowed
    monkeypatch.setattr(v2, "COMMIT", False)
    rs2 = v2.RangeSupport.build(_tracker(IDLE2, haz={7}), margin_mode="focus", focus=9, body2=7)
    assert rs2.body2 == 7 and rs2.stack_ret is None and not rs2.ret_tags


@pytest.mark.parametrize("units, focus, body2", [
    ({7: ((24.0, 6.0), "Slam Antic", NS(fam="CC_SLAM", states=["Slam Antic"])), 9: IDLE2[9]}, 9, 7),  # in a move
    ({7: ((24.0, 6.0), "After Scuttle", None), 9: IDLE2[9]}, 9, 7),           # idle family, not Idle / Walk
    ({7: IDLE2[7], 9: ((30.0, 6.0), "Close Range", None)}, 9, 7),              # the focus not in Idle / Walk
    (IDLE2, 9, 9),                                                             # the focus itself
    (IDLE2, 9, 3),                                                             # not tracked
])
def test_no_narrowing_outside_the_support_domain(monkeypatch, units, focus, body2):
    monkeypatch.setattr(v2, "RETURN_BODY", True)
    rs = v2.RangeSupport.build(_tracker(units), margin_mode="focus", focus=focus, body2=body2)
    assert rs.body2 is None and rs.stack_ret is None


def test_no_focus_no_narrowing(monkeypatch):
    monkeypatch.setattr(v2, "RETURN_BODY", True)
    rs = v2.RangeSupport.build(_tracker(IDLE2), margin_mode="rule", focus=9, body2=7)
    assert rs.focus is None and rs.body2 is None and rs.stack_ret is None


def test_ret_stack_rebuilds_the_stack_exactly_without_tags():
    rs = v2.RangeSupport.build(_tracker(IDLE2, haz={7}), margin_mode="focus", focus=9)
    rs.add(len(rs.samples) - 1, 5, np.ones((3, 3), bool), 40, 40)
    assert not rs.ret_tags and np.array_equal(rs.ret_stack(), rs.stack)


def test_the_feed_passes_the_other_one_and_never_reuses_a_narrowed_build(monkeypatch):
    calls = []

    def build(trk, **kw):
        calls.append(kw.get("body2"))
        return NS(ms=0.0, focus=kw.get("focus"), fc=None)
    monkeypatch.setattr(v2.RangeSupport, "build", staticmethod(build))
    fd = v2.V2Feed(every=3)
    fd.f_fed = 10
    fd.support(NS(fc=None), 10, focus=9, body2=7)
    fd.f_fed = 11
    fd.support(NS(fc=None), 11, focus=9, body2=7)
    assert calls == [7, 7]                       # rebuilt: the Idle / Walk state is read on the frame it is used
    fd.f_fed = 12
    fd.support(NS(fc=None), 12, focus=9)
    fd.f_fed = 13
    fd.support(NS(fc=None), 13, focus=9)
    assert calls == [7, 7, None]                 # without it, the old reuse between rebuilds


# ---- the planner: revocable frames only ----

def _rollout(N, T1, P):
    mode = np.full((N, T1), kin.M_NORMAL, np.int64)
    vel = np.zeros((N, T1, 2))
    cen = np.zeros((N, T1, 2))
    cen[..., 0] = 25.0
    flags = np.zeros((N, T1), np.int64)
    # row 1: a dash away from the other one from P + 1 for 3 frames (the current locked segment)
    mode[1, P + 1:P + 4] = kin.M_DASH
    vel[1, P + 1:P + 4, 0] = -20.0
    # row 2: a dash at the other one (x 30) later in the row: its rule check on every frame
    mode[2, P + 5] = kin.M_DASH
    vel[2, P + 5, 0] = 20.0
    return NS(mode=mode, vel=vel, centre=cen, flags=flags)


def test_planner_reads_the_narrowed_stack_after_the_sent_prefix_and_the_current_lock_only(params, arena):
    pl = ForumPlanner(params, arena, PlannerConfig(T=8, threads=1), ForumConfig())
    N, P, T1 = 5, 2, 12
    rs = NS(body2=7, trk=NS(now={7: (CL, {"pos": (30.0, 6.0)}, None)}),
            occupied_ret=lambda x, y, tk: np.ones(np.shape(x), bool))
    f = NS(rs=rs)
    r1 = _rollout(N, T1, P)
    fr = np.arange(T1)
    o = np.zeros((N, T1), bool)
    out = pl._v2_return(o, f, r1, np.zeros((N, T1)), np.zeros((N, T1)), fr * v2.FT, fr, P, N0=3, cont=True)
    le = pl.v2_ret["lock_end"]
    assert le.tolist() == [P, P + 3, -1, -1, P]          # rows 0, 1 and CONTINUE (4); 2 dashes at it, 3 is a chain row
    assert not out[0, :P + 1].any() and out[0, P + 1:].all()
    assert not out[1, :P + 4].any() and out[1, P + 4:].all()
    assert not out[2].any() and not out[3].any()
    assert pl.v2_ret["info"]["dash_kept"] == 1 and pl.v2_ret["info"]["rows"] == 3


# ---- L2: only while the return is in force and both are in Idle / Walk ----

def test_l2_names_the_other_one_only_with_the_switch_and_both_idle_or_walking(monkeypatch):
    tac, ws, fc = scene(xs=(20., 34.), hx=15.); step(tac, ws, fc)
    out = near_attack(tac, ws, fc)
    assert tac.last["clapper_scene"] == "middle return ground" and out.target == 8 and out.return_body is None
    monkeypatch.setattr(v2, "RETURN_BODY", True)
    out = step(tac, ws, fc)
    assert out.return_body == 7 and tac.last["clapper_back"]["return_body"] == 7
    change(fc, 8, state="Walk")
    assert step(tac, ws, fc).return_body == 7
    change(fc, 8, state="After Scuttle")                 # an idle family state outside the domain
    assert step(tac, ws, fc).return_body is None
    change(fc, 8, state="Idle")
    change(fc, 7, family=G.CC_SLAM, state="Slam Antic", committed=True)   # a new attack: the return is suspended
    out = step(tac, ws, fc)
    assert tac.last["clapper_back"] is None and out.return_body is None


# ---- the switch's binding ----

def test_the_switch_resolves_to_the_module_constant_in_the_measurement_manifest():
    from ssbot.train.forum_measure_manifest import configuration_manifest
    root = Path(v2.__file__).resolve().parents[1]
    m = configuration_manifest(root, None, modules={"ssbot.combat.forum_v2": v2},
                               environ={"SSBOT_FORUM_TWO_RETURN_BODY": "0"})
    s = m["switches"]["SSBOT_FORUM_TWO_RETURN_BODY"]
    assert s["resolution"] == "runtime_binding"
    assert s["effective"] == {"ssbot.combat.forum_v2.RETURN_BODY": v2.RETURN_BODY}


def test_hit_branch_lanes_read_the_narrowed_stack_after_the_lock_end_only(params, arena, monkeypatch):
    pl = ForumPlanner(params, arena, PlannerConfig(T=8, threads=1), ForumConfig())
    T1 = 10
    rows = np.array([0, 1, 2, 4])                      # row indices of the full tick (4: CONTINUE)
    pl.v2_ret = {"lock_end": np.array([2, 5, -1, -1, 3]), "info": {}}
    monkeypatch.setattr(pl, "_contacts_fn", lambda f, b, tk, sk, fn: np.ones((len(b), T1), bool))
    occ = np.zeros((4, T1), bool)
    rh = NS(bound=np.zeros((4, T1, 4)))
    bell = np.array([False, False, False, True])
    out = pl._v2_return_hit(occ, NS(rs=NS()), rh, rh.bound, rows, np.arange(T1) * v2.FT, np.zeros((4, T1), bool),
                            {}, np.zeros(4, bool), bell)
    assert not out[0, :3].any() and out[0, 3:].all()          # past its lock end (2)
    assert not out[1, :6].any() and out[1, 6:].all()          # past its lock end (5)
    assert not out[2].any() and not out[3].any()              # no lock end (a chain row) / a bell row: as they were
    assert pl.v2_ret["info"]["hit_rows"] == 2


def test_l2_keeps_the_other_one_named_for_the_side_slash_just_after_landing_in_the_gap(monkeypatch):
    # w3on 2869: the return completes on the landing in a 5.6 u gap; without the narrowing the next tick's rows could
    # not stay for the side slash. Only RETURN_LANDED_S, only while she still stands in the gap, both Idle / Walk.
    monkeypatch.setattr(v2, "RETURN_BODY", True)
    from ssbot.combat.tactics import clapper_priority as P
    from tests.test_middle_return313 import hero_at
    tac, ws, fc = scene(xs=(20., 34.), hx=15.); step(tac, ws, fc)
    near_attack(tac, ws, fc)
    hero_at(ws, 29.)                                     # landed in the gap: the return is done
    out = step(tac, ws, fc)
    assert tac.last["clapper_back"] is None and tac.last["clapper_back_end"]["end"] == "landed in the standing gap"
    assert out.return_body == 7 and tac.last["clapper_return_body"] == 7
    hero_at(ws, 29., y=9.)                               # off the ground: no longer
    assert step(tac, ws, fc).return_body is None
    hero_at(ws, 29.)
    assert step(tac, ws, fc).return_body == 7
    ws.stamp.t_game_s += P.RETURN_LANDED_S               # past the window
    assert step(tac, ws, fc).return_body is None
    monkeypatch.setattr(v2, "RETURN_BODY", False)        # the switch off: never
    tac, ws, fc = scene(xs=(20., 34.), hx=15.); step(tac, ws, fc)
    near_attack(tac, ws, fc)
    hero_at(ws, 29.)
    out = step(tac, ws, fc)
    assert out.return_body is None and tac.last["clapper_return_body"] is None

"""Key economy (M2 plan, 2026-10-03): the key plan log (combat.keyplan) on synthetic plan streams, the planner's key
cost kernel, and the property that the key economy terms never change the chosen plan's safety class (Hz, U, S, V,
P, the commitments, comfort, first contact, the tail result): synthetic Bell Beast scenes, and a replayed recording
when the run is on this machine."""
from pathlib import Path

import numpy as np
import pytest

from ssbot.combat.keyplan import KeyPlanLog, match_actual, summarize
from ssbot.combat.planner import Planner, PlannerConfig, _key_costs
from ssbot.ipc.framing import BIT
from ssbot.knowledge import kinematics as kin

A = 1 << BIT["attack"]
L = 1 << BIT["left"]
J = 1 << BIT["jump"]


def plan(d: int, n: int, presses: list[tuple[int, int, int]]) -> np.ndarray:
    """Masks for frames d .. d+n-1 with (mask, from, to) runs (absolute frames, to exclusive)."""
    m = np.zeros(n, np.int64)
    for bit, a, b in presses:
        m[max(a - d, 0):max(b - d, 0)] |= bit
    return m


def run(log: KeyPlanLog, f0: int, plans) -> None:
    for k, p in enumerate(plans):
        log.tick(f0 + k, f0 + k + 2, p)


def test_a_tap_planned_ahead_and_sent_unchanged():
    log = KeyPlanLog()
    log.reset(0)
    # an attack tap at frame 110-112 planned from tick 100 (decision frame 102) on
    run(log, 100, [plan(100 + k + 2, 20, [(A, 110, 112)]) for k in range(15)])
    for f in range(100, 125):
        log.observe(f, A if 111 <= f < 113 else 0)          # the game latched it a frame late
    rec = log.record()
    notes = [n for n in rec["notes"] if n[0] == "attack"]
    assert len(notes) == 1
    key, born, p0, r0, st, exf, sup, hist = notes[0]
    assert (born, p0, r0, st, exf, hist) == (100, 110, 112, "x", 108, [])
    sm = summarize(rec)
    assert sm["decided"] == 1 and sm["executed"] == 1 and sm["plan_change_rate"] == 0.0 and sm["leads"] == [10]
    assert match_actual(rec) == {0: (111, 113)}
    assert rec["actual"]["attack"] == [[111, 113]] and sm["flip_changes"] == 0


def test_moved_cancelled_late_and_reactive_presses():
    log = KeyPlanLog()
    log.reset(0)
    plans = []
    for k in range(12):
        d = 100 + k + 2
        if k < 3:
            p = plan(d, 20, [(A, 110, 112), (J, 115, 125)])
        elif k < 6:
            p = plan(d, 20, [(A, 112, 114)])                 # attack moved 2 frames; the jump cancelled
        else:
            p = plan(d, 20, [(A, 112, 114), (L, d, d + 3)])  # a reactive left tap, sent the tick it is decided
        plans.append(p)
    run(log, 100, plans)
    rec = log.record()
    by = {n[0]: n for n in rec["notes"]}
    assert by["attack"][4] == "x" and by["attack"][7] == [[103, 112, 114]]
    assert by["jump"][4] == "c" and by["jump"][7] == [[103, -1, -1]]
    left = [n for n in rec["notes"] if n[0] == "left"]
    assert left[0][1] == 106 and left[0][2] == 108 and left[0][4] == "x"       # born and sent at tick 106: lead 2
    sm = summarize(rec)
    assert sm["changed_before_press"] == 1 and sm["cancelled"] == 1
    # a late tick: the decision frame jumps past a pending press, which was never sent
    log2 = KeyPlanLog()
    log2.reset(1)
    log2.tick(100, 102, plan(102, 20, [(A, 105, 107)]))
    log2.tick(104, 106, plan(106, 20, []))
    n = log2.record()["notes"][0]
    assert n[4] == "l"


def test_held_release_changes_and_open_releases():
    log = KeyPlanLog()
    log.reset(0)
    # a left run held through the plan's end (open release) is not a change while the horizon moves on
    plans = [plan(100 + k + 2, 10, [(L, 104, 200)]) for k in range(6)]
    plans.append(plan(108, 10, [(L, 104, 112)]))            # now released at 112, a frame the last plan held it
    run(log, 100, plans)
    n = [x for x in log.record()["notes"] if x[0] == "left"][0]
    assert n[4] == "x" and n[3] < 0
    assert any(h[2] == 112 for h in n[7])                  # 112 < that plan's end 117: a change (after the press)
    sm = summarize(log.record())
    assert sm["hold_changed_after_press"] == 1 and sm["changed_before_press"] == 0


def test_flip_flops_at_one_frame():
    log = KeyPlanLog()
    log.reset(0)
    seq = [[(A, 120, 122)], [], [(A, 120, 122)], [], [(A, 120, 122)]]
    run(log, 100, [plan(100 + k + 2, 30, p) for k, p in enumerate(seq)])
    ch, ff, ff1 = log.record()["flips"]["attack"]
    assert ch == 8 and ff == 6 and ff1 == 6                 # 2 frames x 4 changes; all but the first go back


def test_key_cost_kernel():
    T = 10
    old = np.zeros(T, np.int64)
    old[3:5] = A                                            # the previous plan: an attack tap at 3-4
    cmd = np.zeros((4, T), np.int64)
    cmd[0, 3:5] = A                                         # the same plan: 1 press, 0 changes
    cmd[1, 4:6] = A                                         # moved by a frame: 2 rises differ, 2 falls differ
    cmd[2] = 0                                              # dropped: 1 rise, 1 fall
    cmd[3, 3:5] = A
    cmd[3, 7:9] = J                                         # an extra jump: 1 more press, 1 rise + 1 fall
    kp, kc = np.zeros(4), np.zeros(4)
    _key_costs(cmd, 0, old, 0, kp, kc)
    assert kp.tolist() == [1, 1, 0, 2]
    assert kc.tolist() == [0.0, 3.0, 1.5, 1.5]
    # a key held before the plan starts is no press
    cmd2 = np.full((1, T), L, np.int64)
    _key_costs(cmd2, L, np.zeros(0, np.int64), 0, kp[:1], kc[:1])
    assert kp[0] == 0 and kc[0] == 0


def test_presses_counted_from_mask_streams():
    from ssbot.tools.key_economy import gameplay_total, presses_from_masks
    fs = list(range(10, 20))
    masks = [L, L, 0, L, L | A, L, 0, J, J, 1 << BIT["enter"]]
    c = presses_from_masks(fs, masks, 10, 19)
    assert c == {"left": 1, "attack": 1, "jump": 1, "enter": 1}      # the first frame's held left is no press
    assert gameplay_total(c) == 3


def test_key_track_draws_a_logged_episode(tmp_path):
    from ssbot.tools.key_track import note_track, render
    log = KeyPlanLog()
    log.reset(0)
    seq = [[(A, 110, 112), (J, 118, 130)]] * 3 + [[(A, 112, 114)]] * 9
    run(log, 100, [plan(100 + k + 2, 30, p) for k, p in enumerate(seq)])
    for f in range(100, 125):
        log.observe(f, A if 112 <= f < 114 else 0)
    rec = log.record()
    notes = note_track(rec, 100, 120)
    by = {n["key"]: n for n in notes}
    assert by["attack"]["steps"] == [(100, 110, 112), (103, 112, 114)] and by["attack"]["latched"] == [112, 114]
    assert by["jump"]["cancel"] == 103
    res = render(rec, 100, 115, tmp_path, video=False)
    assert res["lanes"] == ["jump", "attack"] and len(list((tmp_path / "frames").glob("*.png"))) == 16


# ---- the planner property -----------------------------------------------------------------------------------------

def _sync(dst, src):
    from ssbot.tools.key_cost_check import sync
    sync(dst, src)


def test_key_terms_never_change_the_safety_class():
    """Synthetic scenes (a charge from either side at several phases and distances, a burst on the hero, idle):
    each tick is planned from the same state with the terms off and on (strong weights, so they do pick other plans);
    the chosen plans' classes and tail results are identical, and the "off" choice the on planner reports is the off
    planner's."""
    from ssbot.combat.boss_model import Anchor, BossModel
    from ssbot.combat.forecast import Ctx, Forecaster, Root, load_planner_templates
    from ssbot.combat.safety_filter import FilterContext
    from ssbot.combat.tactics import Tactics, load_playbook
    from ssbot.core.worldstate import ORACLE, E, WorldState

    model = BossModel.load()
    margin = (0.15, 0.25)
    tpls = load_planner_templates(model, margin)
    params = kin.HeroParams.load()
    arena = kin.Terrain2D.from_boxes([(60.0, 0.0, 110.0, 2.0), (67.2, 0.0, 69.2, 14.0), (102.0, 0.0, 104.0, 14.0)])
    on = Planner(params, arena, PlannerConfig(threads=4))
    off = Planner(params, arena, PlannerConfig(threads=4))
    tac = Tactics(load_playbook())
    scenes = []
    for side, dx in (("Set L", 10.0), ("Set R", -12.0), ("Set L", 6.0)):
        an = model.anchor("BB_CHARGE", side)
        for tau in (0.1, 0.3, 0.5, 0.7):
            scenes.append(([Root("Charge Antic", -tau, -tau, Ctx("BB_CHARGE", side, an, "P1", False), current=True)],
                           an.x + dx))
    scenes.append(([Root("Burst Out", 0.0, 0.0, Ctx("BB_BURST", None, Anchor(85.0, 5.49, 1), "P1", False),
                         current=True)], 85.0))
    scenes += [([], x) for x in (80.0, 85.0, 90.0)]
    differs = 0
    n = 0
    for roots, x in scenes:
        on.reset()
        for k in range(4):                               # consecutive ticks: the previous plan matters
            fc = Forecaster(model, ORACLE, margin=margin, templates=tpls)
            fc.tracker.roots = lambda origin, roots=roots: (roots, True)
            f = fc.forecast(2.0, 0.0)
            ws = WorldState()
            ws.hero.pos = E((x, 3.0544))
            ws.res.hp, ws.res.hp_max, ws.res.silk = E(5), E(5), E(5)
            ws.stamp.frame = 1000 + k
            prefs = tac.decide(ws, f, None, 3)
            ctx = FilterContext.from_world(ws, None, 3, want_bind=prefs.want_bind)
            S0 = kin.initial_state(params, x, 2.015 + params.foot)
            prefix = np.array([on.prev_cmd[0] if on.prev_cmd is not None else 0], np.int64)
            _sync(off, on)
            w0 = dict(prefs.weights)
            prefs.weights = dict(w0, key_press=0.0, key_change=0.0)
            ro = off.tick(ws, S0, kin.HoldState.idle(1), prefix, f, prefs, ctx)
            prefs.weights = dict(w0, key_press=0.5, key_change=1.0)
            rn = on.tick(ws, S0, kin.HoldState.idle(1), prefix, f, prefs, ctx)
            assert rn.cls == ro.cls and rn.tail_ok == ro.tail_ok, (roots, x, k, rn.name, ro.name)
            assert (rn.S, rn.V, rn.P, rn.Hz, rn.U, rn.forced_risk) == (ro.S, ro.V, ro.P, ro.Hz, ro.U, ro.forced_risk)
            assert rn.idx_off == ro.idx and rn.cls_off == rn.cls
            differs += rn.idx != ro.idx
            n += 1
    assert differs > 0, "the terms never chose another plan: the property was not exercised"


REC = Path("C:/ssbot/data/runs/m2/20261003_175813_BellBeast_eval_planner_oracle/rec/2026-10-03/TRAIN/i2_000")


@pytest.mark.skipif(not REC.exists(), reason="live recording not on this machine")
def test_key_terms_never_change_the_safety_class_on_a_recording():
    from ssbot.tools.key_cost_check import replay
    out = replay(REC, 900, None, 0.05, 0.1, 4)
    assert out["ticks"] > 500
    assert out["class_mismatch"] == 0 and out["tail_mismatch"] == 0 and out["off_mismatch"] == 0
    assert out["choice_differs"] > 0

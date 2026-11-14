"""Task 182 item 3 (TO_SOL #421 / #422; Sol seq362 / seq363, Astra DESIGN_REVIEW421 / DESIGN_REVIEW422): the landing-hammer exit, a final L2
stance preference (clapper_priority.LANDING_EXIT, default off). The pure exit (landing_exit_x: the analysis prototype's seven cases), then
two outer sequence groups through _landing_facts / _landing_exit / _apply_landing_exit and the real L2 entry, with a fake attack-range
tracker (tac.v2trk.now: iid -> (type, STATE dict, move instance)):
  1. another Clapper's committed open jump moves the stance and the withdraw; L2's own target's jump never does; a new instance of the
     same Clapper starts with no bound facing and no kept side; a wall / unknown jump in the mix keeps every stance;
  2. the side kept while allowed and chosen anew when not, no allowed end keeps the stance, a missing or changed flipX skips, the
     instance's end clears its memory, the switch off leaves the output as before and the exit moves nothing but the two stances.
The pure no-candidate shape stands for that component only, not for the whole policy."""
from dataclasses import fields, is_dataclass, replace
from types import SimpleNamespace as NS

import numpy as np
import pytest

from ssbot.combat.attack_range import Inst
from ssbot.combat.knife_chain_waypoint import WaypointGoal
from ssbot.combat.tactics import clapper_plans as CP, clapper_priority as P, gauntlet as G
from ssbot.combat.tactics.modes import EntryAttack, StageWithdraw
from ssbot.core.worldstate import E
from tests.test_clapper_priority import change, manual, scene, step   # noqa: F401  (autouse manual-B fixture)

F = P.landing_exit_x
W = (15.0, 50.0)
H = .25          # her half widths
PAD = .25


@pytest.fixture(autouse=True)
def plans_on(monkeypatch):
    monkeypatch.setattr(CP, "ENABLED", True)        # the plan table (production: SSBOT_FORUM_TWO_PLAN=1)


def tick(tac, ws, fc):
    """One L2 tick with a fresh log (GauntletTactics.decide starts tac.last afresh; tests.test_clapper_priority.step calls _decide only)."""
    tac.last = {}
    return step(tac, ws, fc)


def same(a, b):
    """Equal by value, numpy arrays and dataclasses (GoalPrefs) included, field by field."""
    if isinstance(a, np.ndarray) or isinstance(b, np.ndarray):
        return isinstance(a, np.ndarray) and isinstance(b, np.ndarray) and a.shape == b.shape and bool(np.array_equal(a, b))
    if is_dataclass(a) and not isinstance(a, type):
        return type(a) is type(b) and all(same(getattr(a, f.name), getattr(b, f.name)) for f in fields(a))
    if isinstance(a, dict):
        return isinstance(b, dict) and a.keys() == b.keys() and all(same(a[k], b[k]) for k in a)
    if isinstance(a, (list, tuple)):
        return type(a) is type(b) and len(a) == len(b) and all(same(x, y) for x, y in zip(a, b))
    return bool(a == b)


# ---- the pure exit (the analysis prototype's seven cases) ----

def test_outside_every_band_is_untouched():
    assert F(30.0, 30.0, [(20.0, 26.0)], [], [], [], [], W, H, H, PAD) == (30.0, None)


def test_the_nearer_allowed_end_is_taken():
    x, rec = F(24.0, 25.5, [(20.0, 26.0)], [], [], [], [], W, H, H, PAD)
    assert rec["span"] == (19.5, 26.5) and x == 26.5 and rec["exit"] == 26.5
    assert all(not e["why"] for e in rec["ends"])


def test_one_side_walled_the_other_crossing_only_the_predicted_landing_root_has_no_candidate():
    # Sol seq362's counter-example shape (the four runtime354 bouts never showed it): her at 20.0 under the band 14 .. 23; the wall stops
    # the left end; the right end crosses the predicted landing root interval 21.5 .. 22.1 while the jumper's current air root 30.0 is off
    # her segment
    x, rec = F(21.0, 20.0, [(14.0, 23.0)], [], [], [30.0], [(21.5, 22.1)], W, H, H, PAD)
    assert x == 21.0 and rec["exit"] is None
    assert rec["ends"][0]["why"] == ["wall"] and rec["ends"][1]["why"] == ["predicted landing root"]


def test_the_exit_leaves_a_live_rune_circle_too():
    x, rec = F(25.0, 25.5, [(20.0, 26.0)], [(26.5, 32.0)], [], [], [], W, H, H, PAD)
    assert rec["span"] == (19.5, 32.5) and x == 19.5             # the nearer allowed end of the merged span
    x2, _ = F(25.0, 31.0, [(20.0, 26.0)], [(26.5, 32.0)], [], [], [], W, H, H, PAD)
    assert x2 == 32.5                                            # nearer from 31: past the circle, not 26.5 inside it


def test_the_targets_own_band_is_an_obstacle_never_a_trigger():
    # _landing_exit passes L2's own target's band with the circles: alone it moves nothing; next to another's band the exit leaves both
    assert F(28.0, 28.0, [], [(26.5, 33.0)], [], [], [], W, H, H, PAD) == (28.0, None)
    x, rec = F(25.0, 31.0, [(20.0, 26.0)], [(26.5, 33.0)], [], [], [], W, H, H, PAD)
    assert rec["span"] == (19.5, 33.5) and x == 33.5


def test_a_current_root_on_the_way_rejects_that_end():
    x, rec = F(24.0, 25.5, [(20.0, 26.0)], [], [], [26.2], [], W, H, H, PAD)
    assert rec["ends"][1]["why"] == ["current root"] and x == 19.5


def test_a_body_next_to_the_band_is_merged():
    x, rec = F(24.0, 25.5, [(20.0, 26.0)], [], [(26.3, 30.0)], [], [], W, H, H, PAD)
    assert rec["span"][1] == 30.5 and rec["exit"] == 30.5


# ---- the outer layer: a fake attack-range tracker on the real scene ----

def state(x, y, vx, vy, st="Air"):
    """A Clapper's STATE dict as knife_chain_transfer.body_path reads it (pos, vel, the Control FSM's state, the body collider)."""
    return {"pos": (x, y), "vel": (vx, vy), "fsms": [{"name": "Control", "state": st, "t": .1}],
            "colliders": [{"name": "Song Heavy Sentry", "enabled": True,
                           "verts_world": [x - 2., y - 3., x + 2., y - 3., x + 2., y + 1., x - 2., y + 1.]}]}


def jump(t0=9.5, branch="open", st="Air", fam="CC_JUMP", dec_x=None):
    """A committed jump instance in state st. dec_x: its decision point (inst.dec["x"]: the jump rule's decision at its first Jump / Air
    frame, attack_range.Segmenter); None: fly() gives it the x it places the jumper at. inst.x0 (the move's start anchor) stays 0."""
    states = ["Jump Antic", "Jump", "Air"] + ([] if st in ("Jump", "Air") else ["Charged?", "Slam Effects?", "Slam 2", "Slam Recover"][
        :["Charged?", "Slam Effects?", "Slam 2", "Slam Recover"].index(st) + 1])
    inst = Inst(fam=fam, t0=t0, x0=0., y0=4.5, s=-1, hero_du=0., branch=branch, states=states)
    if dec_x is not None:
        inst.dec = {"t": t0 + .5, "b": 0, "x": float(dec_x), "y": 8., "s": -1, "L": 0.}
    return inst


def fly(tac, ws, fc, iid, x, vx, inst, flip="auto", y=8., vy=4.):
    """iid in the committed move instance inst at x (its fc subject, the tracker's STATE and instance, its entity's flipX: "auto" =
    facing its x speed, None = absent). An instance without a decision gets one at x (these fixtures' take-off area)."""
    if inst.dec is None:
        inst.dec = {"t": inst.t0 + .5, "b": 0, "x": float(x), "y": float(y), "s": 1 if vx > 0 else -1, "L": 0.}
    st = inst.states[-1]
    air = st in ("Jump", "Air")
    change(fc, iid, family=inst.fam, state=st, committed=True, pos=(x, y if air else 5.))
    if getattr(tac, "v2trk", None) is None:
        tac.v2trk = NS(now={})
    tac.v2trk.now[iid] = ("Song Heavy Sentry", state(x, y if air else 7.45, vx, vy if air else 0., st), inst)
    for e in ws.entities:
        if e.id == iid:
            e.flip_x = (vx > 0) if flip == "auto" else flip


def ground(tac, fc, iid):
    """iid's move instance over (back to Idle): the tracker holds no instance."""
    change(fc, iid, family=G.CC_IDLE, state="Idle", committed=False)
    tac.v2trk.now.pop(iid, None)


def layout(on, monkeypatch, **kw):
    """The positive layout: L2's target 7 idle at 30 (her at 27, its stance 26.0 on her side), the other Clapper 8 jumping at her from 36
    (x speed -8: lands near 33.6 facing left, its hammer band reaching back over 26)."""
    monkeypatch.setattr(P, "LANDING_EXIT", on)
    tac, ws, fc = scene(xs=(30., 36.), hx=27.)
    fly(tac, ws, fc, 8, 36., -8., jump(**kw))
    return tac, ws, fc


def sc_of(tac, ws, fc, hx=27., mem=None):
    """A Scene-like object of the current tick (the real geometry of these entities) for the outer functions alone; mem: L2's own memory
    unless given."""
    subjects = [s for s in fc.subjects if s.alive and s.in_play and s.pos is not None]
    return NS(tac=tac, ws=ws, subjects=subjects, mem=tac._clapper_priority if mem is None else mem,
              geo=P.geometry(tac, ws, subjects), hx=hx, t=ws.stamp.t_game_s)


# group 1 ----------------------------------------------------------------------------------------------------------------------------

def test_another_clappers_committed_open_jump_moves_the_final_stance(monkeypatch):
    tac, ws, fc = layout(False, monkeypatch)
    off = tick(tac, ws, fc)
    assert off.target == 7 and off.stance_x == pytest.approx(26.) and "clapper_landing_exit" not in tac.last
    tac, ws, fc = layout(True, monkeypatch)
    on = tick(tac, ws, fc)
    rec = tac.last["clapper_landing_exit"]["stance"]
    assert on.target == 7 and rec["x0"] == pytest.approx(26.) and on.stance_x == pytest.approx(rec["exit"])
    assert rec["exit"] == rec["span"][0] < 26. and not rec["ends"][0]["why"]
    assert set(rec["ends"][1]["why"]) == {"current root", "predicted landing root"}    # the right end past 7's root and 8's landing
    assert tac.goal.stance_x == pytest.approx(on.stance_x) and "landing exit 26.00->" in tac.last["goal_why"]
    (b,) = rec["bands"]
    assert b["iid"] == 8 and not b["own"] and b["face"] == -1 and b["state"] == "Air" and 33. < b["root"] < 34.5
    assert b["band"][0] == pytest.approx(b["root"] - P.LEXIT_BAND[1]) and b["band"][1] == pytest.approx(b["root"] + P.LEXIT_BODY)


def test_the_withdraw_stance_moves_with_its_own_side(monkeypatch):
    tac, ws, fc = layout(True, monkeypatch)
    out = tick(tac, ws, fc)
    sc = sc_of(tac, ws, fc, mem={})
    base = replace(out, stance_x=40., withdraw=StageWithdraw(26., (7, "stomp", 8), 100, None, (False, False, False)))
    g = NS(stance_x=40.)
    new, how = P._apply_landing_exit(sc, g, base, "x")
    rec = tac.last["clapper_landing_exit"]
    assert rec["stance"] is None and new.stance_x == 40. and g.stance_x == 40. and how == "x"      # 40 lies in no band
    assert new.withdraw.stance_x == pytest.approx(rec["withdraw"]["exit"]) and rec["withdraw"]["exit"] < 26.
    (key,) = sc.mem["lexit"]
    assert sc.mem["lexit"][key] == {"face": -1, "side_withdraw": -1}            # the stance's own side slot untouched


def test_the_targets_own_jump_never_triggers(monkeypatch):
    for on in (False, True):
        monkeypatch.setattr(P, "LANDING_EXIT", on)
        tac, ws, fc = scene(xs=(30., 36.), hx=27.)
        fly(tac, ws, fc, 8, 36., -8., jump())
        tac.goal.target = 8
        sc = sc_of(tac, ws, fc, mem={})
        (b,), unknown = P._landing_facts(sc)
        assert b["own"] and not unknown
        assert P._landing_exit(sc, [b], 33., "stance") == (33., None)        # inside its band, but its own target's
    # through L2: whenever L2 aims at the jumper, the stance is the jump rule's
    res = {}
    for on in (False, True):
        monkeypatch.setattr(P, "LANDING_EXIT", on)
        tac, ws, fc = scene(xs=(24., 40.), hx=27.)
        fly(tac, ws, fc, 8, 40., -8., jump())
        out = tick(tac, ws, fc)
        assert out.target == 8
        res[on] = (out.stance_x, tac.last.get("clapper_landing_exit"))
    assert res[True] == (res[False][0], None)


def test_a_new_instance_of_the_same_clapper_starts_with_no_facing_or_side(monkeypatch):
    tac, ws, fc = layout(True, monkeypatch, t0=9.5)
    tick(tac, ws, fc)
    mem = tac._clapper_priority["lexit"]
    assert list(mem) == [(8, 9.5)] and mem[(8, 9.5)]["face"] == -1 and mem[(8, 9.5)]["side_stance"] == -1
    # the next jump of the same Clapper (a new t0), facing the other way: bound afresh, no 'facing changed', no kept side
    fly(tac, ws, fc, 8, 24., 8., jump(t0=11.25))
    sc = sc_of(tac, ws, fc, hx=27.)
    bands, unknown = P._landing_facts(sc)
    assert not unknown and list(sc.mem["lexit"]) == [(8, 11.25)] and sc.mem["lexit"][(8, 11.25)] == {"face": 1}
    x, rec = P._landing_exit(sc, bands, 27., "stance")
    assert rec is not None and "kept_side" not in rec


def test_the_targets_own_band_is_merged_as_an_obstacle_by_the_outer_layer(monkeypatch):
    # L2's target 7 also in a committed jump (from 30 leftwards: lands near 28.4, its band reaching back to ~20.6): the exit out of 8's band
    # (25.9 .. 35.9) for her at 19 goes past 7's band too, not to 8's own left edge inside it
    tac, ws, fc = layout(True, monkeypatch)
    fly(tac, ws, fc, 7, 30., -6., jump(t0=9.0))
    sc = sc_of(tac, ws, fc, hx=19., mem={})
    bands, unknown = P._landing_facts(sc)
    own = next(b for b in bands if b["own"])
    assert not unknown and own["iid"] == 7 and own["face"] == -1
    from ssbot.combat.tactics.gauntlet import JT
    x, rec = P._landing_exit(sc, bands, 30., "stance")
    assert x == rec["exit"] == rec["span"][0]                                          # her side's end, allowed
    assert x == pytest.approx(own["band"][0] - sc.geo["right"] - JT["pad"], abs=1e-3)  # past the target's grown band, not inside it


def test_the_targets_predicted_landing_root_stays_in_the_hard_filter(monkeypatch):
    # 7 (L2's target) jumping leftwards from 26 lands near 23.6; she at 24.5 between its landing and its air root: the merged span's left
    # end lies past 7's predicted landing only, the right one past 7's air root - no end, the stance kept
    tac, ws, fc = layout(True, monkeypatch)
    fly(tac, ws, fc, 7, 26., -8., jump(t0=9.0))
    sc = sc_of(tac, ws, fc, hx=24.5, mem={})
    bands, unknown = P._landing_facts(sc)
    assert not unknown and {b["iid"]: b["own"] for b in bands} == {7: True, 8: False}
    x, rec = P._landing_exit(sc, bands, 30., "stance")
    assert x == 30. and rec["exit"] is None
    assert rec["ends"][0]["why"] == ["predicted landing root"] and "current root" in rec["ends"][1]["why"]


def test_a_landing_the_wall_rule_would_push_is_unknown(monkeypatch):
    # Sol seq364 (Astra's counter-example): decided at 46 facing left (its back 2.99 u from the right wall), STATE vx -1 / vy 38, body
    # (44, 3, 48, 7). The wall-free ballistic body lands at frame 54 on 45.10 - its branch open, inside the open zone - but the wall
    # rule pushes that landing to 44.59 (48.99 - 4.4): unknown, both stances kept
    from ssbot.combat import jump_behind as JB, knife_chain_transfer as T
    from ssbot.combat.are_types.clapper import WALL_ZONE
    res = {}
    for on in (False, True):
        monkeypatch.setattr(P, "LANDING_EXIT", on)
        tac, ws, fc = scene(xs=(30., 46.), hx=40.)
        fly(tac, ws, fc, 8, 46., -1., jump(dec_x=46.), y=6., vy=38.)
        res[on] = tick(tac, ws, fc)
    e = tac.v2trk.now[8][1]
    bp = T.body_path(e, P.LEXIT_PATH_F)
    k = int(np.nonzero(bp[1:, 1] <= T.ROUTE_FLOOR_Y + 1e-6)[0][0]) + 1
    root = 46. + float(bp[k][0] - bp[0][0])
    assert tuple(bp[0]) == (44., 3., 48., 7.) and k == 54 and root == pytest.approx(45.1)
    assert WALL_ZONE[0] <= root <= WALL_ZONE[1] and JB.wall_rule(46., root, -1) == pytest.approx(44.59)
    assert P._landing_facts(sc_of(tac, ws, fc, hx=40., mem={})) == ([], [(8, "Air", "wall rule moves the landing")])
    assert tac.last["clapper_landing_exit"]["unknown"] == [[8, "Air", "wall rule moves the landing"]]
    assert same(res[True], res[False])
    # the same flight decided 7 u off that wall (its back 6.99 u from it): no push - an open jump that needs no wall correction, its band
    fly(tac, ws, fc, 8, 42., -1., jump(t0=12.0, dec_x=42.), y=6., vy=38.)
    (b,), unknown = P._landing_facts(sc_of(tac, ws, fc, hx=40., mem={}))
    assert not unknown and b["root"] == pytest.approx(41.1) and JB.wall_rule(42., b["root"], -1) == b["root"]


@pytest.mark.parametrize("dec", [None, {"t": 10., "x": float("nan")}, {"t": 10.}])
def test_a_missing_or_non_finite_decision_point_is_unknown(monkeypatch, dec):
    tac, ws, fc = layout(True, monkeypatch)
    tac.v2trk.now[8][2].dec = dec                      # (inst.x0, the move's start anchor, is never read in its place)
    assert P._landing_facts(sc_of(tac, ws, fc, mem={})) == ([], [(8, "Air", "no decision point")])


def test_a_missing_state_velocity_in_the_air_is_unknown(monkeypatch):
    tac, ws, fc = layout(True, monkeypatch)
    del tac.v2trk.now[8][1]["vel"]                     # body_path would take (0, 0): a straight drop
    assert P._landing_facts(sc_of(tac, ws, fc, mem={})) == ([], [(8, "Air", "no STATE velocity")])


def test_the_switch_is_off_by_default():
    import os
    if os.environ.get("SSBOT_FORUM_LANDING_EXIT") is None:
        assert P.LANDING_EXIT is False


@pytest.mark.parametrize("how", ["target wall branch", "target unknown branch", "other wall branch", "other wall zone"])
def test_a_wall_or_unknown_jump_in_the_mix_keeps_every_stance(monkeypatch, how):
    res = {}
    for on in (False, True):
        tac, ws, fc = layout(on, monkeypatch, branch="wall" if how == "other wall branch" else "open")
        if how.startswith("target"):
            fly(tac, ws, fc, 7, 30., 0.5, jump(t0=9.0, branch="wall" if "wall" in how else None))
        if how == "other wall zone":
            fly(tac, ws, fc, 8, 47., -2., jump())          # its ballistic landing ~46.4: past the open zone's 45.5
        out = tick(tac, ws, fc)
        res[on] = out
    assert same(res[True], res[False])
    rec = tac.last["clapper_landing_exit"]
    assert "stance" not in rec and rec["unknown"]
    want = {"target wall branch": (7, "branch wall"), "target unknown branch": (7, "branch None"),
            "other wall branch": (8, "branch wall"), "other wall zone": (8, "landing root in the wall zone")}[how]
    assert [u[0] for u in rec["unknown"]] == [want[0]] and rec["unknown"][0][2] == want[1]


def test_a_missing_scene_geometry_or_tracker_keeps_the_stance(monkeypatch):
    tac, ws, fc = layout(True, monkeypatch)
    tick(tac, ws, fc)
    sc = sc_of(tac, ws, fc)
    sc.geo = None
    bands, unknown = P._landing_facts(sc)
    assert bands and unknown == [(None, None, "no scene geometry")]
    tac.v2trk = None
    assert P._landing_facts(sc_of(tac, ws, fc)) == ([], [(None, None, "no tracker")])
    out = tick(tac, ws, fc)
    assert tac.last["clapper_landing_exit"] == dict(unknown=[[None, None, "no tracker"]], bands=[]) and out.stance_x == pytest.approx(26.)


# group 2 ----------------------------------------------------------------------------------------------------------------------------

def test_the_side_is_kept_while_allowed_and_chosen_anew_when_not():
    # With the hard root filter one jump's band never leaves both ends allowed (its predicted landing root lies between them), so on real
    # bands the kept side is always the only allowed one. The side memory alone, on a synthetic band whose predicted root interval lies
    # off it, with no Clapper roots: walls 0 .. 60, no bodies, no circles.
    from ssbot.combat.tactics.gauntlet import JT
    g = .25 + JT["pad"]
    sc = NS(tac=NS(rune_life=None), ws=None, subjects=[], mem={}, geo=dict(left=.25, right=.25, xa=0., xb=60., bodies={}), hx=34., t=0.)
    syn = [dict(iid=8, own=False, key=(8, 9.5), state="Air", face=-1, root=33., root_iv=(1., 1.5), land_k=10, band=(25., 35.))]
    lo, hi = 25. - g, 35. + g
    x, rec = P._landing_exit(sc, syn, 30., "stance")            # both allowed: the nearer (right) one, now kept
    assert x == pytest.approx(hi) and "kept_side" not in rec and sc.mem["lexit"][(8, 9.5)] == {"side_stance": 1}
    sc.hx = 26.
    x, rec = P._landing_exit(sc, syn, 30., "stance")            # the left one nearer now: the kept right one holds
    assert x == pytest.approx(hi) and rec["kept_side"] == 1 and all(not e["why"] for e in rec["ends"])
    sc.subjects = [NS(iid=99, pos=(33., 5.))]                    # a root on the way right: the left one, kept from then on
    x, rec = P._landing_exit(sc, syn, 30., "stance")
    assert rec["ends"][1]["why"] == ["current root"] and x == pytest.approx(lo) and "kept_side" not in rec
    assert sc.mem["lexit"][(8, 9.5)] == {"side_stance": -1}
    sc.subjects.append(NS(iid=98, pos=(25.2, 5.)))              # and one on the way left: no end, the stance kept, the side as it was
    x, rec = P._landing_exit(sc, syn, 30., "stance")
    assert x == 30. and rec["exit"] is None and sc.mem["lexit"][(8, 9.5)] == {"side_stance": -1}
    x, rec = P._landing_exit(sc, syn, 30., "withdraw")          # the withdraw has its own slot
    assert rec["exit"] is None and "side_withdraw" not in sc.mem["lexit"][(8, 9.5)]


def test_the_real_band_moves_her_to_the_side_she_is_on(monkeypatch):
    # the real band: she right of 8's predicted landing root and of its current (air) root takes the right end (the left one past them),
    # and back on the left the left one
    tac, ws, fc = layout(True, monkeypatch)
    tick(tac, ws, fc)
    sc = sc_of(tac, ws, fc, hx=36.8)
    bands, _ = P._landing_facts(sc)
    x, rec = P._landing_exit(sc, bands, 34., "stance")
    assert "predicted landing root" in rec["ends"][0]["why"] and not rec["ends"][1]["why"] and x == rec["ends"][1]["x"]
    assert "kept_side" not in rec and sc.mem["lexit"][bands[0]["key"]]["side_stance"] == 1
    sc.hx = 27.
    x, rec = P._landing_exit(sc, bands, 28., "stance")
    assert x == rec["ends"][0]["x"] and "kept_side" not in rec and sc.mem["lexit"][bands[0]["key"]]["side_stance"] == -1


@pytest.mark.parametrize("seq", [(None, False, False), (False, True, False), (False, None, False)])
def test_a_missing_or_changed_flip_x_skips(monkeypatch, seq):
    tac, ws, fc = layout(True, monkeypatch)
    e8 = next(e for e in ws.entities if e.id == 8)
    e8.facing = E(-1.)                     # the oracle backend's Entity.facing (clapper_facing's fallback): never read here
    seen = []
    for fl in seq:
        e8.flip_x = fl
        out = tick(tac, ws, fc)
        rec = tac.last.get("clapper_landing_exit") or {}
        seen.append((round(out.stance_x, 4), [u[2] for u in rec.get("unknown") or []]))
    if seq[0] is None:      # no flipX, then bound left on the first one seen, kept
        assert seen[0] == (26., ["no observed flipX"]) and seen[1][0] < 26. and seen[2][0] < 26. and not seen[1][1]
    elif seq[1] is True:    # bound left, then seen right: unknown from then on, also once it reads left again
        assert seen[0][0] < 26. and seen[1] == (26., ["facing changed"]) and seen[2] == (26., ["facing changed"])
    else:                   # bound left, then absent: no observed flipX (clapper_facing's Entity.facing fallback is not used)
        assert seen[0][0] < 26. and seen[1] == (26., ["no observed flipX"]) and seen[2][0] < 26.


def test_the_instance_end_clears_its_memory(monkeypatch):
    tac, ws, fc = layout(True, monkeypatch)
    tick(tac, ws, fc)
    assert (8, 9.5) in tac._clapper_priority["lexit"]
    # landed and in its hammer: the band from the observed root, the memory kept
    fly(tac, ws, fc, 8, 33.6, 0., jump(st="Slam 2", dec_x=36.))          # its decision point: the take-off at 36
    out = tick(tac, ws, fc)
    rec = tac.last["clapper_landing_exit"]["stance"]
    assert rec["bands"][0]["state"] == "Slam 2" and rec["bands"][0]["root"] == pytest.approx(33.6) and out.stance_x < 26.
    assert (8, 9.5) in tac._clapper_priority["lexit"]
    # Slam Recover: no hammer ahead, no band, memory still held (the instance lives)
    fly(tac, ws, fc, 8, 33.6, 0., jump(st="Slam Recover", dec_x=36.))
    tick(tac, ws, fc)
    assert "clapper_landing_exit" not in tac.last and (8, 9.5) in tac._clapper_priority["lexit"]
    # over: no instance, the memory goes
    ground(tac, fc, 8)
    tick(tac, ws, fc)
    assert tac._clapper_priority["lexit"] == {}


def test_the_switch_off_computes_nothing_and_changes_nothing(monkeypatch):
    def boom(sc):
        raise AssertionError("LANDING_EXIT off must not read anything")
    tac, ws, fc = layout(False, monkeypatch)
    monkeypatch.setattr(P, "_landing_facts", boom)
    out = tick(tac, ws, fc)
    assert out.stance_x == pytest.approx(26.) and "clapper_landing_exit" not in tac.last and "landing exit" not in tac.last["goal_why"]
    assert "lexit" not in tac._clapper_priority


def test_the_exit_moves_nothing_but_the_two_stances(monkeypatch):
    # through L2: on and off differ in the stance only
    res = {}
    for on in (False, True):
        tac, ws, fc = layout(on, monkeypatch)
        res[on] = tick(tac, ws, fc)
    assert res[True].stance_x != res[False].stance_x
    assert same(replace(res[True], stance_x=res[False].stance_x), res[False])
    # on an output that carries a waypoint, an entry attack, a hit_kw and a withdraw: only stance_x and the withdraw's stance_x change
    tac, ws, fc = layout(True, monkeypatch)
    tick(tac, ws, fc)
    sc = sc_of(tac, ws, fc)
    wp = WaypointGoal(x=31.5, by_f=500, kind="retreat", source=8, plan=(1, 1, "back"))
    ea = EntryAttack(target=7, kind="side", source=8, source_family="CC_JUMP", source_distance=6., picked_at=9.9)
    base = replace(tick(tac, ws, fc), stance_x=28., waypoint=wp, entry_attack=ea, hit_kw={7: (0., 0., 0., 2.)},
                   withdraw=StageWithdraw(29., (7, "stomp", 8), 100, None, (False, False, False)))
    new, _ = P._apply_landing_exit(sc, NS(stance_x=28.), base, "x")
    assert new.stance_x < 28. and new.withdraw.stance_x < 29.
    assert same(replace(new, stance_x=base.stance_x, withdraw=base.withdraw), base)
    assert new.waypoint is wp and new.entry_attack is ea and new.target == base.target and new.hit_kw == base.hit_kw
    assert tac.last["clapper_landing_exit"]["waypoint"] == [31.5, "retreat"] and tac.last["clapper_landing_exit"]["entry"] == [7, "side"]

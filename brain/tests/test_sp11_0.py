"""Task 1v1 SP11-0 (forum.md 82): quick wins from the SP10 cause audits, each behind its own switch, default off.
SSBOT_FORUM_TWO_GUARD - the other Clapper's danger spans (its jump landing band once aimed, its big rune circle, its
hammer, its body) for the one-Clapper scripts: the chase (no start / abort inside one, no step / dash into one), the low
hop (no start / abort with its stance in one), the slam playbook's way out (the side away from them);
SSBOT_FORUM_TWO_RUNEGATE - the playbook's "other rune circle" gate on the circle's lit window at the strike's frames (the
dome); SSBOT_FORUM_TWO_COMMIT - a non-focus Clapper's committed jump and its rune circle with the focus margin in the v2
support. Off: unchanged."""
import importlib

import pytest

from ssbot.combat import evade_chase as ec
from ssbot.combat import rune_lowhop as rl
from ssbot.combat import slam_play as sp
from ssbot.combat import two_play as tp
from tests.test_sp10b import after_run, two
from tests.test_sp9 import two_state


def test_runegate_default_off(monkeypatch):
    monkeypatch.delenv("SSBOT_FORUM_TWO_RUNEGATE", raising=False)
    monkeypatch.setenv("SSBOT_FORUM_V2", "1")
    try:
        assert not importlib.reload(sp).TWO_RUNEGATE
        monkeypatch.setenv("SSBOT_FORUM_TWO_RUNEGATE", "1")
        assert importlib.reload(sp).TWO_RUNEGATE
    finally:
        monkeypatch.delenv("SSBOT_FORUM_V2", raising=False)
        monkeypatch.delenv("SSBOT_FORUM_TWO_RUNEGATE", raising=False)
        importlib.reload(sp)


@pytest.mark.parametrize("v2,val,want", [("1", None, True), ("1", "0", False), ("0", None, False), (None, None, False),
                                         (None, "1", True)])
def test_guard_and_commit_follow_v2(monkeypatch, v2, val, want):
    """Since the SP11-0 A/B: TWO_GUARD and TWO_COMMIT follow SSBOT_FORUM_V2 when unset (=0 off)."""
    from ssbot.combat import attack_range as ar
    from ssbot.combat import forum_v2 as fv
    for k, v in (("SSBOT_FORUM_V2", v2), ("SSBOT_FORUM_TWO_GUARD", val), ("SSBOT_FORUM_TWO_COMMIT", val)):
        if v is None:
            monkeypatch.delenv(k, raising=False)
        else:
            monkeypatch.setenv(k, v)
    try:
        assert importlib.reload(tp).GUARD == want
        assert importlib.reload(fv).COMMIT == want and importlib.reload(ar).COMMIT_CORE == want
        assert fv.COMMIT_M == fv.FOCUS_M
    finally:
        for k in ("SSBOT_FORUM_V2", "SSBOT_FORUM_TWO_GUARD", "SSBOT_FORUM_TWO_COMMIT"):
            monkeypatch.delenv(k, raising=False)
        importlib.reload(tp)
        importlib.reload(ar)
        importlib.reload(fv)


def test_committed_predicate():
    from ssbot.combat import forum_v2 as fv
    from ssbot.combat.attack_range import Inst
    mk = (lambda fam, *sts: Inst(fam=fam, t0=0.0, x0=0.0, y0=0.0, s=1, hero_du=0.0, states=list(sts)))
    assert fv.committed(mk("CC_JUMP", "Jump Antic", "Jump", "Air"))
    assert fv.committed(mk("CC_JUMP_CAST", "Cast Slam Antic", "Cast Slam Antic 2", "Jump", "Air", "Slam 2"))
    assert not fv.committed(mk("CC_JUMP", "Jump Antic"))                 # before the aim: the landing follows her
    assert not fv.committed(mk("CC_SLAM", "Slam Antic"))                 # the antic turns to her
    assert not fv.committed(None)


@pytest.fixture
def guard_on(monkeypatch):
    for k in ("GUARD", "SPACE", "ANY"):
        monkeypatch.setattr(tp, k, True)
    yield


def jump_seq(two, b_x=40.0, hx=31.0, fam_st="Jump Antic"):
    """B (iid 99, at b_x facing left) jumps at her: antic, then its aim (Air) with her at hx."""
    for i, (st, tin) in enumerate(((fam_st, 0.0), (fam_st, 0.2), ("Air", 0.0))):
        s = two_state(1000 + i, "Idle", 0.5, hx=hx, b_st=st, b_x=b_x)
        s["ents"][1]["fsms"] = [{"name": "Control", "state": st, "t": tin}]
        two.observe(1000 + i, s, (1000 + i) / 60.0)
    return s


def test_guard_spans_landing_rune_hammer_body(guard_on):
    two = tp.TwoPlay()
    s = jump_seq(two, b_x=40.0, hx=31.0, fam_st="Cast Slam Antic")
    sp_ = two.guard_spans(1002, s, 1002 / 60.0)
    kinds = {(k, i) for _, _, k, i in sp_}
    assert ("land", 99) in kinds and ("rune", 99) in kinds and ("body", 7) in kinds and ("body", 99) in kinds
    # B faces left (toward her): the landing x0 + 0.92 clamp(31 + 5 - 40) = 40 - 3.68 = 36.32; the band 3.0 u behind
    # (right of it) to 8.3 u in front (left of it)
    lo, hi = next((a, b) for a, b, k, i in sp_ if k == "land")
    assert lo == pytest.approx(36.32 - 8.3) and hi == pytest.approx(36.32 + 3.0)
    c = 36.32 - 6.48
    lo, hi = next((a, b) for a, b, k, i in sp_ if k == "rune")
    assert lo == pytest.approx(c - 7.74) and hi == pytest.approx(c + 7.74)
    # the focus's own spans are skipped by the consumers
    assert tp.guard_hit(sp_, 30.0, 30.2, own=99) is None or tp.guard_hit(sp_, 30.0, 30.2, own=99) == "body"
    assert tp.guard_hit(sp_, 30.0, 30.2, kinds=("land",), own=7) == "land"
    # a slam: Slam Antic both sides 12.5 u, Slam 1 in front only
    s = two_state(1010, "Idle", 0.5, hx=31.0, b_st="Slam 1", b_x=40.0)
    two = tp.TwoPlay()
    sp_ = two.guard_spans(1010, s, 1010 / 60.0)
    lo, hi = next((a, b) for a, b, k, i in sp_ if k == "hammer")
    assert lo == pytest.approx(40.0 - 12.5) and hi == pytest.approx(40.0 + 1.9)
    assert tp.guard_room(sp_, 25.0, 1, kinds=("hammer",)) == pytest.approx(27.5 - 25.0)
    assert tp.guard_room(sp_, 30.0, 1, kinds=("hammer",)) == 0.0
    # one live Clapper: none
    s1 = two_state(1011, "Idle", 0.5)
    s1["ents"] = s1["ents"][:1]
    assert two.guard_spans(1011, s1, 1011 / 60.0) == []


def test_chase_held_by_the_other_ones_landing(guard_on):
    """F (iid 7 at 31, facing left) evades; she is 4.5 u in front of it (x 26.5); B's jump landing band (aimed) covers
    the ground between: no start; with the band farther the run key stops at its edge; no dash into it."""
    two = tp.TwoPlay()
    # B at 20 faces right: its landing from her x 26.5 at the aim: 20 + 0.92 * (26.5 - 5 - 20) = 21.38, band to 29.68
    jump_seq(two, b_x=20.0, hx=26.5)
    s = two_state(1003, ec.EVADE, 3 / 60.0, x_rel=4.5, b_st="Air", b_x=20.0, b_flip=True)
    gsp = two.guard_spans(1003, s, 1003 / 60.0)
    ch = ec.EvadeChase(one=False, two=True)
    assert ch.step(1003, s, True, True, focus=7, guard=gsp) is None and ch.why_not.get("guard") == 1
    assert ch.guard_f == [[1003, "land"]]
    # without the guard the chase starts
    ch = ec.EvadeChase(one=False, two=True)
    assert ch.step(1003, s, True, True, focus=7) is not None
    # (fp1 fix) inside a band whose exit toward F (28.0, 1.5 u on) is short of the chase's stop (F 8 u away at 34.5):
    # the chase is her way out - it starts; with the exit 7 u on (F 8 u away) it does not
    s8 = two_state(1003, ec.EVADE, 3 / 60.0, x_rel=8.0, cx=34.5, b_st="Idle", b_x=45.0)
    ch = ec.EvadeChase(one=False, two=True)
    assert ch.step(1003, s8, True, True, focus=7, guard=[(20.0, 28.0, "land", 99)]) is not None
    assert ch.run.guard_kind == "land"
    ch = ec.EvadeChase(one=False, two=True)
    assert ch.step(1003, s8, True, True, focus=7, guard=[(20.0, 33.5, "land", 99)]) is None
    # F facing right at 25 (she 4.5 u in front at 29.5, the way to F is -x); a span ending 0.2 u short of her: the run
    # key held back (the next step would enter it)
    s = two_state(1003, ec.EVADE, 3 / 60.0, x_rel=4.5, cx=25.0, flip=True, b_st="Idle", b_x=45.0)
    gsp = [(10.0, 29.3, "land", 99)]
    ch = ec.EvadeChase(one=False, two=True)
    m = ch.step(1003, s, True, True, focus=7, guard=gsp)
    assert m == 0 and ch.run is not None and ch.run.guard_stops == 1
    gsp = [(10.0, 25.0, "land", 99)]                    # 4.5 u of room: the step goes
    ch = ec.EvadeChase(one=False, two=True)
    m = ch.step(1003, s, True, True, focus=7, guard=gsp)
    assert m & sp.M_L
    # 2.5 u of room (her 7.5 u in front at 32.5, the span to 30.0): the step, no dash (it needs 3.78 u)
    ch = ec.EvadeChase(one=False, two=True)
    s2 = two_state(1003, ec.EVADE, 3 / 60.0, x_rel=7.5, cx=25.0, flip=True, b_st="Idle", b_x=45.0)
    gsp2 = [(10.0, 30.0, "land", 99)]
    m = ch.step(1003, s2, True, True, focus=7, guard=gsp2)
    assert m == sp.M_L and ch.run.dash_k is None
    ch = ec.EvadeChase(one=False, two=True)
    m = ch.step(1003, s2, True, True, focus=7)
    assert m & sp.M_DASH                                 # (the same without the guard: the dash)


def test_lowhop_no_start_with_the_stance_in_the_others_circle():
    hop = rl.RuneLowHop(two=True)
    s = two_state(1000, "Spell Antic", 2 / 60.0, x_rel=4.0)
    hx = sp.hero_x(s)
    gsp = [(hx - 3.0, hx + 0.5, "rune", None)]
    hop.step(1000, s, True, True, t_game=1000 / 60.0, guard=gsp)
    assert hop.run is None and hop.why_not.get("guard") == 1
    # (fp1 fix) only the big rune circle counts for the low hop: a landing band there does not
    hop = rl.RuneLowHop(two=True)
    hop.step(1000, s, True, True, t_game=1000 / 60.0, guard=[(hx - 3.0, hx + 0.5, "land", 99)])
    assert hop.run is not None
    hop = rl.RuneLowHop(two=True)
    hop.step(1000, s, True, True, t_game=1000 / 60.0, guard=[(hx + 30.0, hx + 31.0, "rune", None)])
    assert hop.run is not None
    # in the run: a span appearing over the stance aborts it (outside the critical window)
    s2 = two_state(1001, "Spell Antic", 3 / 60.0, x_rel=4.0)
    assert hop.step(1001, s2, True, True, t_game=1001 / 60.0, guard=gsp) is None
    assert hop.run is None and hop.done[-1].why == "guard"


@pytest.mark.parametrize("guard", [False, True])
def test_slam_way_out_side_away_from_the_other_ones_landing(monkeypatch, guard):
    """A (iid 7 at 30 facing right) struck, B at 42: SIDE's pick is the front (between them); B's jump landing band
    covers the front landing spot (33.7): with the guard the way out goes behind A."""
    monkeypatch.setattr(sp, "TWO_PLAY", True)
    monkeypatch.setattr(sp, "LATE", True)
    monkeypatch.setattr(sp, "NEAR", True)
    monkeypatch.setattr(sp, "SIDE", True)
    monkeypatch.setattr(sp, "TWO_HANDOFF", False)
    p = sp.SlamPlay(sp.PlayCfg())
    r = after_run(face=1, ta=10.0)
    r.near, r.k_turn, r.k_slash = None, None, None
    p.run = r
    ta0 = 10.0 + 48 / 60.0
    gsp = [(32.0, 40.0, "land", 8)] if guard else None
    # her x 30.2 (just over A's centre, rising from the bounce): behind is clear by Slam 0 + 40
    s = two(1000, "Slam 2", 0.1, "Air", 0.1, ax=30.0, bx=42.0, hx=30.2, ground=False, vy=6.0)
    p.step(1000, s, False, t_game=ta0 + 12 / 60.0, guard=gsp)
    assert r.near == (-1 if guard else 1)
    assert (r.side_why == "guard") == guard


def test_runegate_dome_and_burst(monkeypatch):
    """The other one's jump cast landed at x 20 facing right at clock 10.0 (its circle centre 26.75): the strike from a
    stand point 5 u past the centre started at the landing is under the dome in its bounce (k 65-88: 6-6.9 u up,
    sqrt(51.7 - 6.5^2) = 3.1 u at the apex); a stand point 9 u past the centre is not; a burst circle never blocks."""
    monkeypatch.setattr(sp, "TWO_RUNEGATE", True)
    p = sp.SlamPlay(sp.PlayCfg())
    rc = (20.0, 1, 10.0)
    assert p._rg_exposed(rc, 26.75 + 3.0, 10.0, 2)
    assert not p._rg_exposed(rc, 26.75 + 9.0, 10.0, 2)
    # a strike started 40 frames after the landing: the lit window at k 25-48 (on the ground / rising at 5 u): exposed
    assert p._rg_exposed(rc, 26.75 + 5.0, 10.0 + 40 / 60.0, 2)
    # past the lit window: not
    assert not p._rg_exposed(rc, 26.75 + 3.0, 10.0 + 90 / 60.0, 2)
    # its circle seen lit, then unlit: burst
    lit = {"type_key": "damager", "iid": 555, "pos": [26.75, 3.3], "colliders": [
        {"verts_world": [26.75 - 7.19, 3.3, 26.75 + 7.19, 3.3, 26.75, 10.5], "enabled": True}]}
    s = two(1000, "Idle", 0.1, "Idle", 0.1)
    s["ents"].append(lit)
    p._rg_observe(s, 11.1)
    lit["colliders"][0]["enabled"] = False
    p._rg_observe(s, 11.25)
    assert not p._rg_exposed(rc, 26.75 + 3.0, 11.26, 2)


def test_runegate_off_keeps_the_old_gate(monkeypatch):
    monkeypatch.setattr(sp, "TWO_RUNEGATE", False)
    p = sp.SlamPlay(sp.PlayCfg())
    p._rune[8] = (20.0, 1, 10.0)
    s = two(1000, "Slam Antic", 0.0, "Idle", 0.1, ax=40.0, bx=20.0, hx=35.0)
    assert p._two_danger(s, s["ents"][0], 30.0, 10.5, 2) == "other rune circle"
    assert p._two_danger(s, s["ents"][0], 30.0, 10.0 + 1.5, 2) is None

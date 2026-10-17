"""Task 1v1 SP8d (forum.md 75): the small runes with a low hop and slashes through (SSBOT_FORUM_RUNE_LOWHOP, default
off; ssbot.combat.rune_lowhop)."""
import copy
import importlib

import pytest

from ssbot.combat import rune_lowhop as lh
from ssbot.combat import slam_play as sp
from tests.test_slam_play import state

SA, C1, C2, IDLE = 44, 6, 25, 40          # Spell Antic, Cast 1, Cast 2, Idle frames of the toy cast


def cast_state_at(k):
    """The Control state and its time at frame k from the Spell Antic entry."""
    if k < 0:
        return "Idle", 1.0
    for name, n in (("Spell Antic", SA), ("Cast 1", C1), ("Cast 2", C2), ("Idle", IDLE)):
        if k < n:
            return name, k / 60.0
        k -= n
    return "Evade Scuttle", k / 60.0


def c_state(f, k, x_rel, cx=31.0, flip=False, bottom=0.0, atk_cd=0.0, bombs=(), hp=9, two=False, facing=None):
    face = 1 if flip else -1
    st, tin = cast_state_at(k)
    s = state(f, st, tin, cx=cx, flip=flip, hx=cx + face * x_rel, ground=bottom <= 0.031, hp=hp)
    h = s["hero"]
    h["box"][1] = 3.015 + bottom
    h["box"][3] = 5.094 + bottom
    h["tm"] = {"atk_cd": atk_cd}
    h["anim"] = {"clip": "Idle"}
    h["facing"] = -face if facing is None else facing
    s["ents"][0]["vel"] = [0.0, 0.0]
    for i, (bx, lit) in enumerate(bombs):
        s["ents"].append({"type_key": "rune bomb small", "iid": 500 + i, "pos": [bx, 3.65],
                          "colliders": [{"verts_world": _circle(bx, 3.65), "r": lh.R, "enabled": lit,
                                         "damage": {"eff": 2} if lit else None}]})
    if two:
        o = copy.deepcopy(s["ents"][0])
        o["iid"] = 99
        o["pos"] = [cx + 15.0, 7.45]
        s["ents"].append(o)
    return s


def _circle(x, y):
    import math
    out = []
    for i in range(8):
        a = 2 * math.pi * i / 8
        out += [x + lh.R * math.cos(a), y + lh.R * math.sin(a)]
    return out


def simulate(x_rel0=4.3, cx=31.0, flip=False, cfg=None, n=140, a1=None, lit_lead=20, hurt_at=None, two=False):
    """A toy cast: Spell Antic at k = 0, Cast 2 at SA + C1; ring r's bombs (both sides) appear at Cast 2 + 9.6 r (ring
    1 at a1 when given) and light lit_lead frames later for 6 frames. She walks WALK_U per frame with a key on the
    ground, jumps by the hop table (the hold so far), the attack cooldown 18 frames. Returns (script, rows) with rows
    [(k, x_rel, bottom, mask, lit bombs over her)]."""
    h = lh.RuneLowHop(cfg or lh.HopCfg())
    face = 1 if flip else -1
    toward = sp.M_R if -face > 0 else sp.M_L
    pending, rows = {}, []
    x = x_rel0
    kc = SA + C1
    x0 = cx
    press_k, held = None, 0
    last_atk = -99
    for k in range(-2, n):
        f = 5000 + k
        m_now = pending.pop(f, 0)
        bottom = 0.0
        if m_now & sp.M_J and press_k is None:
            press_k, held = k, 0
        if press_k is not None:
            j = k - press_k
            if m_now & sp.M_J and held == j:
                held += 1
            tab = lh.HOP_LO[min(max(held, 9), 16)]
            bottom = tab[j] if j < len(tab) else 0.03
            if j >= len(tab):
                press_k = None
        if m_now & sp.M_A and not (pending.get(f - 1, 0) & sp.M_A) and k - last_atk >= 18:
            last_atk = k
        if m_now & toward:
            x -= sp.WALK_U
        elif m_now & (sp.M_L | sp.M_R):
            x += sp.WALK_U
        bombs, lit_over = [], []
        for r in (0, 1, 2, 3):
            a = kc + (round(9.6 * r) if not (r == 1 and a1 is not None) else a1 - kc)
            for side in ((1,) if r == 0 else (1, -1)):
                bx = x0 + face * side * 4.2 * r
                if a <= k < a + lit_lead + 6:
                    lit = k >= a + lit_lead
                    bombs.append((bx, lit))
                    hx = cx + face * x
                    if lit and abs(hx - bx) < lh.R + 0.25 and bottom < lh.bomb_top(3.65, hx - bx):
                        lit_over.append((r, round(bottom, 2)))
        cd = max(0.0, (18 - (k - last_atk)) / 60.0)
        hp = 9 if hurt_at is None or k < hurt_at else 7
        s = c_state(f, k, x, cx=cx, flip=flip, bottom=bottom, atk_cd=cd, bombs=bombs, hp=hp, two=two)
        m = h.step(f, s, bottom <= 0.031, True, t_game=f / 60.0)
        rows.append((k, round(x, 3), round(bottom, 2), m, lit_over))
        if m is not None:
            pending[f + lh.SEND_AHEAD] = m
    return h, rows


def test_off_by_default(monkeypatch):
    monkeypatch.delenv("SSBOT_FORUM_RUNE_LOWHOP", raising=False)
    monkeypatch.setenv("SSBOT_FORUM_V2", "1")
    try:
        assert not importlib.reload(lh).ENABLED
        monkeypatch.setenv("SSBOT_FORUM_RUNE_LOWHOP", "1")
        assert importlib.reload(lh).ENABLED
    finally:
        monkeypatch.delenv("SSBOT_FORUM_RUNE_LOWHOP", raising=False)
        monkeypatch.delenv("SSBOT_FORUM_V2", raising=False)
        importlib.reload(lh)


def test_hop_tables_rise_together_and_peak_by_hold():
    for H in range(9, 17):
        lo, hi = lh.HOP_LO[H], lh.HOP_HI[H]
        assert max(lo) <= max(hi) + 1e-9
        assert lo[0] < 0.05 and lo[-1] < 0.05
    apex = [max(lh.HOP_LO[H]) for H in range(9, 17)]
    assert apex == sorted(apex)
    assert 3.5 < max(lh.HOP_LO[12]) < 3.6 and max(lh.HOP_HI[12]) < lh.BODY_IDLE[0]


def test_hop_plan_lowest_hold_with_slack():
    # ring 1 seen at a = 0: lit 20-21 .. 27 with one frame each side, top 2.83 + 0.12
    p = lh.hop_plan([(19, 28, 2.95)], 0, range(9, 17), 3)
    assert p["H"] == 12 and p["lo"] == 6 and p["hi"] == 8 and p["P"] == 7
    # a lower threshold (she is 1.4 u off the bomb's centre): a lower hold
    thr = lh.bomb_top(3.65, 1.4) + 0.12
    q = lh.hop_plan([(19, 28, thr)], 0, range(9, 17), 3)
    assert q["H"] < 12
    # too late: no press frame clears
    assert lh.hop_plan([(5, 14, 2.95)], 0, range(9, 17), 3) is None


def test_slash_lower_edge():
    # from the ground she meets any body; 3.5 u up she does not meet the Idle body 2.2 u ahead
    assert lh.RuneLowHop()._slash_meets(2.2, 0.0, lh.BODY_IDLE[0])
    assert not lh.RuneLowHop()._slash_meets(2.2, 3.5, lh.BODY_IDLE[0])
    assert lh.RuneLowHop()._slash_meets(2.2, 2.5, lh.BODY_IDLE[0])
    assert not lh.RuneLowHop()._slash_meets(3.2, 0.0, lh.BODY_IDLE[0])      # beyond the x reach


def test_bomb_top():
    assert lh.bomb_top(3.65, 0.0) == pytest.approx(2.816, abs=0.01)
    assert lh.bomb_top(3.65, 2.5) == float("-inf")
    assert lh.bomb_top(3.65, 1.0) < lh.bomb_top(3.65, 0.2)


@pytest.mark.parametrize("flip", [False, True])
@pytest.mark.parametrize("x_rel0", [3.0, 4.3, 6.5])
def test_toy_cast_hops_over_ring1_and_slashes(flip, x_rel0):
    h, rows = simulate(x_rel0=x_rel0, flip=flip)
    run = (h.done + [h.run])[0]
    assert run.P is not None and run.H in (11, 12, 13), (run.plan, run.why)
    assert not any(r[4] for r in rows), [r for r in rows if r[4]]           # never under a lit bomb
    assert max(r[2] for r in rows) < lh.BODY_IDLE[0]                         # below its head
    presses = [p for p in run.presses]
    assert len(presses) >= 4
    assert all(b - a >= 19 for (a, *_), (b, *_) in zip(presses, presses[1:]))
    assert run.phase == "done" and run.why == "landed"


def test_hop_timed_from_ring1_appearance():
    for a1 in (SA + C1 + 9, SA + C1 + 10, SA + C1 + 12):
        h, rows = simulate(a1=a1)
        run = (h.done + [h.run])[0]
        assert a1 + 6 <= run.P <= a1 + 8
        assert not any(r[4] for r in rows)


def test_late_light_is_still_cleared():
    h, rows = simulate(lit_lead=21)
    assert not any(r[4] for r in rows)


def test_no_start_two_behind_far():
    h, _ = simulate(two=True)
    assert h.run is None and not h.done and h.why_not.get("two")
    h, _ = simulate(x_rel0=-3.0)
    assert h.why_not.get("behind")
    h, _ = simulate(x_rel0=11.0)
    assert h.why_not.get("far")


def test_abort_on_hp_loss():
    h, rows = simulate(hurt_at=30)
    assert h.done and h.done[0].phase == "abort" and h.done[0].why == "hurt"


def test_critical_during_hold():
    h, rows = simulate(n=SA + C1 + 25)
    run = h.run
    assert run is not None and run.phase == "hop"
    assert h.critical()


def test_no_air_slash_on_idle_inside_the_window():
    h, rows = simulate()
    run = (h.done + [h.run])[0]
    kc = SA + C1
    for k, air, d, bot in run.presses:
        st, tin = cast_state_at(k + 1)
        if air and st == "Idle":
            # an air press on the Idle body comes only after the hold and the covering bomb's window
            assert k >= run.P + run.H and k > kc + 10 + 20 + 7

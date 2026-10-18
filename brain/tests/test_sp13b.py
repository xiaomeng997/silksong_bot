"""Task 1v1 SP13b (forum.md 88): SSBOT_FORUM_TWO_BOMBS2 - the low hop against both casters' bombs (combat.rune_lowhop,
combat.rune_bombs.pending_rows) and SSBOT_FORUM_TWO_PMCAST - TWO_PUSHMID's cast route (combat.push_cast). Off:
unchanged."""
import copy

import numpy as np

from ssbot.combat import rune_bombs as rb
from ssbot.combat import rune_lowhop as lh
from ssbot.combat import slam_play as sp
from ssbot.combat import two_play as tp
from tests.test_sp8d import c_state


def test_defaults_off():
    assert not lh.BOMBS2
    assert not lh.RuneLowHop(two=True).b2
    c = lh.HopCfg()
    assert c.h_max == 16 and c.h_max2 == 26 and c.look2 == 45 and c.rise2 == 13
    # the extended holds continue the low hops' lowest lane (the same model): >= 2.95 u from j 11 to j 43 at H 26
    for H in range(17, 27):
        assert lh.HOP_LO[H][:12] == lh.HOP_LO[16][:12]
    a = [j for j, v in enumerate(lh.HOP_LO[26]) if v >= 2.95]
    assert a[0] == 11 and a[-1] == 43 and max(lh.HOP_LO[26]) == 5.48


def test_hop_plan2_single_split_tail():
    # two windows 15 frames apart: one full jump (H 19) clears both - the low hops cannot
    p = lh.hop_plan2([(30, 37, 3.0), (45, 51, 3.1)], 0, range(9, 27), 3)
    assert p["n"] == p["of"] == 2 and p["H"] > 16 and p["H2"] is None
    assert lh.hop_plan([(30, 37, 3.0), (45, 51, 3.1)], 0, range(9, 17), 3) is None
    # far apart: the first hop now, the second after the landing
    p = lh.hop_plan2([(30, 37, 3.0), (120, 127, 3.0)], 0, range(9, 27), 3)
    assert p["n"] == 1 and p["H"] <= 16 and p["H2"] == 0
    # in between (30 frames): no jump clears both, no second hop fits -> the first one, the umbrella for the rest
    p = lh.hop_plan2([(30, 37, 3.0), (60, 67, 3.0)], 0, range(9, 27), 3)
    assert p["n"] == 1 and p["H2"] == -1
    assert lh.hop_plan2([], 0, range(9, 27), 3) is None


def test_pending_rows():
    rows = rb.pending_rows([(1, 30.0, 7.4, "Spell Antic", 10 / 60), (2, 40.0, 7.4, "Idle", 0.0),
                            (3, 20.0, 7.4, "Cast 2", 0.1)])
    assert len(rows) and set(rows[:, 0]) == {1.0}
    xs = sorted(set(np.round(rows[:, 1], 2)))
    assert 30.0 in xs and 34.2 in xs and 25.8 in xs
    # ring 1 (x0 + 4.2): Cast 2 37.5 .. 41 frames from now, appears 9 .. 10.5 later, lights 19.5 .. 21.5 after that
    r1 = rows[np.isclose(rows[:, 1], 34.2)]
    assert r1[:, 4].min() <= 37.5 + 9 + 19.5 and r1[:, 5].max() >= 41 + 10.5 + 21.5 + 6
    assert abs(rows[0, 2] - (7.4 + rb.DV)) < 1e-9


def test_other_danger_cast_ok():
    s = c_state(5000, 10, 4.3, two=True)
    o = s["ents"][1]
    o["pos"] = [s["ents"][0]["pos"][0] - 8.0 + 1.0, 7.45]       # within 9 u of her
    o["fsms"] = [{"name": "Control", "state": "Spell Antic", "t": 0.1}]
    hx = sp.hero_x(s)
    assert tp.other_danger(s, s["ents"][0]["iid"], hx) == "other Spell Antic"
    assert tp.other_danger(s, s["ents"][0]["iid"], hx, cast_ok=True) is None


def _two_cast(k, other_k):
    s = c_state(5000 + k, k, 4.3, two=True)
    o = s["ents"][1]
    o["pos"] = [s["ents"][0]["pos"][0] - 4.3 - 6.5, 7.45]       # 6.5 u behind her, facing her
    o["flipX"] = True
    st, tin = ("Spell Antic", other_k / 60.0) if other_k >= 0 else ("Idle", 1.0)
    o["fsms"] = [{"name": "Control", "state": st, "t": tin}]
    return s


def test_b2_run_survives_the_other_cast():
    # off: the other one's Spell Antic within 9 u ends the run ("other"); BOMBS2: the run goes on with its bombs
    for b2, want in ((False, "abort"), (True, None)):
        h = lh.RuneLowHop(two=True)
        h.b2 = b2
        for k in range(0, 30):
            s = _two_cast(k, k - 20)
            h.step(5000 + k, s, True, True, t_game=(5000 + k) / 60.0, bombs=np.zeros((0, 6)) if b2 else None)
        if want is None:
            assert h.run is not None and h.run.phase == "stance"
            assert h.run.fcw, "the other caster's pending row covers her"
        else:
            assert h.run is None and h.done and h.done[-1].phase == "abort" and h.done[-1].why == "other"


def test_b2_fc_windows_and_plan():
    h = lh.RuneLowHop(two=True)
    h.b2 = True
    s = _two_cast(0, -1)
    h.step(5000, s, True, True, t_game=5000 / 60.0, bombs=np.zeros((0, 6)))
    r = h.run
    hx = sp.hero_x(s)
    # a forecast bomb right at her x lit 40 .. 46 frames from the STATE, and one 16 frames later
    h._bk = np.array([[99, hx, 3.65, lh.R, 40, 46], [99, hx + 0.1, 3.65, lh.R, 56, 62]], float)
    w = h._fc_windows(r, hx)
    assert len(w) == 2 and w[0][0] == r.k - 2 + 40 - 1 and w[1][1] == r.k - 2 + 62 + 1
    assert 99 in r.owners
    p = lh.hop_plan2(w, r.k, range(9, 27), 3)
    assert p is not None and p["n"] == 2 and p["H"] > 16          # one full jump clears both

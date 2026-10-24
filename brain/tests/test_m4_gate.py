"""Map v2 M4 G: the gate's per-episode check (ssbot.tools.m4_gate) on synthetic frames / log rows."""
from ssbot.tools import m4_gate as g


def _fr(f, x, act=0, st="Idle", hits=()):
    return {"f": f, "box": [x - 0.25, 0.0, x + 0.25, 2.0], "vel": (0.0, 0.0), "clip": "Idle", "act": act,
            "ents": [(7, g.CLAPPER, 30.0, 7.4, 0.0, 0.0, st, 0.1, [], 100, True)],
            "ev": [("hit", {"src": s, "type_key": g.CLAPPER, "dealt": 9}) for s in hits]}


def test_behaviour_still_and_flicker():
    fr = [_fr(f, 20.0, st="Roar") for f in range(0, 50)]                 # the intro: not engaged
    fr += [_fr(f, 20.0) for f in range(50, 400)]                          # stands still 349 frames
    b = g.behaviour(fr, None)
    assert b["still_f"] == 349 and b["engaged_f"] == 350
    fr2 = [_fr(f, 20.0 + 0.05 * f, act=(g.B_LEFT if (f // 3) % 2 else g.B_RIGHT)) for f in range(100)]
    b2 = g.behaviour(fr2, None)
    assert b2["lr_rev_60"] == 20 and b2["still_f"] < 10


def test_owner_at_and_switches():
    rows = [{"f": 10, "own": "plan", "m2": 0}, {"f": 11, "own": "m2", "m2": 1}, {"f": 14, "own": "plan", "m2": 0}]
    at = g.owner_at(rows)
    assert at(12) == "plan" and at(13) == "m2" and at(15) == "m2" and at(16) == "plan" and at(11) is None
    assert g.owner_switches(rows)[0] == 2


def test_moves_credit_the_press_owner():
    fr = [_fr(f, 20.0) for f in range(0, 20)]
    fr[5]["act"] = g.B_ATTACK | (1 << 19)
    fr[6]["act"] = g.B_ATTACK | (1 << 19)
    fr[9]["ev"] = [("hit", {"src": "DownSlash", "type_key": g.CLAPPER, "dealt": 9})]
    rows = [{"f": 1, "own": "plan", "m2": 0}, {"f": 3, "own": "m2", "m2": 1}, {"f": 4, "own": "plan", "m2": 0}]
    m = g.moves(fr, rows, None)
    assert m["strike"] == {"m2": 1} and m["hits"][0]["press"] == 5


def test_problems():
    e = {"outcome": "CLEAR", "f_kill": 100, "hp_before_kill": 0, "kill_s": 18.0, "beh": {"still_f": 20, "lr_rev_60": 3},
         "map2": {"rows": 900, "own_sw_60": 5}}
    assert g.problems(e, True) == []
    assert g.problems({**e, "hp_before_kill": 1}, True)
    assert g.problems({**e, "map2": {}}, True) and not g.problems({**e, "map2": {}}, False)
    assert g.problems({**e, "outcome": "TIMEOUT", "f_kill": None}, False)
    assert g.problems(e, True, exit_code=1)

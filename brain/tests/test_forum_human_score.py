"""ssbot.tools.forum_human_score: the 0.5x frame merge, the person's action classes, the planner-order rank and the
summary on synthetic ticks (no recording, no planner)."""
import numpy as np

from ssbot.ipc.framing import BIT
from ssbot.tools.forum_human_score import (GAME_MASK, KEY_NAMES, _merge_pair, _rank, action_class, situation,
                                           summarize_ticks)


def test_merge_pair_is_one_game_frame():
    a = {"f": 100, "dt": 1 / 120, "udt": 1 / 60, "ts": 0.5, "fs": 0, "ev": [{"k": "damage", "f": 100}],
         "input": {"mask": 1 << BIT["jump"]}}
    b = {"f": 101, "dt": 1 / 120, "udt": 1 / 60, "ts": 0.5, "fs": 1, "ev": [{"k": "hit", "f": 101}],
         "input": {"mask": 1 << BIT["attack"]}, "hero": {"pos": [1.0, 2.0]}}
    m = _merge_pair(a, b, 7, 0.5)
    assert m["f"] == 7 and m["_f_raw"] == 101
    assert abs(m["dt"] - 1 / 60) < 1e-12 and abs(m["udt"] - 1 / 60) < 1e-12 and m["ts"] == 1.0 and m["fs"] == 1
    assert [e["k"] for e in m["ev"]] == ["damage", "hit"] and all(e["f"] == 7 for e in m["ev"])
    assert m["input"]["mask"] == (1 << BIT["jump"]) | (1 << BIT["attack"])
    assert m["hero"] is b["hero"]
    # a hit stop (time scale 0) stays one: the kinematics read it as a world freeze, not as 0.5x slow motion
    z = _merge_pair(dict(a, dt=0.0, ts=0.0), dict(b, dt=0.0, ts=0.0), 8, 0.5)
    assert z["dt"] == 0.0 and z["ts"] == 0.0


def test_game_mask_drops_menu_buttons():
    assert GAME_MASK & (1 << BIT["enter"]) == 0 and GAME_MASK & (1 << BIT["jump"])
    assert GAME_MASK & (1 << BIT["right"]) and GAME_MASK & (1 << BIT["clawline"])


def test_action_class_order():
    base = {"hurt": False, "bind": False, "harpoon": False, "tool": False, "dash_attack": False, "wall": False,
            "glide": False, "down_slash": False, "air_attacks": 0}
    assert action_class(base) == "other"
    assert action_class(dict(base, air_attacks=2)) == "air_combo"
    assert action_class(dict(base, wall=True, harpoon=True)) == "harpoon"
    assert action_class(dict(base, hurt=True, harpoon=True)) == "hurt"


def test_rank_and_first_key():
    n = 4
    keys = [np.zeros(n) for _ in KEY_NAMES]
    J = np.array([5.0, 3.0, 4.0, 1.0])
    keys[KEY_NAMES.index("J")] = -J
    V = np.array([True, True, False, True])
    keys[KEY_NAMES.index("V")] = ~V
    pool = np.arange(n)
    # row 2 (V False) is behind every row with V True whatever its J
    assert _rank(keys, pool, 2) == (4, "V")
    assert _rank(keys, pool, 0) == (1, None)
    assert _rank(keys, pool, 1) == (2, "J")
    # the planner left row 3 unknown: S = 1 from the verdict puts it last
    assert _rank(keys, pool, 3, over={KEY_NAMES.index("S"): 1})[1] == "S"


def _tick(err, forced, S, hind, pick_hind=-1, same=False, hits=(0.0, 1.0), defending=()):
    return {"best": ["WAIT+idle", err, err], "kerr": [err, err], "forced": forced, "same_as_pick": same,
            "person": {"hurt": False, "bind": False, "harpoon": err > 1, "tool": False, "dash_attack": False,
                       "wall": False, "glide": False, "down_slash": False, "air_attacks": 0},
            "hit_in": -1, "pick": ["MOVE(R)+runR", 0, pick_hind], "chosen_moved": False,
            "vb": {"S": S, "src": "stage1" if S else None, "hind": hind, "ok": True, "unmod": False, "known": True,
                   "pl_S": int(S), "rank": 3, "why": "J", "keys": {"sk_n": 0, "sk_c": 0.0},
                   "layers": {"cats": {"window": [10, 1]}, "need": ["window"],
                              "groups": [["com_win", "Song Pilgrim 01", "EN_CHARGE", 10, 1]]} if S else None},
            "vk": {"S": S, "src": None, "hind": hind, "unmod": False},
            "pick_keys": {"sk_n": 0, "sk_c": 0.0},
            "J": {"w": [10.0, 0.6, 0.15, 0.6, 3.0, 0.3, 0.2], "best": [hits[0], 0, 0, -2.0, -0.1, 0, 1],
                  "pick": [hits[1], 0, 0, -1.0, -0.1, 1, 1], "cont": [0.0, 0.0], "tv": None},
            "ctx": {"near": [["Song Reed", "RE_DEFEND", "Defend", 3.0, 1.0, 2.0]], "defending": list(defending),
                    "flier_above": False}}


def test_summary_counts():
    T = [_tick(0.1, False, False, -1), _tick(0.1, False, False, -1, defending=("Song Reed",)),
         _tick(0.1, True, True, -1), _tick(0.1, True, True, 5), _tick(2.0, False, False, -1)]
    s = summarize_ticks(T, 0.35)
    assert s["ticks"] == 5 and s["match"]["close"] == 0.8
    assert s["outside"]["by_action"]["harpoon"][0] == 1
    m = s["matched"]
    assert m["n"] == 4 and m["unsafe"] == 0.5 and m["false_alarm"] == 0.25 and m["false_alarm_of_unsafe"] == 0.5
    assert m["fa_need"] == {"window": 1.0}
    sd = s["safe_differ"]
    assert sd["n"] == 2 and sd["worst_term"]["hit"] == 1.0
    assert situation(T[1]) == "waits_by_defender"

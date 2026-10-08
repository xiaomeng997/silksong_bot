"""Forum plan R8 (clash): the Wanderer crest's kinematics (AB_DOWN_SLASH), the parry-recover event, the clash table
and its builder, the swing finder the EV_CLASH branch uses."""
from pathlib import Path

import numpy as np
import pytest

from ssbot.combat.forum_planner import K_DOWN, K_SIDE, K_UP, ClashTable, swings
from ssbot.knowledge import kinematics as kin
from ssbot.tools.forum_clash_stats import build_table, slot_of, wilson_ub

KDIR = Path(__file__).resolve().parents[2] / "knowledge" / "1.0.30000" / "kinematics"
FLOOR = 3.0


@pytest.fixture(scope="module")
def arena():
    return kin.Terrain2D.from_boxes([(10.0, 0.0, 53.0, FLOOR), (10.0, 0.0, 14.01, 30.0), (48.99, 0.0, 53.0, 30.0)])


@pytest.fixture(scope="module")
def wanderer():
    return kin.HeroParams.load(KDIR / "hero_wanderer_forum.json")


@pytest.fixture(scope="module")
def reaper():
    return kin.HeroParams.load(KDIR / "hero_reaper_forum.json")


def _onsets(flags: np.ndarray) -> list[int]:
    a = (flags & kin.F_ATTACKING) != 0
    return [int(k) for k in range(1, len(a)) if a[k] and not a[k - 1]]


def test_wanderer_params(wanderer, reaper):
    assert wanderer.crest == "Wanderer"
    assert (wanderer.attack_duration, wanderer.attack_cooldown, wanderer.attack_recovery) == (0.25, 0.3, 0.1)
    assert wanderer.abilities & kin.AB_DOWN_SLASH and not wanderer.abilities & kin.AB_RPR_DOWN
    assert not reaper.abilities & kin.AB_DOWN_SLASH
    # every other Forum loadout bit is the Reaper's
    assert wanderer.abilities & ~(kin.AB_DOWN_SLASH | kin.AB_RPR_DOWN) == reaper.abilities & ~kin.AB_RPR_DOWN


def test_down_attack_is_a_slash_for_wanderer(wanderer, reaper, arena):
    m = np.zeros((1, 30), np.int64)
    m[0, :8] = kin.B_JUMP
    m[0, 10:13] = kin.B_ATTACK | kin.B_DOWN
    for p, slash in ((wanderer, True), (reaper, False)):
        S = kin.initial_state(p, 30.0, FLOOR + p.foot)
        r = kin.rollout(S, m, p, arena)
        modes = set(int(x) for x in r.mode[0])
        if slash:
            assert _onsets(r.flags[0]), "the Wanderer down attack swings (cState.attacking)"
            assert kin.M_RPR_DS not in modes and kin.M_DS_ANTIC not in modes
        else:
            assert kin.M_RPR_DS in modes


def test_parry_recover_lets_the_next_swing_out(wanderer, arena):
    S = kin.initial_state(wanderer, 30.0, FLOOR + wanderer.foot)
    m = np.zeros((1, 40), np.int64)
    m[0, 0:2] = kin.B_ATTACK
    m[0, 12:14] = kin.B_ATTACK            # 0.2 s later: inside the 0.3 s cooldown
    ev = np.zeros((1, 40), np.int64)
    plain = _onsets(kin.rollout(S, m, wanderer, arena).flags[0])
    ev[0, 2 + 6] = kin.EV_PARRY_RECOVER   # a clash on the swing's first frames, recovered 0.1 s later
    parried = _onsets(kin.rollout(S, m, wanderer, arena, events=ev).flags[0])
    assert len(plain) >= 1 and len(parried) >= 2
    assert parried[0] == plain[0]
    # the second press is taken at once after the recover (without it: queued until the cooldown ends)
    assert parried[1] < (plain[1] if len(plain) > 1 else 99)
    assert parried[1] <= 15


def test_unused_bits_leave_reaper_rollouts_alone(reaper, arena):
    rng = np.random.default_rng(3)
    S = kin.initial_state(reaper, 30.0, FLOOR + reaper.foot)
    bits = (kin.B_ATTACK, kin.B_JUMP, kin.B_LEFT, kin.B_RIGHT, kin.B_UP, kin.B_DOWN, kin.B_DASH)
    m = np.zeros((16, 36), np.int64)
    for i in range(16):
        for k in range(0, 36, 4):
            m[i, k:k + 4] = sum(b for b in bits if rng.random() < 0.3)
    a = kin.rollout(S, m, reaper, arena, variants="bounds_lo")
    # a parry-recover event where nothing attacks changes nothing
    ev = np.zeros_like(m)
    ev[:, 0] = kin.EV_PARRY_RECOVER
    S2 = kin.initial_state(reaper, 30.0, FLOOR + reaper.foot)
    m2 = m.copy()
    m2[:, :12] &= ~kin.B_ATTACK
    b0 = kin.rollout(S2, m2, reaper, arena, variants="bounds_lo")
    b1 = kin.rollout(S2, m2, reaper, arena, variants="bounds_lo", events=ev)
    assert np.array_equal(b0.bound, b1.bound)
    assert a.bound.shape == b0.bound.shape


def test_swings_kinds(wanderer, arena):
    S = kin.initial_state(wanderer, 30.0, FLOOR + wanderer.foot)
    m = np.zeros((1, 60), np.int64)
    m[0, 0:2] = kin.B_ATTACK | kin.B_RIGHT
    m[0, 20:22] = kin.B_ATTACK | kin.B_UP
    m[0, 30:40] = kin.B_JUMP
    m[0, 44:46] = kin.B_ATTACK | kin.B_DOWN
    lat, _ = __import__("ssbot.combat.holdfilter", fromlist=["hold_filter_jit"]).hold_filter_jit(
        m, kin.HoldState.idle(1))
    r = kin.rollout(S, lat, wanderer, arena)
    sw = swings(r.flags[0], r.mode[0], lat[0], r.box[0], 1, True)
    kinds = [k for _, k, _ in sw]
    assert kinds[:3] == [K_SIDE, K_UP, K_DOWN], sw


def test_clash_table_and_builder(tmp_path):
    rows = []
    for out, n in (("clash", 30), ("hit", 1), ("neither", 9)):
        rows.append({"crest": "Wanderer", "type": "Song Pilgrim 01", "family": "EN_SLASH", "slot": "normal",
                     "side": "front", "clashable_collider_on": True, "n": n, out: n})
    rows.append({"crest": "Reaper", "type": "Song Pilgrim 01", "family": "EN_SLASH", "slot": "normal",
                 "side": "behind", "clashable_collider_on": True, "n": 50, "hit": 50})
    rows.append({"crest": "Reaper", "type": "Song Heavy Sentry", "family": "CC_SLAM", "slot": "normal",
                 "side": "front", "clashable_collider_on": False, "n": 50, "neither": 50})
    rows.append({"crest": "Reaper", "type": "Song Reed", "family": "RE_IDLE", "slot": "up",
                 "side": "front", "clashable_collider_on": False, "n": 50, "clash": 50})
    tab = build_table([{"union_setups": rows}], min_n=10)
    k = "Song Pilgrim 01|EN_SLASH|side"
    assert tab["p_fail"][k]["n"] == 40 and tab["p_fail"][k]["hit"] == 1      # the behind rows are left out
    assert tab["p_fail"][k]["p_fail"] == round(wilson_ub(1, 40), 4)
    assert "Song Heavy Sentry|CC_SLAM|side" in tab["left_out"]
    assert "Song Reed|RE_IDLE|up" in tab["left_out"]
    p = tmp_path / "clash.json"
    import json
    p.write_text(json.dumps(tab), encoding="utf-8")
    ct = ClashTable.load(p)
    assert ct.p_fail("Song Pilgrim 01", "EN_SLASH", "side") == pytest.approx(wilson_ub(1, 40), abs=1e-4)
    assert ct.p_fail("Song Pilgrim 01", None, "side") is None
    assert ct.p_fail("Song Heavy Sentry", "CC_SLAM", "side") is None
    assert slot_of("UpSlash", False) == "up" and slot_of("DownSlashAlt", False) == "down"
    assert slot_of("SlashAlt", False) == "normal" and slot_of("Slash", True) == "wall"

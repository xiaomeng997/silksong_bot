"""Map v2 M4a probe (ssbot.probes.m4_probe): the open-loop trials fit the pre-spawn window and press what they say;
the closed-loop generators run against synthetic states without a game."""
import random

from ssbot.probes import m4_probe as mp
from ssbot.probes.m0_probe import M_A, M_CLAW, M_D, M_DASH, M_J, M_L, M_R, PRE_SPAWN_F


def _first(m, bit, start=0):
    for i in range(start, len(m)):
        if m[i] & bit:
            return i
    return None


def test_open_loop_trials():
    rng = random.Random(5)
    for _ in range(300):
        for fn in (mp.trial_adash, mp.trial_adash_claw, mp.trial_gdash_jump, mp.trial_dash_end):
            d = rng.choice((-1, 1))
            m, p = fn(rng, d)
            assert 10 < len(m) <= PRE_SPAWN_F
            assert all(isinstance(x, int) and x >= 0 for x in m)
            if fn is mp.trial_adash:
                k = p["k"]
                assert _first(m, M_DASH) == k
                assert bool(m[k] & M_J) == p["jh"]
                assert not (m[k] & (M_L if d > 0 else M_R))
                if p["cancel"] == "claw":
                    assert _first(m, M_CLAW) == k + p["c"]
                if p["cancel"] == "datk":
                    f = k + p["c"]
                    assert m[f] & M_D and m[f] & M_A and not m[f] & (M_L | M_R)
            if fn is mp.trial_adash_claw:
                fc = _first(m, M_CLAW)
                assert fc == p["k"] + p["c"]
                assert (_first(m, M_DASH) == p["k"]) == p["pre"] or not p["pre"]
                assert _first(m, M_DASH, fc) == fc + 32 + p["j"]


class _Pd:
    def __init__(self):
        self.calls = []

    def set(self, **kv):
        self.calls.append(kv)
        return {}


class _R:
    def __init__(self):
        self.pd = _Pd()


def _state(f, hx, cx, st="Idle", clip="Idle", acc=True, ground=True, yb=0.0, vy=0.0):
    from ssbot.knowledge import kinematics as kin
    names = kin.cstate_names()
    i = names.index("onGround")
    cs = [0] * ((len(names) + 63) // 64)
    if ground:
        cs[i >> 6] |= 1 << (i & 63)
    box = [hx - 0.25, 3.015 + yb, hx + 0.25, 3.015 + yb + 2.08]
    ent = {"type_key": "Song Heavy Sentry", "hp": 200, "pos": [cx, 4.5], "fsms": [{"name": "Control", "state": st}],
           "colliders": [{"kind": "box", "name": "Song Heavy Sentry", "enabled": True,
                          "verts_world": [cx - 0.8, 3.0, cx + 0.8, 3.0, cx + 0.8, 6.9, cx - 0.8, 6.9]}]}
    return {"f": f, "hero": {"box": box, "vel": [0, vy], "anim": {"clip": clip}, "hero_accepting_input": acc,
                             "cstate": cs, "health": 7}, "ents": [ent]}


def _drive(gen, states):
    next(gen)
    out = []
    try:
        for s in states:
            out.append(gen.send(s))
    except StopIteration as e:
        return out, e.value
    return out, None


def test_hook_touch_runs():
    rng = random.Random(3)
    R = _R()
    g = mp.gen_hook_touch(rng, R)
    # idle at 4 u, then the Harpoon clips for 30 frames, then control
    seq = [_state(100 + i, 30.0, 34.0) for i in range(5)]
    seq += [_state(105 + i, 30.0, 34.0, clip="Harpoon Throw", acc=False, ground=False) for i in range(30)]
    seq += [_state(135 + i, 31.0, 34.0, clip="Airborne", ground=False) for i in range(200)]
    masks, res = _drive(g, seq)
    assert res is not None and res["act"] in ("dash", "walk", "none")
    assert any(m & M_CLAW for m in masks)
    assert R.pd.calls and "isInvincible" in R.pd.calls[0]
    if res["act"] == "dash":
        assert any(m & M_DASH for m in masks)


def test_bounce_jump_runs():
    rng = random.Random(4)
    g = mp.gen_bounce_jump(rng, _R())
    hx = 34.0 + random.Random(4).uniform(-1.0, 1.0)      # the trial's offset (its first draw): she is there
    seq = [_state(100 + i, hx, 34.0) for i in range(3)]
    # the jump: up, then falling onto its top (box top at 6.9 - 3.015 = 3.885 above the floor)
    seq += [_state(103 + i, hx, 34.0, clip="Airborne", ground=False, yb=min(0.3 * i, 5.0), vy=5.0) for i in range(20)]
    seq += [_state(123 + i, hx, 34.0, clip="Airborne", ground=False, yb=5.0 - 0.2 * i, vy=-8.0) for i in range(150)]
    masks, res = _drive(g, seq)
    assert res is not None and "k" in res and res["k"] >= 2
    i_ds = _first(masks, M_D)
    assert i_ds is not None and masks[i_ds] & M_A
    assert _first(masks, M_J, i_ds) == i_ds + res["k"]

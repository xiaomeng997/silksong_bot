"""Actual-hook bounce ownership regression from reviewed Opus Task150b: the real vault engine on the patched table
(lock / timeout / HP / bomb / bounce successor) and the B2 hook-bounce handover with its negatives. No game, no P."""
import json
from pathlib import Path
from types import SimpleNamespace as NS

import numpy as np
import pytest

import ssbot
from ssbot.combat import knife_chain_vault as V, knife_chain_vault_native as VN
from ssbot.combat.knife_chain_air_native import NativeManualAirChain
from ssbot.combat.knife_chain_b2 import NativeChainB2
from ssbot.combat.knife_chain_commitment import MoveInstance
from ssbot.combat.knife_chain_eval import Run
from ssbot.knowledge import kinematics as km
from tests.test_knife_chain_b2 import raw

BIT = 1 << km.cstate_names().index("downSpikeBouncing")
MOVE = MoveInstance(7, 990, "VAULT_IDLE")
BODY = [29.0, 7.0, 31.0, 10.0]                     # target body box (x0, y0, x1, y1)


def scene(f, target="Evade Scuttle", clip="Harpoon Antic", accepting=False, bits=False, counter=0, hits=(), health=7,
          hx=35.0):
    s = raw(f)
    s["hero"]["anim"]["clip"] = clip
    s["hero"]["hero_accepting_input"] = accepting
    s["hero"]["health"] = health
    s["hero"]["pos"] = [hx, 6.0]
    s["hero"]["box"] = [hx - 0.25, 5.0, hx + 0.25, 7.08]
    s["hero"]["cstate"] = [BIT if bits else 0, 0]
    s["hero"]["cstate_int"] = [0, counter, 0, 0]
    t = s["ents"][0]
    t["fsms"][0]["state"] = target
    x0, y0, x1, y1 = BODY
    t["colliders"] = [{"name": "Song Heavy Sentry", "enabled": True, "verts_world": [[x0, y0], [x1, y0], [x1, y1], [x0, y1]]}]
    s["ents"].append({"iid": 8, "type_key": "Song Heavy Sentry", "hp": 130, "flipX": False, "pos": [40., 7.449],
                      "fsms": [{"name": "Control", "state": "Air", "t": 0.}]})
    s["ev"] = [{"f": f, "k": "hit", "d": {"ent": ent, "src": src}} for src, ent in hits]
    return s


def far_lock_runner(locked, bounced=False, f_press=1001, over_dir=-1):
    r = VN.load_runner()
    v = dict(r.chains[V.CHAIN].vars)
    v.update(iid=7, face=1, over_dir=over_dir, req={"x_end": 26.0, "nogo": [], "near": None,
                                                    "far": {"hop": 3, "claw_after": 3, "d": 22, "p": 22}},
             F_open=1000, f_open=998, hp0=7, side_hits=[], cs=NS(f_press=f_press), _hook_locked=locked,
             bounced=bounced, bounce_f=1004 if bounced else None)
    r.run = Run(V.CHAIN, "far_lock", v)
    return r


def step(r, s, accepting=False, bombs=None):
    return r.step(s["f"], s, False, accepting, s["f"] / 60., None, None, None,
                  np.zeros((0, 6)) if bombs is None else bombs)


# ---- T1: the real engine on the patched table ----
def test_locked_hook_keeps_far_lock_when_the_target_scuttles():
    r = far_lock_runner(True)
    step(r, scene(1004))
    assert r.run is not None and r.run.link == "far_lock"


def test_unlocked_hook_keeps_the_original_hand_back():
    r = far_lock_runner(False)
    step(r, scene(1004))
    assert r.run is None and "target left" in r.done[-1].v["why"]


def test_lock_keeps_timeout_hurt_and_path_bomb():
    r = far_lock_runner(True, f_press=950)                       # claw_press > 45
    step(r, scene(1004))
    assert r.run is None and "no control return" in r.done[-1].v["why"]
    r = far_lock_runner(True)
    step(r, scene(1004, health=5))
    assert r.run is None and "hurt" in r.done[-1].v["why"]
    r = far_lock_runner(True)
    step(r, scene(1004), bombs=np.array([[0., 30.0, 0., 0.5, 0., 0.]]))
    assert r.run is None and "bomb" in r.done[-1].v["why"]


def test_lock_does_not_widen_other_watch_rules():
    r = far_lock_runner(True)
    r.run.v["unlocked_hit_f"] = 1003                              # an unlocked non-Harpoon hit still hands back
    step(r, scene(1004))
    assert r.run is None and "jump cast" in r.done[-1].v["why"]


def test_hook_bounce_over_the_body_starts_over():
    r = far_lock_runner(False, bounced=True)
    s = scene(1004, target="Walk", clip="Harpoon Catch", accepting=True, bits=True, hx=30.0)
    s["hero"]["pos"], s["hero"]["box"] = [30.0, 11.5], [29.75, 10.5, 30.25, 12.58]   # above the body top (10)
    step(r, s, accepting=True)
    assert r.run is not None and r.run.link == "over"


def test_hook_bounce_beside_the_body_hands_back():
    r = far_lock_runner(False, bounced=True)
    step(r, scene(1004, target="Walk", clip="Harpoon Catch", accepting=True, bits=True, hx=30.0), accepting=True)
    assert r.run is None and "real hook bounce off the body" in r.done[-1].v["why"]


@pytest.mark.parametrize("hx", [35.0, 25.0])
def test_hook_bounce_off_the_body_hands_back(hx):
    r = far_lock_runner(False, bounced=True)
    step(r, scene(1004, target="Walk", clip="Harpoon Catch", accepting=True, bits=True, hx=hx), accepting=True)
    assert r.run is None and "real hook bounce off the body" in r.done[-1].v["why"]


def test_no_bounce_keeps_the_original_control_return_to_far_strike():
    r = far_lock_runner(False)
    step(r, scene(1020, target="Idle", clip="Airborne", accepting=True), accepting=True)
    assert r.run is not None and r.run.link == "far_strike"


# ---- T2: B2 hook-bounce handover on fixed synthetic transactions ----
def committed(sent=(1001, 1002)):
    n = NativeManualAirChain(runner_factory=VN.load_runner, probe_ref="hook150")
    n.begin(scene(1000, target="Idle", clip="Airborne", accepting=True))
    n.commitment = {"move": MOVE, "origin": 1000, "ta": 0., "predicted_bounce": None, "fixed_hook": False, "manual_air": True}
    n._hook_start = {"move": MOVE, "origin": 1000, "targets": (1001, 1002), "sent_targets": set(sent), "seen_frame": None}
    n.runner.run = far_lock_runner(True).run
    return n


def feed(n, seq):
    for s in seq:
        n.observe(s)
    return n


def seq(hits=(("Harpoon Damager", 7),), bounce=True, pre_bits=False, counter=False, hit_at=1003):
    """1001 Harpoon Antic (seen), hit at hit_at, 1005 control + marker (bit or counter) unless bounce is False."""
    out = []
    for f in range(1001, 1006):
        last = f == 1005
        out.append(scene(f, clip="Harpoon Catch" if last else "Harpoon Antic", accepting=last,
                         bits=pre_bits or (last and bounce and not counter), counter=8 if (last and bounce and counter) else 0,
                         hits=hits if f == hit_at else ()))
    return out


def handed(n):
    return n.commitment is None and n.post_context is not None and n.post_context.get("kind") == "hook_bounce"


@pytest.mark.parametrize("counter", [False, True])
def test_target_harpoon_hit_then_new_marker_hands_back_as_hook_bounce(counter):
    n = feed(committed(), seq(counter=counter))
    assert n._hook_start is None and handed(n)
    assert n.post_context["hook_hit"] == 1003 and n.post_context["bounce"] == 1005 and n.post_context["hit"] is None
    assert n._hit is None and n._accepted is None and n._press is None
    assert n.runner.run.v["bounced"] is True and n.runner.run.v["bounce_f"] == 1005
    assert [e["frame"] for e in n.events if e["event"] == "b2_real_hook_bounce_handback"] == [1005]
    n._recover("fixture: a later successor abort", 1007)          # nothing left to blame on the vault move
    assert not n._failure_exposures and MOVE not in n._failed_hook_moves


@pytest.mark.parametrize("hits", [(("Harpoon Damager", 8),), (("Harpoon Damager", 7), ("Harpoon Dash Damager", 8)),
                                  (("Needle", 7),), (("DownSlash", 7),)])
def test_wrong_mixed_or_non_harpoon_hit_never_hands_back(hits):
    n = feed(committed(), seq(hits=hits))
    assert n.commitment is not None and n.post_context is None


def test_no_new_marker_never_hands_back():
    n = feed(committed(), seq(pre_bits=True))                       # the bit was on since the hook was seen
    assert n.commitment is not None and n.post_context is None
    n = feed(committed(), seq(bounce=False))                        # control returned, no bounce
    assert n.commitment is not None and n.post_context is None


def test_hit_before_the_hook_was_seen_does_not_count():
    s = seq(hit_at=None)
    s[0]["ev"] = [{"f": 999, "k": "hit", "d": {"ent": 7, "src": "Harpoon Damager"}}]
    n = feed(committed(), s)
    assert n.commitment is not None and n.post_context is None


def test_pending_hook_never_hands_back_or_locks():
    n = committed(sent=())                                          # no successful CLAW send
    feed(n, seq())
    assert n._hook_start["seen_frame"] is None and "hook_bounce" not in n._hook_start
    assert n.commitment is not None and n.post_context is None


def test_other_family_is_untouched():
    n = committed()
    other = MoveInstance(7, 990, "RUNE_TRANSFER")
    n.commitment = {**n.commitment, "move": other}
    n._hook_start = {**n._hook_start, "move": other}
    feed(n, seq())
    assert n.post_context is None and "hook_bounce" not in n._hook_start

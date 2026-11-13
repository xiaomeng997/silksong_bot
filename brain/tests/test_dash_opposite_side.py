"""The person 11-13 (rx411 bout 1 f5590, "大黄蜂不砍N，跑到墙边躲着"): a knife-chain dash impulse against a side key still in flight waits.

5589 the planner's MOVE(L) for 5591; 5590 the transfer's DASH+R for 5592 passed its lock scan (the modelled dash went LEFT, away from N, so
nothing was met): the game turned her at 5592 and dashed left into the wall. Live chain dash starts of five 50s
(s312/b_items/dash_side_table.txt): 36 of the 42 that went the other way had an opposite side key in flight. NativeManualAirChain.
_opposite_in_flight refuses such an impulse inside _dash_lock_scan before any roll; the owners' refused-dash paths then send the side key
alone (ground walk / dash links and the waypoint), keep the current owner (a fresh air start), or wait a tick (an active transfer Run)."""
from dataclasses import replace
from types import SimpleNamespace as NS

import numpy as np

from ssbot.combat import knife_chain_transfer as T
from ssbot.combat.knife_chain_air_native import NativeManualAirChain
from ssbot.combat.knife_chain_format import MASK_NAMES as B
from ssbot.knowledge import kinematics as K
from tests.test_dash_lock179 import FC, chain, geometry, ground_dash_scene
from tests.test_shared_strike_approach import flight
from tests.test_target_entry_attack import native

OPP = NativeManualAirChain._opposite_in_flight


def sim_of(prefix, latched=0, desired=0, face=None):
    """face: her facing in the model start (+1 right, -1 left); None: no start (facing unknown)."""
    hold = K.HoldState.from_hf({"latched": latched, "desired": desired})
    out = NS(prefix=np.asarray(prefix, np.int64), hold=hold)
    if face is not None:
        S = np.zeros(K.K)
        S[K.FACE] = face
        out.start = S
    return out


# ---- the rule ----

def test_an_opposite_side_key_in_flight_holds_the_impulse_back_while_she_faces_its_side():
    turn = OPP(sim_of([B["L"]], face=1), B["DASH"] | B["R"])
    assert turn["opposite_in_flight"] and turn["in_flight"] == [B["L"]] and not turn["queued_press"] and turn["face"] == 1
    assert OPP(sim_of([B["R"] | B["J"]], face=-1), B["DASH"] | B["L"])["opposite_in_flight"]
    assert OPP(sim_of([B["L"]]), B["DASH"] | B["R"])["face"] is None          # facing unknown: held back all the same


def test_facing_away_already_lets_it_go():
    # no turn comes from the key in flight; the impulse's own side key turns her (87 of 108 such live dashes went the key's way)
    assert OPP(sim_of([B["L"]], face=-1), B["DASH"] | B["R"]) is None
    assert OPP(sim_of([B["R"]], face=1), B["DASH"] | B["L"]) is None


def test_the_same_side_no_side_or_both_sides_in_flight_do_not():
    assert OPP(sim_of([B["R"]]), B["DASH"] | B["R"]) is None
    assert OPP(sim_of([0]), B["DASH"] | B["R"]) is None
    assert OPP(sim_of([B["L"] | B["R"]]), B["DASH"] | B["R"]) is None      # both held: no turn key of its own
    assert OPP(sim_of([B["L"]]), B["DASH"]) is None                         # an impulse without a side key goes the way she faces


def test_a_press_queued_in_the_hold_filter_counts_when_no_side_key_is_in_flight():
    assert OPP(sim_of([0], latched=0, desired=B["L"]), B["DASH"] | B["R"])["queued_press"]
    assert OPP(sim_of([0], latched=B["L"], desired=B["L"]), B["DASH"] | B["R"]) is None     # held: no new turn
    assert OPP(sim_of([0], latched=B["L"], desired=0), B["DASH"] | B["R"]) is None          # released
    assert OPP(sim_of([B["R"]], latched=0, desired=B["L"]), B["DASH"] | B["R"]) is None     # her own side key comes after it


def test_the_last_side_key_before_the_impulse_decides():
    # a given row (the air approach): the keys before its first dash press come after the prefix
    rows = np.array([B["R"], B["L"], B["DASH"] | B["R"], B["L"]], np.int64)
    turn = OPP(sim_of([0]), B["DASH"] | B["R"], rows)
    assert turn["in_flight"] == [0, B["R"], B["L"]]                          # the L after the impulse is no part of it
    assert OPP(sim_of([0]), B["DASH"] | B["R"], rows[[1, 0, 2]]) is None    # L then R before it: R is the last
    # test_return_air316 A2 2770: the planner's DASH+L in flight, then the approach's own R keys before its air dash
    assert OPP(sim_of([B["DASH"] | B["L"]]), B["DASH"] | B["R"], np.array([B["R"], B["R"], B["DASH"] | B["R"]])) is None
    assert OPP(sim_of([B["L"], 0]), B["DASH"] | B["R"])["opposite_in_flight"]   # a key with no side key turns nothing


def test_the_lock_scan_refuses_it_before_any_roll():
    r, s, sim = flight()
    _, p, _, mask = T.propose(r, s, 0., sim, 8, False, np.zeros((0, 6)), set())
    assert mask & B["DASH"] and mask & B["R"]
    scans = []
    geo = NS(scan=lambda q: scans.append(q) or NS(complete=True, contacts=()))
    lock, info = native()._dash_lock_scan(replace(sim, prefix=np.array([B["L"]], np.int64)), p, mask, 0., geo, "air")
    assert lock is None and info["opposite_in_flight"] and info["dash_mask"] == mask and not scans
    lock, info = native()._dash_lock_scan(sim, p, mask, 0., geo, "air")       # nothing opposite in flight: scanned as before
    assert lock is not None and "opposite_in_flight" not in info and scans


# ---- the owners ----

def _opposite_prefix(monkeypatch, n, sim, key):
    sim = replace(sim, prefix=np.array([key], np.int64))
    monkeypatch.setattr(n, "queued_prefix", lambda *a: (key, "known test prefix"))
    return sim


def test_a_fresh_ground_dash_runs_its_side_key_alone_this_tick(monkeypatch):
    # rx411 5590 itself: a fresh walk / dash link on the ground whose dash is due, L in flight, its DASH+R
    n, s, sim = ground_dash_scene(monkeypatch)
    sim = _opposite_prefix(monkeypatch, n, sim, B["L"])
    geometry(monkeypatch)
    offer = n._transfer_offer(s, 0., sim, FC, NS(target=8), True)
    assert offer is not None and not offer.mask & B["DASH"] and offer.mask & B["R"]
    refused = next(e for e in n.events if e["event"] == "rune_transfer_dash_refused")
    assert refused["opposite_in_flight"] and refused["owner"] == "same transfer Run runs without the dash this tick"
    assert offer.path.assumptions["dash_refused"]


def test_an_active_air_run_waits_a_tick_instead_of_handing_back(monkeypatch):
    r, s, sim = flight()
    n = chain(monkeypatch, r)
    sim = _opposite_prefix(monkeypatch, n, sim, B["L"])
    geometry(monkeypatch)
    recovered = []
    monkeypatch.setattr(n, "_recover", lambda reason, f: recovered.append((reason, f)))
    offer = n._transfer_offer(s, 0., sim, FC, NS(target=8), False)
    assert not recovered and offer is not None and offer.stage == "active"
    assert not offer.mask & B["DASH"] and offer.mask & B["R"]
    refused = next(e for e in n.events if e["event"] == "rune_transfer_dash_refused")
    assert refused["owner"] == "same transfer Run waits a tick: an opposite side key in flight"


def test_a_fresh_air_start_leaves_the_keys_with_their_current_owner(monkeypatch):
    r, s, sim = flight()
    r.run = None
    n = chain(monkeypatch, r)
    sim = _opposite_prefix(monkeypatch, n, sim, B["L"])
    geometry(monkeypatch)
    assert n._transfer_offer(s, 0., sim, FC, NS(target=8), False) is None
    refused = next(e for e in n.events if e["event"] == "rune_transfer_dash_refused")
    assert refused["opposite_in_flight"] and refused["owner"] == "current owner keeps the keys"
    assert n.runner.run is None and n.commitment is None


def test_the_waypoint_run_sends_its_side_key_alone(monkeypatch):
    # test_l2_plan182's waypoint offer on a real model: 30 -> 39 by f132 takes the dash (DASH+R). With L in flight its own route model
    # already finds no way in time from there, so its key choice is held at that DASH+R here: the refused-dash path is what is tested
    from ssbot.combat import knife_chain_waypoint as WP
    from ssbot.combat.air_chain import ChainSim
    from tests.test_l2_plan182 import PARAMS, TERRAIN, _offer, hero_state
    from ssbot.knowledge import kinematics as kin
    plain, _ = _offer(monkeypatch, 30., 39., by=32, lock="pass")             # (the fixture's stand-in for a clear lock scan)
    assert plain is not None and plain.mask == B["DASH"] | B["R"]             # nothing in flight: the dash goes
    monkeypatch.setattr(WP, "next_mask", lambda sim, goal, f: (B["DASH"] | B["R"], "dash"))
    sim = ChainSim(hero_state(30.), np.array([B["L"]], np.int64), kin.HoldState.idle(1), PARAMS, TERRAIN, 100, 100)
    out, ch = _offer(monkeypatch, 30., 39., by=32, sim=sim)                  # the real _dash_lock_scan: its rule answers first
    note = next(m for m in ch.notes if m["event"] == "waypoint_dash_refused")
    assert note["opposite_in_flight"] and out is not None and not out.mask & B["DASH"] and out.mask & B["R"]

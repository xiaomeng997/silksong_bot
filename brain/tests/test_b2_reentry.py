"""Causal land re-entry without a saved draft, native execution, or a model rollout."""
from copy import deepcopy
import json
from pathlib import Path

import pytest

from ssbot.combat import knife_chain_slam as family
from ssbot.combat.knife_chain_eval_fast import bind_slam_runner
from ssbot.combat.knife_chain_format import chains_from_json, MASK_NAMES as B
from ssbot.combat.knife_chain_history import HistView

FA = 2598
IID = 335460


def state(f, *, ground=False, antic=FA, iid=IID):
    # The regression's observed falling approach, shortened to relevant lanes.
    sample = {2599: (31.998, 7.706, 28.09), 2601: (32.148, 7.132, 27.97),
              2602: (32.223, 6.821, 27.91), 2603: (32.223, 6.493, 27.91),
              2604: (32.298, 6.146, 27.85), 2605: (32.373, 5.783, 27.79),
              2606: (32.448, 5.404, 27.73), 2607: (32.523, 5.009, 27.67)}
    hx, hy, cx = sample.get(f, (32.5, 5.009, 27.67))
    return {"f": f, "dt": 1 / 60, "hero": {"health": 7, "silk": 9,
        "pos": [hx, hy], "box": [hx - .23, hy - 1.553, hx + .23, hy + .526],
        "vel": [0., -22.], "hero_accepting_input": True, "anim": {"clip": "Fall"}},
        "ents": [{"iid": iid, "type_key": "Song Heavy Sentry", "hp": 150,
            "flipX": True, "pos": [cx, 7.449],
            "fsms": [{"name": "Control", "state": "Slam Antic", "t": (f - antic) / 60}]}], "ev": []}


def runner(bound=False, *, b2=True):
    path = Path(family.__file__).with_name("knife_chain_slam_v01.json")
    chains = chains_from_json(json.loads(path.read_text("utf-8")))
    cfg = dict(chains["slam_jump"].cfg)
    cfg.update(CLAWSTRIKE=False, AIRSTRIKE=False, EARLY=False, TWO_PLAY=False, TWO_HANDOFF=False)
    for chain in chains.values():
        chain.cfg = cfg.copy()
    r = family.make_runner(chains)
    r.anchor.b2_strict_observations = b2
    return bind_slam_runner(r) if bound else r


def history(*, first=2599, sent=None, cut=2607, ground_before=False, antic=FA):
    fs = [f for f in (2599, 2601, 2602, 2603, 2604, 2605, 2606, 2607) if f >= first]
    rows = [(f, state(f, antic=antic), f / 60, ground_before, True) for f in fs]
    # Actual successful ordinary sends; target2602 is missing, not zero-padded.
    sent = ({2600: 0, 2601: 0, 2603: B["L"], 2604: B["L"], 2605: B["L"],
             2606: B["L"], 2607: B["L"], 2608: B["L"]} if sent is None else sent)
    return HistView(rows, sent, cut, strict_pogo=True)


@pytest.mark.parametrize("bound", [False, True])
def test_2599_land_to_2607_reentry_matches_continuous_wait_without_missing_receipt(bound):
    continuous = runner(bound)
    assert continuous.step(2599, state(2599), False, True, t_game=2599 / 60) == B["R"]
    assert continuous.run.link == "land" and continuous.run.v["k_air"] == 3
    for f in (2601, 2602, 2603, 2604, 2605, 2606):
        continuous.step(f, state(f), False, True, t_game=f / 60)
    expected = continuous.step(2607, state(2607), False, True, t_game=2607 / 60)
    assert expected == 0 and continuous.run.link == "land"

    fresh = runner(bound)
    H = history(); before = deepcopy(H.sent)
    an = H.antic(IID, "Slam Antic", ())
    assert not H.complete_antic_receipts(an)
    fresh.anchor.hist = H
    assert fresh.anchor.external is False and fresh.run is None
    mask = fresh.step(2607, state(2607), False, True, t_game=2607 / 60)
    assert mask == expected and fresh.run.link == continuous.run.link
    assert fresh.run.v["k_air"] == continuous.run.v["k_air"] == 3
    assert fresh.run.v["late"] == continuous.run.v["late"]
    assert fresh.run.entered["via"] == "observed_early_air"
    assert H.sent == before and 2602 not in dict(fresh.run.sent)
    assert fresh.anchor.external is False  # no general external-entry relaxation


@pytest.mark.parametrize("bound", [False, True])
def test_late_current_air_without_early_air_history_stays_unchecked(bound):
    fresh = runner(bound); fresh.anchor.hist = history(first=2607)
    assert fresh.step(2607, state(2607), False, True, t_game=2607 / 60) is None
    assert fresh.run is None or fresh.run.link != "land"
    assert not fresh.anchor.entries and fresh.anchor.external is False


@pytest.mark.parametrize("bits", [B["J"], B["D"] | B["A"], B["CLAW"]])
def test_existing_external_land_key_guards_still_reject_another_started_action(bits):
    fresh = runner(); H = history()
    H.sent[2603] = 0; H.sent[2604] = bits
    H.F_sorted = sorted(H.sent)
    fresh.anchor.hist = H
    assert fresh.step(2607, state(2607), False, True, t_game=2607 / 60) is None
    assert not fresh.anchor.entries


@pytest.mark.parametrize("why", ["no_history", "ground_history", "other_antic", "other_target", "future_cut", "ground_now"])
def test_only_same_current_observed_antic_air_can_restore_land(why):
    fresh = runner(); H = history(); current = state(2607); ground = False
    if why == "no_history": H = None
    elif why == "ground_history": H = history(ground_before=True)
    elif why == "other_antic": H = history(antic=FA - 60)
    elif why == "other_target": current = state(2607, iid=IID + 1)
    elif why == "future_cut": H = history(cut=2608)
    elif why == "ground_now": ground = True
    fresh.anchor.hist = H
    fresh.step(2607, current, ground, True, t_game=2607 / 60)
    assert not fresh.anchor.entries
    assert fresh.run is None or fresh.run.entered is None


def test_current_land_guards_can_still_abort_reconstructed_early_air():
    fresh = runner(); fresh.anchor.hist = history(cut=2630)
    current = state(2630)
    assert fresh.step(2630, current, False, True, t_game=2630 / 60) is None
    assert fresh.run is None
    assert fresh.done[-1].v["why"] == "no landing"


def test_no_successful_historical_land_entry_is_not_manufactured_from_air_only():
    fresh = runner(); H = history()
    # Every early observation is behind the target, so its original look guards
    # never reached land even though the generic airborne bit is true.
    for f, s, *_ in H.rows:
        s["hero"]["pos"][0] = 20.
        s["hero"]["box"][: :2] = [19.77, 20.23]
    fresh.anchor.hist = H
    fresh.step(2607, state(2607), False, True, t_game=2607 / 60)
    assert not fresh.anchor.entries


@pytest.mark.parametrize("bound", [False, True])
def test_non_b2_reentry_retains_the_original_late_current_look_behavior(bound):
    fresh = runner(bound, b2=False); fresh.anchor.hist = history()
    assert fresh.step(2607, state(2607), False, True, t_game=2607 / 60) is None
    assert not fresh.anchor.entries
    assert fresh.run is None or fresh.run.link != "land"

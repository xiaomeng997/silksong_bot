"""Task 180 (Sol seq 248): the manual-B two-Clapper L2 as complete tactic units (clapper_tactics) under one shared
pick (clapper_priority). Each rule id belongs to one unit with its documented maximum; the shared selector and
application name no tactic; only the winner commits; the evaluation log names every tactic's outcome (offers, not
applicable and why, excluded by which event, filtered by the scene owner) and the pick's triggers; event releases are
logged with their reason. Behaviour is the earlier decide's (the replay regression of #322 compares it call by call)."""
import inspect
from dataclasses import replace

import pytest

from ssbot.combat.tactics import clapper_priority as P, clapper_tactics as T, gauntlet as G
from tests.test_clapper_priority import change, manual, scene, step   # noqa: F401  (autouse manual-B fixture)

DOC_SCORES = {"keep": 50., "intercept": 130., "hold": 140., "near": 110., "takeoff": 90., "middle": 70.,
              "retreat": 150., "flip": 80., "overhead": 65., "middle_jump": 95., "bait": 145., "return": 145.,
              "back": 70.}
EVENTS = ("middle_jump", "intercept_hold", "takeoff", "back", "cluster")


def test_every_rule_is_one_tactic_unit_with_its_documented_maximum():
    assert P.DEFAULT_SCORES == DOC_SCORES
    assert sorted(T.RULES) == sorted(DOC_SCORES)
    assert all(rule in T.RULES[rule].scores for rule in DOC_SCORES)
    names = [t.name for t in T.TACTICS]
    assert len(set(names)) == len(names) == 11          # bait -> return and intercept -> hold: one unit each
    assert sorted(t.event for t in T.TACTICS if t.event) == sorted(EVENTS)
    assert {t.event for t in T.OBSERVE} == set(EVENTS)
    # the pool order keeps the earlier decide's tie order: keep first, the cluster route last
    assert [r for t in T.TACTICS for r in t.scores] == ["keep", "middle_jump", "intercept", "hold", "near", "takeoff",
                                                         "middle", "retreat", "flip", "overhead", "back", "bait",
                                                         "return"]


def test_the_shared_pick_and_application_name_no_tactic():
    src = inspect.getsource(P)
    for name in list(DOC_SCORES) + list(EVENTS):
        assert '"%s"' % name not in src and "'%s'" % name not in src, name


def test_only_the_winner_commits_and_every_tactic_may_only_release(monkeypatch):
    tac, ws, fc = scene(hx=15.); step(tac, ws, fc)
    calls = []
    for tactic in T.TACTICS:
        for hook in ("commit", "release"):
            orig = getattr(tactic, hook)
            monkeypatch.setattr(tactic, hook, lambda sc, rule, target, _o=orig, _t=tactic, _h=hook:
                                (calls.append((_h, _t.name)), _o(sc, rule, target))[1])
    change(fc, 7, family=G.CC_JUMP, state="Jump Antic", committed=True)
    step(tac, ws, fc)
    assert tac.last["clapper_winner"]["rule"] == "bait"
    assert [c for c in calls if c[0] == "commit"] == [("commit", "cluster bait and return")]
    assert sorted(n for h, n in calls if h == "release") == sorted(t.name for t in T.TACTICS)


def test_the_pick_log_names_every_tactic_and_the_scene_owner_filter():
    tac, ws, fc = scene(hx=15.); step(tac, ws, fc)
    change(fc, 7, family=G.CC_JUMP, state="Jump Antic", committed=True)
    step(tac, ws, fc)
    ev = tac.last["clapper_eval"]
    assert ev["winner"]["rule"] == "bait" and ev["winner"]["tactic"] == "cluster bait and return"
    assert "subjects changed" in ev["triggers"]
    recs = {r["tactic"]: r for r in ev["tactics"]}
    assert list(recs) == [t.name for t in T.TACTICS]
    for r in ev["tactics"]:
        assert sum(k in r for k in ("offers", "not_applicable", "excluded_by")) == 1, r
    assert recs["cluster bait and return"]["offers"] == ["bait"] and recs["keep focus"]["offers"] == ["keep"]
    # every other offer is out of the pool while the route owns the jump, and says so
    pool = {c["rule"] for c in tac.last["clapper_choices"]}
    assert pool <= {"keep", "bait"}
    for name, r in recs.items():
        if "offers" in r and name not in ("keep focus", "cluster bait and return"):
            assert r["filtered_by"] == "cluster bait and return"


def test_a_jump_between_the_two_excludes_its_fallbacks_in_the_log():
    tac, ws, fc = scene(xs=(20., 32.), hx=26.); step(tac, ws, fc)
    change(fc, 7, family=G.CC_JUMP, state="Jump Antic", committed=True)
    step(tac, ws, fc)
    recs = {r["tactic"]: r for r in tac.last["clapper_eval"]["tactics"]}
    assert recs["middle jump"]["offers"] == ["middle_jump"]
    for name in ("jump intercept", "focus take-off", "enter middle", "outer jump retreat", "flip inward",
                 "tight middle overhead"):
        assert recs[name]["excluded_by"] == ["middle_jump"], name


def test_an_event_end_is_logged_with_its_reason():
    tac, ws, fc = scene(hx=15.); step(tac, ws, fc)
    change(fc, 7, family=G.CC_JUMP, state="Jump Antic", committed=True)
    step(tac, ws, fc)
    change(fc, 7, family=G.CC_IDLE, state="Idle", committed=False)
    step(tac, ws, fc)
    assert {"tactic": "cluster bait and return", "end": "jump ended"} in tac.last["clapper_releases"]


def test_a_tactic_offer_needs_no_change_to_the_shared_code():
    # an override of one tactic's maximum reaches the pool through the shared comparison alone
    tac, ws, fc = scene(hx=15.); step(tac, ws, fc)
    tac.rules = replace(tac.rules, clapper_scores={"bait": 10.})
    change(fc, 7, family=G.CC_JUMP, state="Jump Antic", committed=True)
    step(tac, ws, fc)
    bait = next(c for c in tac.last["clapper_choices"] if c["rule"] == "bait")
    assert bait["maximum"] == pytest.approx(10.) and tac.last["clapper_winner"]["rule"] == "keep"

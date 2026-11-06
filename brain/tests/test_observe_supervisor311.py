"""Task 179 #311 (Sol seq 231): the observation bout through the REAL supervisor and control path.

Under SSBOT_FORUM_OBSERVE_BOUT=1 the Forum supervisor config records Q1 / Q3 / Q4 / Q6 (HP, predicted death, hit
counts, risk) and never pauses or quits on them: non-lethal hits down to 1 HP and a guard-vetoed lethal hit leave the
planner's next key in place (SupervisedControl returns no override). The switch off keeps Q1's pause / quit; Q5,
QF and the other fault paths still pause either way. The bout only starts on the healthy TRAIN LethalBlock."""
from types import SimpleNamespace as NS

import pytest

from ssbot.ipc.framing import BIT
from ssbot.safety import game_codes as gc
from ssbot.safety.supervisor import OBSERVE_ONLY_TRIGGERS, forum_supervisor_config
from ssbot.train import observe_bout
from ssbot.train.supervision import SupervisedControl, entity_support

PAUSE = 1 << BIT["pause"]


def playing(f, hp, ev=()):
    return {"f": f, "q": f * 166_667, "ts": 1.0, "ev": list(ev), "ents": [],
            "game": {"gs": gc.GS_PLAYING, "ui": 4, "menu": 6, "fading": False, "paused": False, "pd_mode": 0,
                     "scene": "Bone_05"},
            "pause": {"blk": 0, "dsq": False, "preload": False},
            "hero": {"health": hp, "max_health": 7, "health_blue": 0,
                     "fractured_mask": {"equipped": False, "amount_left": 0}}}


def control(monkeypatch, observe):
    monkeypatch.setenv(observe_bout.ENV, "1" if observe else "0")
    cfg = forum_supervisor_config()
    assert cfg.observe_only == (OBSERVE_ONLY_TRIGGERS if observe else frozenset())
    return SupervisedControl(cfg, support=lambda s: entity_support(s, worst_damage=2))


def bout(sc):
    """7 HP; three 2-mask hits (f 10, 30, 50) to 1 HP; a guard-vetoed lethal hit at f 70 (HP stays 1); on to f 90."""
    hp, out = 7, []
    for f in range(91):
        ev = []
        if f in (10, 30, 50):
            hp -= 2
            ev = [{"k": "damage", "d": {"source": "x", "amount": 2}}]
        if f == 70:
            ev = [{"k": "would_die", "d": {"blocked": True, "cause": "death_catch"}}]
        out.append((f, hp, sc.step(playing(f, hp, ev))))
    return out


def test_observed_hits_to_one_hp_and_a_vetoed_lethal_hit_keep_the_planner_keys(monkeypatch):
    sc = control(monkeypatch, True)
    out = bout(sc)
    assert all(r.mask is None and not r.decision.pause_pending and not r.decision.quit_requested for _, _, r in out)
    assert sc.pq is None and sc.first_pending_f is None
    low = [r for f, hp, r in out if hp == 1]
    assert low and all("Q1" in r.decision.triggers and "Q1" in r.decision.observed for r in low)
    assert all(r.decision.tier == "RED" and r.decision.restrictions.no_new_fights for r in low)   # actual-HP care
    assert any("Q1: hits_to_death 1" in x for r in low for x in r.decision.reasons)
    mid = [r for f, hp, r in out if hp == 3]
    assert any("Q3" in r.decision.observed for r in mid)                    # h = 2, unknown support: recorded only


def test_without_the_observation_q1_still_hands_the_keys_to_the_pause_loop(monkeypatch):
    sc = control(monkeypatch, False)
    out = bout(sc)
    f0, hp0, r0 = next((f, hp, r) for f, hp, r in out if r.decision.pause_pending)
    assert hp0 <= 3 and r0.decision.quit_requested and any(t in r0.decision.triggers for t in ("Q1", "Q3"))
    assert not r0.decision.observed and sc.pq is not None
    assert any(r.mask is not None for f, hp, r in out if f >= f0)


def test_observed_q4_hit_counts_are_recorded_not_latched(monkeypatch):
    sc = control(monkeypatch, True)
    for f in range(6):
        kw = {"unpredicted_hits": 1, "unpredicted_sources": (5,)} if f in (2, 4) else {}
        r = sc.step(playing(f, 7), **kw)
    assert "Q4" in r.decision.observed and not r.decision.pause_pending and sc.sup.q4 is None
    assert r.mask is None


@pytest.mark.parametrize("fault", ["frame_age", "unknown_scene", "injected"])
@pytest.mark.parametrize("observe", [False, True])
def test_fault_paths_still_pause_under_the_observation(monkeypatch, fault, observe):
    sc = control(monkeypatch, observe)
    sc.step(playing(0, 7))
    st, kw = playing(1, 7), {}
    if fault == "frame_age":
        kw = {"frame_age_ms": 60.0}
    elif fault == "unknown_scene":
        kw = {"scene_known": False}
    else:
        sc.inject_fault("QF", "test")
    r = sc.step(st, **kw)
    assert r.decision.pause_pending and not r.decision.observed
    assert {"Q5", "QF"} & set(r.decision.triggers)


GOOD = {"lethal_block": "block", "profile": "TRAIN", "refused": False,
        "healthy": {"net1": True, "net2": True, "watcher": True}}


@pytest.mark.parametrize("change,ok", [({}, True), ({"lethal_block": "off"}, False), ({"profile": "RELEASE"}, False),
                                      ({"refused": True}, False), ({"healthy": {"net1": True, "net2": False}}, False),
                                      ({"healthy": {}}, False)])
def test_the_bout_only_starts_on_the_healthy_train_lethal_block(change, ok):
    assert observe_bout.guard_ok({**GOOD, **change}) is ok


@pytest.mark.parametrize("observe,guards,starts", [(True, GOOD, True), (True, {**GOOD, "lethal_block": "off"}, False),
                                                   (False, {**GOOD, "lethal_block": "off"}, True)])
def test_back_into_slot_checks_the_guard_only_for_the_observation(monkeypatch, observe, guards, starts):
    from ssbot.probes import common
    from ssbot.tools import combat_run
    monkeypatch.setenv(observe_bout.ENV, "1" if observe else "0")
    monkeypatch.setattr(common, "load_slot", lambda *a, **k: None)
    monkeypatch.setattr(common, "stand_up", lambda *a, **k: None)
    calls = []
    link = NS(closed=False, state={},
              rpc=lambda name, **k: calls.append(name) or ({"save_suppression": True} if name == "guards.set" else guards))
    if starts:
        combat_run.back_into_slot(link, NS(scene="x"), 0, tries=1)
    else:
        with pytest.raises(SystemExit, match="healthy TRAIN LethalBlock"):
            combat_run.back_into_slot(link, NS(scene="x"), 0, tries=1)
    assert ("guards.get" in calls) is observe

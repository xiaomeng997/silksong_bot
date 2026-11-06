"""Task 179 #317 (Sol seq 240): 甲 the Idle Time a strike witness may use comes from causal evidence per Idle instance
(map2.clapper reads idle_buddy at the Idle ENTRY: 68 with the buddy alive then, unknown keeps 39; a hit since the entry
revokes it), and 乙 an air transfer / continuation Run over its target with no strike witness possible hands back
through B2 recovery instead of holding until it falls on her."""
from pathlib import Path
from types import SimpleNamespace as NS

import numpy as np

from ssbot.combat import knife_chain_transfer as T
from ssbot.combat.knife_chain_air import load_runner
from ssbot.combat.knife_chain_air_native import NativeManualAirChain
from ssbot.combat.knife_chain_eval import Run
from ssbot.combat.knife_chain_format import MASK_NAMES as B
from tests.test_knife_chain_transfer import fit_pose


def _native():
    n = NativeManualAirChain(runner_factory=load_runner, probe_ref="strike-evidence")
    n.reset(0, start_frame=999)
    return n


def _clapper(iid, x, state="Idle", t=0., hp=100, flip=False):
    return fit_pose({"iid": iid, "type_key": "Song Heavy Sentry", "hp": hp, "pos": [x, 7.45], "vel": [0., 0.],
                     "flipX": flip, "fsms": [{"name": "Control", "state": state, "t": t}],
                     "colliders": [{"name": "Song Heavy Sentry", "enabled": True, "verts_world": []}]})


def _state(f, ents, hits=(), hero=(20., 12.)):
    x, y = hero
    return {"f": f, "ents": ents, "ev": [{"k": "hit", "f": f, "d": {"src": "DownSlash", "ent": i}} for i in hits],
            "hero": {"pos": [x, y], "box": [x - .25, y - 1.04, x + .25, y + 1.04], "health": 7}}


def _feed(n, f0, f1, t0=0., x8=25., hits=None, buddy_hp=100):
    """Clapper 8 Idle from frame f0 (clock t0 there), 7 alive at x 18 (hp buddy_hp); hits: {frame: [iids]}."""
    for f in range(f0, f1 + 1):
        n._observe_idle_evidence(_state(f, [_clapper(7, 18., hp=buddy_hp), _clapper(8, x8, t=t0 + (f - f0) / 60.)],
                                        (hits or {}).get(f, ())))


def test_the_buddy_at_an_observed_idle_entry_gives_the_with_buddy_idle_time():
    n = _native()
    _feed(n, 1000, 1005)                                     # entry seen at 1000 (clock 0), 7 alive then
    ev = n._idle_ev[8]
    assert (ev["entry"], ev["buddy"], ev["hit"]) == (1000, True, None)
    assert T.idle_time_of(ev) == 68 and T.idle_time_of(None) == 39


def test_an_unobserved_entry_or_a_dead_buddy_keeps_the_no_buddy_time():
    n = _native()
    _feed(n, 1000, 1003, t0=.5)                              # first seen 30 frames into its Idle: entry not observed
    assert n._idle_ev[8]["buddy"] is None and T.idle_time_of(n._idle_ev[8]) == 39
    m = _native()
    _feed(m, 1000, 1003, buddy_hp=0)                         # the buddy dead at the entry
    assert m._idle_ev[8]["buddy"] is False and T.idle_time_of(m._idle_ev[8]) == 39


def test_a_hit_during_the_instance_revokes_it_and_only_a_new_instance_rebinds():
    n = _native()
    _feed(n, 1000, 1010, hits={1008: [8]})                   # the same Idle still shown after a hit (frozen fixture)
    ev = n._idle_ev[8]
    assert ev["hit"] == 1008 and T.idle_time_of(ev) == 39
    # the reaction ends in a new Idle: its clock restarts on the hit frame, the hit does not revoke the new instance
    for f in range(1011, 1014):
        n._observe_idle_evidence(_state(f, [_clapper(7, 18.), _clapper(8, 25., t=(f - 1011) / 60.)],
                                        [8] if f == 1011 else ()))
    ev = n._idle_ev[8]
    assert (ev["entry"], ev["hit"], ev["buddy"]) == (1011, None, True)


def test_any_other_state_drops_the_record():
    n = _native()
    _feed(n, 1000, 1002)
    n._observe_idle_evidence(_state(1003, [_clapper(7, 18.), _clapper(8, 25., state="Slam Antic", t=0.)]))
    assert 8 not in n._idle_ev


def test_the_witness_reads_the_given_idle_time():
    e = _clapper(8, 25., t=50 / 60.)                          # Idle k 50: past 39, inside 68
    assert T.contact_body_witness(e, 10, idle_no_evade=True) is None or \
        not np.isfinite(T.contact_body_witness(e, 10, idle_no_evade=True)).all(axis=1).any()
    w = T.contact_body_witness(e, 10, idle_no_evade=True, idle_time=68)
    assert w is not None and np.isfinite(w[:10]).all()


def _sim():
    return NS(prefix=np.array([0], np.int64))


def test_over_the_target_with_no_witness_is_a_reason_a_witness_or_not_over_is_not():
    n = _native()
    over = _state(1100, [_clapper(7, 18.), _clapper(8, 25., t=50 / 60.)], hero=(25., 12.))
    assert "no strike witness" in n._no_strike_overhead(over, _sim(), 8)          # Idle k 50, no evidence: 39
    _feed(n, 1050, 1100)                                     # the same Idle with its entry (1050) and buddy seen
    over = _state(1100, [_clapper(7, 18.), _clapper(8, 25., t=50 / 60.)], hero=(25., 12.))
    assert n._no_strike_overhead(over, _sim(), 8) is None                          # 68: the witness still holds
    beside = _state(1100, [_clapper(7, 18.), _clapper(8, 25., t=80 / 60.)], hero=(30., 12.))
    assert n._no_strike_overhead(beside, _sim(), 8) is None                        # not over her: the Run approaches
    n._idle_ev[8]["hit"] = 1090
    assert "revoked" in n._no_strike_overhead(over, _sim(), 8)
    recover = _state(1100, [_clapper(7, 18.), _clapper(8, 25., state="Slam Recover", t=0.)], hero=(25., 12.))
    assert n._no_strike_overhead(recover, _sim(), 8) is None                       # a fitted still pose with time
    # live prefix 2612: a still state whose witness is absent for now (pose still settling) keeps the Run
    bad = _clapper(8, 25., state="Slam Recover", t=0.)
    bad["colliders"][0]["verts_world"] = [23., 3.5, 27., 3.5, 27., 7.5, 23., 7.5]
    assert T.contact_body_witness(bad, 10) is None
    assert n._no_strike_overhead(_state(1100, [_clapper(7, 18.), bad], hero=(25., 12.)), _sim(), 8) is None
    moving = _clapper(8, 25., state="Slam Recover", t=0.)
    moving["fsms"][0]["state"] = "Evade Scuttle"
    assert "no fitted still pose" in n._no_strike_overhead(_state(1100, [_clapper(7, 18.), moving], hero=(25., 12.)),
                                                           _sim(), 8)


def test_an_air_run_over_a_target_with_no_witness_hands_back_through_recovery(monkeypatch):
    n = _native()
    p = T.TransferPlan(8, 7, 900, 1000, 0., B["R"], 10000, 0, 0, False, 1000, 0)
    for link, handed in (("air", True), ("strike", False)):
        n.runner.run = Run(T.PROGRAM, link, p.variables())
        rec = []
        monkeypatch.setattr(n, "_recover", lambda why, f: rec.append((why, f)))
        monkeypatch.setattr(n, "queued_prefix", lambda f, s: (None, None))       # stop right after the decision
        st = _state(1100, [_clapper(7, 18.), _clapper(8, 25., t=50 / 60.)], hero=(25., 12.))
        n._transfer_offer(st, 1., _sim(), None, NS(target=8), False)
        got = [e for e in n.events if e["event"] == "transfer_no_witness_handback" and e["frame"] == 1100]
        assert bool(got) is handed and (rec[:1] and "no strike witness" in rec[0][0]) == handed
        n.events.clear()


def _admission(evidence, target_t):
    """A fresh air ReturnGoal start over 476-like body toward a target Idle at clock target_t (A3-like 2798 pose)."""
    from ssbot.combat.air_chain import ChainSim
    from ssbot.knowledge import kinematics as K
    root = Path(__file__).resolve().parents[2]
    params = K.hero2(K.HeroParams.load(root / "knowledge/1.0.30000/kinematics/hero_wanderer_forum.json"))
    terrain = K.Terrain2D.from_boxes([(-100., -10., 100., 3.015)])
    hx, hy = 19.62, 13.40
    s = {"f": 1000, "hero": {"pos": [hx, hy], "health": 7, "hero_accepting_input": True},
         "ents": [_clapper(7, 20.47, flip=True), _clapper(8, 26.2, t=target_t)],
         "act": {"hf": {"latched": 0, "desired": 0, "pending": [0] * 22, "age": [100] * 22}}}
    S = K.initial_state(params, hx, hy + .514, vx=0., vy=-5., facing=1, ground=False)
    sim = ChainSim(S, np.array([0], np.int64), K.HoldState.from_act(s["act"]), params, terrain, 1000, 1000)
    n = _native()
    if evidence is not None:
        n._idle_ev[8] = evidence
    plan = T.TransferPlan(8, 7, 900, 1000, 0., B["R"], 2, 0, 0, False, 1000, 0)
    geo = NS(scan=lambda path: NS(complete=True, contacts=()))
    return n._return_admission(s, sim, plan, 1., geo)


def test_after_a_hit_the_old_idle_evidence_is_revoked_and_admission_needs_a_new_instance():
    fresh = {"entry": 990, "buddy": True, "hit": None, "t": .2, "first": 990}
    assert _admission(fresh, .2) is None                                 # a fresh Idle with its entry seen
    hit = dict(fresh, hit=995)
    assert "strike witness" in _admission(hit, .2)                       # the same instance after a hit: no witness
    # 40 frames past the entry: only the with-buddy Idle Time (68) still holds over her
    assert "strike witness" in _admission(dict(fresh, buddy=None), 40 / 60.)
    assert _admission(fresh, 40 / 60.) is None
    renewed = {"entry": 1000, "buddy": True, "hit": None, "t": 0., "first": 1000}
    assert _admission(renewed, 0.) is None                               # the reaction's new Idle: re-admitted


def test_the_runs_press_now_rows_read_the_idle_evidence(monkeypatch):
    from ssbot.combat.knife_chain_eval import Prims
    p = Prims()
    T.register(p)
    stomp = p.acts["transfer_stomp_plan"]
    seen = []
    monkeypatch.setattr(T, "contact_body_witness",
                        lambda e, frames, idle_no_evade=False, idle_time=None: seen.append(idle_time))
    e = _clapper(8, 25., t=.5)

    def x(ev):
        return NS(v={"jump_until": 0, "side": B["R"]},
                  obs=NS(sim=NS(prefix=np.array([0])), ground=False, e=e, k=0, f=1000,
                         hero={"box": [24.75, 11., 25.25, 13.]}, idle_ev=ev))
    assert stomp(x({"entry": 970, "buddy": True, "hit": 990})) is None and seen == []   # revoked: no witness at all
    stomp(x({"entry": 970, "buddy": True, "hit": None}))
    stomp(x({"entry": 970, "buddy": None, "hit": None}))
    stomp(x(None))
    assert seen == [68, 39, 39]

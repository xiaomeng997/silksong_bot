"""Targeted hook step and cached early-jump finite cases: the sent / in-flight hook's current step and the early-jump expansion.

They drive the development tree's real transfer.propose, transfer.render, air.model_path, transfer.face_hook_check,
map2.strike.claw_hook and B2Geometry.scan (with a stub RangeSupport as Root's geometry tests use). Model rows,
not a hit, ride or flight claim."""
from pathlib import Path
from types import SimpleNamespace as NS

import numpy as np
import pytest

import ssbot
from ssbot.combat.knife_chain_air import load_runner as _load_runner, model_path


def load_runner():
    r=_load_runner();r.chains["rune_transfer"].cfg["FACE_HOOK"]=True
    return r


@pytest.fixture(autouse=True)
def enable_face_hook(monkeypatch):
    monkeypatch.setenv("SSBOT_FORUM_CHAIN_FACE_HOOK","1")
from ssbot.combat.knife_chain_eval import Run
from ssbot.combat.knife_chain_format import MASK_NAMES as B
from ssbot.combat.knife_chain_transfer import TransferPlan, propose
from ssbot.combat import knife_chain_face_hook as FH
from ssbot.combat.knife_chain_geometry import B2Geometry, GeometryUnavailable
from ssbot.combat.knife_chain_commitment import MoveInstance
from ssbot.knowledge import kinematics as K
from ssbot.combat.air_chain import ChainSim

ROOT = Path(ssbot.__file__).resolve().parents[2]
PARAMS = K.hero2(K.HeroParams.load(ROOT / "knowledge/1.0.30000/kinematics/hero_wanderer_forum.json"))
TERRAIN = K.Terrain2D.from_boxes([(-100., -10., 100., 3.015)])
MOVE = MoveInstance(8, 990, "RUNE_TRANSFER")


def ent(iid, x, st, face=-1, t=.1, vx=0.):
    return {"iid": iid, "type_key": "Song Heavy Sentry", "hp": 100, "pos": [x, 7.45], "vel": [vx, 0.], "flipX": face > 0,
            "fsms": [{"name": "Control", "state": st, "t": t}],
            "colliders": [{"name": "Song Heavy Sentry", "enabled": True,
                           "verts_world": [x - 1.8, 3.01, x + 1.8, 3.01, x + 1.8, 6.92, x - 1.8, 6.92]}]}


def act(f, mask):
    return {"target": f, "applied": f, "mask": mask, "hf": {"latched": mask, "desired": mask, "pending": [0] * 22, "age": [100] * 22}}


def scene(f=1000, gap=6., st="Idle", y=7.0, vy=0., prefix=0, t_state=.1, hx=25.):
    s = {"f": f, "dt": 1 / 60,
         "hero": {"pos": [hx, y], "box": [hx - .25, y - 1.553, hx + .25, y + .532], "vel": [0., vy], "health": 7,
                  "hero_accepting_input": True, "silk": 3, "can": {"harpoon": True}, "tm": {"dash_cd": 0.},
                  "anim": {"clip": "Airborne"}},
         "ents": [ent(7, 12., "Cast 2", face=1), ent(8, 25. + gap, st, face=-1, t=t_state)], "act": act(f, prefix), "ev": []}
    S = K.initial_state(PARAMS, hx, y, vy=vy, mode=K.M_NORMAL, ground=False)
    return s, ChainSim(S, np.array([prefix], np.int64), K.HoldState.from_act(s["act"]), PARAMS, TERRAIN, f, f)


def ground_plan(f=1000):
    return TransferPlan(8, 7, 990, 990, 990 / 60., B["R"], 10000, 10000, 10000, False, f, f - 990)


def ground_scene(gap=11., f=1000, st="Idle", t_state=.1, vel=8.25):
    key = B["R"]
    s = {"f": f, "dt": 1 / 60,
         "hero": {"pos": [25., 4.568], "box": [24.75, 3.015, 25.25, 5.1], "vel": [vel, 0.], "health": 7,
                  "hero_accepting_input": True, "silk": 3, "can": {"harpoon": True}, "tm": {"dash_cd": .25},
                  "anim": {"clip": "Run"}},
         "ents": [ent(7, 12., "Cast 2", face=1), ent(8, 25. + gap, st, face=-1, t=t_state)], "act": act(f, key), "ev": []}
    S = K.initial_state(PARAMS, 25., 4.568, vx=vel, mode=K.M_NORMAL, ground=True)
    sim = ChainSim(S, np.array([key], np.int64), K.HoldState.from_act(s["act"]), PARAMS, TERRAIN, f, f)
    r = load_runner()
    r.run = Run("rune_transfer", "walk", {**dict(r.chains["rune_transfer"].vars), **ground_plan(f).variables()})
    return r, s, sim


def step_path(f, **kw):
    s, sim = scene(f=f, **kw)
    return model_path(sim, NS(origin=f, press_k=None, entry_k=0, contact_frame=None, iid=8, move=MOVE),
                      np.zeros(1, np.int64), f / 60.)


def anchor(gap=6., **kw):
    s, sim = scene(gap=gap, **kw)
    return FH.press_anchor(sim, 1, 1002, s["ents"][1])          # P = 1003


def seen(P):
    return {"move": MOVE, "origin": P - 2, "targets": (P, P + 1), "sent_targets": {P}, "seen_frame": P}


def rs_stub(region=None, owner=9):
    """Root's geometry-test stub: owner `owner`'s body occupies hero-centre x in region (any y); no hazards."""
    def occ(x, y, t):
        x = np.asarray(x)
        return np.zeros(x.shape, bool) if region is None else (x >= region[0]) & (x <= region[1])
    return NS(k_shift=0, samples=(0, 62), margin_mode="rule", focus=7,
              trk=NS(now={8: (0, 0, NS(fam=None)), owner: (0, 0, NS(fam=None))}, orphan_hazards={}),
              haz_raw={}, raw={}, layers={}, bombs=None,
              cv=NS(cell=.1, index=lambda x, y: (x, y, np.ones(np.asarray(x).shape, bool))),
              occupied=occ, occupied_only=lambda x, y, t, ids: occ(x, y, t) if owner in ids else np.zeros(np.asarray(x).shape, bool),
              occupied_hazards=lambda x, y, t, ids: np.zeros(np.asarray(x).shape, bool))


# ---- (A) the sent / in-flight hook's current step -------------------------------------------------------------------

def test_overlay_follows_the_hooked_model_over_a_whole_hook():
    a = anchor()
    P = a["P"]
    inc = {}
    for j in range(0, 42):
        ps = FH.step_paths(step_path(P + j), {"hook_press": a}, seen(P), P + j)
        inc[j] = {(round(float(q.box[2, 0] - q.box[0, 0]), 3), round(float(q.box[2, 1] - q.box[0, 1]), 3)) for q in ps}
        assert all(not q.check_flags.any() and not q.flags.any() for q in ps)          # no protection
        assert all(dx >= -1e-9 for dx, _ in inc[j])                                     # never away from the face
    free = step_path(P + 12, vy=-5.)
    assert free.box[2, 1] - free.box[0, 1] < -.1                                        # K falls ...
    held = FH.step_paths(free, {"hook_press": a}, seen(P), P + 12)
    assert {(round(float(q.box[2, 0] - q.box[0, 0]), 3), round(float(q.box[2, 1] - q.box[0, 1]), 3))
            for q in held} == {(0., 0.)} == inc[12]                                      # ... the Throw holds still
    assert max(dx for j in range(14, 24) for dx, _ in inc[j]) >= 1.4                    # the hooked dash: 1.4 u / step
    late = FH.step_paths(step_path(P + 41), {"hook_press": a}, seen(P), P + 41)
    assert any(q.stage != "transfer_hook_step" for q in late)                            # after control: K's flight


def test_overlay_preflight_catches_an_other_owner_on_the_dash_that_free_flight_misses():
    a = anchor()
    P = a["P"]
    j = next(j for j in range(14, 26) if any(abs(q.box[2, 0] - q.box[0, 0]) >= 1.4 for q in
             FH.step_paths(step_path(P + j), {"hook_press": a}, seen(P), P + j)))
    f = P + j
    path = step_path(f)
    x0 = .5 * (path.box[0, 0] + path.box[0, 2])
    geo = B2Geometry(NS(rs=rs_stub((x0 + .7, x0 + 3.))), f, MOVE, None)
    assert not geo.preflight(path).contacts                                              # K: no contact
    scan = FH.step_scan(geo, path, {"hook_press": a}, seen(P), f)
    assert scan.complete and any(c.owner_iid == 9 for c in scan.contacts)
    target_only = B2Geometry(NS(rs=rs_stub((x0 + .7, x0 + 3.), owner=8)), f, MOVE, None)
    assert any(c.owner_iid==8 for c in FH.step_scan(target_only, path, {"hook_press": a}, seen(P), f).contacts)  # target danger is retained too


def test_overlay_keeps_no_invulnerability_from_the_free_flight_rows():
    a = anchor()
    P = a["P"]
    f = P + 12
    path = step_path(f)
    path.check_flags = path.check_flags | K.F_INVULN
    x0 = .5 * (path.box[0, 0] + path.box[0, 2])
    geo = B2Geometry(NS(rs=rs_stub((x0 - .05, x0 + .05))), f, MOVE, None)
    assert not geo.preflight(path).contacts                                              # masked by F_INVULN
    assert FH.step_scan(geo, path, {"hook_press": a}, seen(P), f).contacts               # unmasked: zero protection


@pytest.mark.parametrize("case", ["no_anchor", "no_watch", "nothing_sent", "press_outside_slots", "bad_rows"])
def test_unknown_hook_step_is_explicitly_unchecked(case):
    a = anchor()
    P = a["P"]
    f = P + 5
    v, w, path = {"hook_press": a}, seen(P), step_path(f)
    if case == "no_anchor":
        v = {}
    if case == "no_watch":
        w = None
    if case == "nothing_sent":
        w = {**w, "sent_targets": set(), "seen_frame": None}
    if case == "press_outside_slots":
        w = {**w, "seen_frame": P + 7}
    if case == "bad_rows":
        path.box = path.box[:2]
    with pytest.raises(GeometryUnavailable, match="unchecked"):
        FH.step_paths(path, v, w, f)


def test_a_missed_first_slot_keeps_the_second_slot_and_its_late_application_anchored():
    a = anchor()
    P = a["P"]
    w = {**seen(P), "sent_targets": {P + 1}, "seen_frame": None}                       # only the hold slot was sent
    ps = FH.step_paths(step_path(P + 20), {"hook_press": a}, w, P + 20)                  # presses P+1 .. P+3
    assert any(q.stage == "transfer_hook_step" for q in ps)
    assert FH.step_paths(step_path(P + 20), {"hook_press": a}, {**w, "seen_frame": P + 3}, P + 20)
    with pytest.raises(GeometryUnavailable, match="planned slots|late bound"):
        FH.step_paths(step_path(P + 20), {"hook_press": a}, {**w, "seen_frame": P + 4}, P + 20)


def test_sent_not_seen_press_covers_late_application_and_keeps_k_rows_while_ahead():
    a = anchor()
    P = a["P"]
    w = {**seen(P), "seen_frame": None}
    ps = FH.step_paths(step_path(P - 1), {"hook_press": a}, w, P - 1)                    # P in flight, P+1 / P+2 ahead
    assert any(q.stage != "transfer_hook_step" for q in ps) and any(q.stage == "transfer_hook_step" for q in ps)
    ps = FH.step_paths(step_path(P + 17), {"hook_press": a}, w, P + 17)                  # P, P+1, P+2 all possible:
    dx = {round(float(q.box[2, 0] - q.box[0, 0]), 3) for q in ps}                        # the early dash moves,
    assert 0. in dx and max(dx) >= 1.4                                                   # a late press still holds


def test_transfer_offer_checks_a_sent_hook_through_the_overlay_and_unknown_is_unchecked(monkeypatch):
    from ssbot.combat import knife_chain_air_native as mod
    from ssbot.combat.knife_chain_air import AirAnchor
    from ssbot.combat.claw_strike import CsPlan
    a = anchor()
    P = a["P"]
    f = P + 18
    n = mod.NativeManualAirChain(runner_factory=load_runner, probe_ref="hookstep170")
    n.reset(0, start_frame=1000)
    p = replace_plan(f)
    v = {**dict(load_runner().chains["rune_transfer"].vars), **p.variables(), "cs": CsPlan(P - 1, 0, P, 0), "hook_press": a}
    n.runner.run = Run("rune_transfer", "claw_lock", dict(v))
    draft = load_runner().fork_empty(AirAnchor())
    draft.run = Run("rune_transfer", "claw_lock", dict(v))
    path = step_path(f)
    monkeypatch.setattr(mod.transfer, "propose", lambda *a_, **kw: (draft, p, path, 0))
    monkeypatch.setattr(n, "queued_prefix", lambda *a_: (0, "fixture"))
    n._hook_start = seen(P)
    n.commitment = {"move": MOVE, "origin": P - 2, "ta": p.ta}
    n._context = (None, None, None, None)
    st, _ = scene(f=f)
    fc = NS(rs=rs_stub())
    calls = []
    real = FH.step_scan
    monkeypatch.setattr(FH, "step_scan", lambda *a_: (calls.append(a_[1]), real(*a_))[1])
    offer = n._transfer_offer(st, f / 60., NS(prefix=np.array([0])), fc, NS(target=8), False)
    assert offer is not None and calls == [path] and n.counts["transfer_hook_step_checked"] == 1
    recovered = []
    monkeypatch.setattr(n, "_recover", lambda reason, frame: recovered.append(reason))
    draft.run.v.pop("hook_press")
    assert n._transfer_offer(st, f / 60., NS(prefix=np.array([0])), fc, NS(target=8), False) is None
    assert n.counts["rune_transfer_unchecked"] == 1 and recovered == ["rune transfer external step unchecked"]


def replace_plan(f):
    return TransferPlan(8, 7, 990, 990, 990 / 60., B["R"], 10000, 10000, 10000, False, f, f - 990)


# ---- (B) the early jump: one existing-recipe expansion, cached in the Run -------------------------------------------

def early(gap, **kw):
    r, s, sim = ground_scene(gap=gap, **kw)
    return FH.early_jump(r, ground_plan(), sim, 1000 / 60., s, s["ents"][1], None, 10, "walk", False)


def test_early_jump_admits_a_face_hook_band_on_one_expansion():
    e = early(11.)
    assert e["ok"] and e["jump_k"] == 13 and e["next_f"] == 1001 and e["decide_f"] > 1001
    assert e["ray_margin"] >= 0. and e["retreat_reserve"] > 0.


def test_failed_expansion_waits_for_its_own_reach_deficit_or_a_new_target_state():
    e = early(20.)
    assert not e["ok"] and 1001 < e["next_f"] <= 1000 + 36
    assert not FH.early_jump_stale(e, e["next_f"] - 1, "Idle")
    assert FH.early_jump_stale(e, e["next_f"], "Idle") and FH.early_jump_stale(e, 1001, "Walk")


def test_the_evaluation_tick_sends_no_j_and_the_next_tick_jumps_from_the_cache(monkeypatch):
    calls = []
    real = FH.early_jump
    monkeypatch.setattr(FH, "early_jump", lambda *a, **kw: (calls.append(1), real(*a, **kw))[1])
    r, s, sim = ground_scene(gap=11.)
    made = propose(r, s, 1000 / 60., sim, 8, True, np.zeros((0, 6)), set())
    assert made is not None and made[0] is not None and len(calls) == 1
    assert not made[3] & B["J"] and made[0].run.v["early_hook"]["ok"]                  # nothing built on a J tick
    r.run = made[0].run
    r2, s2, sim2 = ground_scene(gap=11. - 8.25 / 60., f=1001)
    made2 = propose(r, s2, 1001 / 60., sim2, 8, True, np.zeros((0, 6)), set())
    assert len(calls) == 1 and made2[3] & B["J"]                                         # jumps without recomputing


@pytest.mark.parametrize("case", ["within_jump_root", "spell_antic", "approach_only", "cached_failure"])
def test_no_early_jump_expansion_outside_its_scope(case, monkeypatch):
    calls = []
    monkeypatch.setattr(FH, "early_jump", lambda *a, **kw: calls.append(1))
    r, s, sim = ground_scene(gap=7. if case == "within_jump_root" else 11.,
                             st="Spell Antic" if case == "spell_antic" else "Idle")
    if case == "approach_only":
        r.run.v["_approach_only"] = True
    if case == "cached_failure":
        r.run.v["early_hook"] = {"f": 999, "ok": False, "state": "Idle", "jump_k": 12, "next_f": 1010}
    made = propose(r, s, 1000 / 60., sim, 8, True, np.zeros((0, 6)), set())
    assert calls == []
    if case == "within_jump_root":
        assert made[3] & B["J"]                                                          # the existing rule jumps


@pytest.mark.parametrize("case", ["other_target", "bad_target_slots", "unsent_seen_slot", "out_of_window_send"])
def test_hook_step_rejects_watch_identity_and_unreported_activation(case):
    a=anchor();P=a["P"];w=seen(P)
    if case=="other_target":w["move"]=MoveInstance(9,990,"RUNE_TRANSFER")
    elif case=="bad_target_slots":w["targets"]=(P+1,P+2)
    elif case=="unsent_seen_slot":w["seen_frame"]=P+3
    else:w["sent_targets"]={P+2}
    with pytest.raises(GeometryUnavailable):FH.step_paths(step_path(P+20),{"hook_press":a},w,P+20)


def test_disabled_face_hook_never_builds_the_early_jump_recipe(monkeypatch):
    r,s,sim=ground_scene(gap=11.);r.chains["rune_transfer"].cfg["FACE_HOOK"]=False
    def fail(*a,**kw):raise AssertionError("disabled feature built an early-jump recipe")
    monkeypatch.setattr(FH,"early_jump",fail)
    made=propose(r,s,1000/60.,sim,8,True,np.zeros((0,6)),set())
    assert made is not None and "early_hook" not in made[0].run.v and not made[3]&B["J"]
